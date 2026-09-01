#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/uninstaller_dialog.py — نافذة إلغاء التثبيت القوي (مستوحاة من IObit Uninstaller).
"""
from __future__ import annotations
import shutil
import re
from typing import List, Tuple

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QMessageBox, QCheckBox, QProgressBar, QGroupBox, QSplitter,
    QTextEdit, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("uninstaller_dialog")


class PackageLoaderWorker(QThread):
    packages_loaded = pyqtSignal(list)  # list of (name, version, size, desc, is_explicit)
    failed = pyqtSignal(str)

    def run(self):
        try:
            # الحزم المثبتة مع الحجم والوصف
            r = run_unprivileged(["pacman", "-Qi"])
            if not r.ok:
                self.failed.emit("فشل قراءة الحزم")
                return

            packages = []
            current = {}
            for line in r.stdout.splitlines():
                if line.startswith("Name "):
                    current["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Version "):
                    current["version"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description "):
                    current["desc"] = line.split(":", 1)[1].strip()
                elif line.startswith("Installed Size "):
                    current["size"] = line.split(":", 1)[1].strip()
                elif line.startswith("Install Reason "):
                    current["explicit"] = "Explicitly" in line
                elif line.strip() == "" and current.get("name"):
                    packages.append((
                        current.get("name", ""),
                        current.get("version", ""),
                        current.get("size", "—"),
                        current.get("desc", ""),
                        current.get("explicit", True),
                    ))
                    current = {}

            # الحزم اليتيمة (orphans)
            orphan_r = run_unprivileged(["pacman", "-Qdtq"])
            orphans = set(orphan_r.stdout.strip().splitlines()) if orphan_r.ok else set()

            # دمج الحالة
            final = []
            for name, ver, size, desc, explicit in packages:
                is_orphan = name in orphans
                final.append((name, ver, size, desc, explicit, is_orphan))

            self.packages_loaded.emit(final)
        except Exception as exc:
            self.failed.emit(str(exc))


class UninstallWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, packages: List[str], deep_clean: bool = True, parent=None):
        super().__init__(parent)
        self.packages = packages
        self.deep_clean = deep_clean

    def run(self):
        logs = []
        try:
            # 1. إلغاء التثبيت مع الاعتماديات والإعدادات
            cmd = ["pacman", "-Rns", "--noconfirm"] + self.packages
            self.progress.emit(f"جاري إزالة: {', '.join(self.packages)}...")
            result = run_privileged(cmd)
            logs.append(result.stdout + result.stderr)

            if not result.ok:
                self.failed.emit(f"فشل الإزالة:\n{result.stderr}")
                return

            # 2. التنظيف العميق (بقايا AUR, cache, build files)
            if self.deep_clean:
                self.progress.emit("جاري التنظيف العميق للبقايا...")
                for pkg in self.packages:
                    # حذف من cache AUR
                    for cache_dir in [f"/tmp/{pkg}", f"/var/tmp/{pkg}"]:
                        run_privileged(["rm", "-rf", cache_dir])
                    # حذف من home cache (yay/paru)
                    home_cache = run_unprivileged(["bash", "-c", "echo $HOME"]).stdout.strip()
                    if home_cache:
                        for helper in ["yay", "paru"]:
                            p = f"{home_cache}/.cache/{helper}/{pkg}"
                            run_privileged(["rm", "-rf", p])

                # pacman -Sc (تنظيف cache الحزم المُلغى تثبيتها)
                run_privileged(["pacman", "-Sc", "--noconfirm"])

            self.finished_ok.emit("\n".join(logs))
        except Exception as exc:
            self.failed.emit(str(exc))


class UninstallerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إلغاء تثبيت البرامج 🗑️")
        self.resize(880, 640)
        self.setLayoutDirection(Qt.RightToLeft)
        self._loader = None
        self._worker = None
        self._all_packages = []  # (name, ver, size, desc, explicit, orphan)
        self._build_ui()
        self._load_packages()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # شريط البحث والفلترة
        top_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 ابحث عن حزمة...")
        self.search_edit.textChanged.connect(self._filter)
        top_row.addWidget(self.search_edit, stretch=1)

        self.orphan_only_check = QCheckBox("الحزم اليتيمة فقط")
        self.orphan_only_check.stateChanged.connect(self._filter)
        top_row.addWidget(self.orphan_only_check)

        self.select_all_btn = QPushButton("تحديد الكل")
        self.select_all_btn.clicked.connect(self._select_all)
        top_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("إلغاء التحديد")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        top_row.addWidget(self.deselect_all_btn)

        layout.addLayout(top_row)

        # الجدول
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "الحزمة", "الإصدار", "الحجم", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        # تفاصيل الاعتماديات
        details_group = QGroupBox("تفاصيل الحزمة المحددة")
        details_layout = QVBoxLayout(details_group)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(100)
        details_layout.addWidget(self.details_text)
        layout.addWidget(details_group)

        self.table.itemSelectionChanged.connect(self._show_details)

        # شريط التقدم
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # الأزرار السفلية
        btn_row = QHBoxLayout()

        self.deep_clean_check = QCheckBox("تنظيف عميق (إزالة بقايا AUR + Cache)")
        self.deep_clean_check.setChecked(True)
        btn_row.addWidget(self.deep_clean_check)

        btn_row.addStretch()

        self.uninstall_btn = QPushButton("🗑️ إلغاء تثبيت المحدد")
        self.uninstall_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold;")
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        btn_row.addWidget(self.uninstall_btn)

        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self._load_packages)
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _load_packages(self):
        self.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._loader = PackageLoaderWorker(parent=self)
        self._loader.packages_loaded.connect(self._on_packages_loaded)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.start()

    def _on_packages_loaded(self, packages):
        self._all_packages = packages
        self.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._filter()

    def _on_load_failed(self, err):
        self.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "خطأ", err)

    def _filter(self):
        query = self.search_edit.text().lower()
        orphan_only = self.orphan_only_check.isChecked()

        filtered = []
        for name, ver, size, desc, explicit, is_orphan in self._all_packages:
            if query and query not in name.lower() and query not in desc.lower():
                continue
            if orphan_only and not is_orphan:
                continue
            filtered.append((name, ver, size, desc, explicit, is_orphan))

        self.table.setRowCount(len(filtered))
        for row, (name, ver, size, desc, explicit, is_orphan) in enumerate(filtered):
            chk = QCheckBox()
            self.table.setCellWidget(row, 0, chk)

            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(ver))
            self.table.setItem(row, 3, QTableWidgetItem(size))

            if is_orphan:
                status = "يتيمة ⚠️"
                color = "#ff9800"
            elif not explicit:
                status = "تبعية"
                color = "#aaaaaa"
            else:
                status = "مثبتة"
                color = "#2e7d32"

            status_item = QTableWidgetItem(status)
            status_item.setForeground(QtGui.QColor(color))
            self.table.setItem(row, 4, status_item)

            # تخزين الاسم في الصف لاستخدامه لاحقاً
            self.table.item(row, 1).setData(Qt.UserRole, name)

    def _show_details(self):
        selected = self.table.selectedItems()
        if not selected:
            self.details_text.clear()
            return

        row = self.table.currentRow()
        name_item = self.table.item(row, 1)
        if not name_item:
            return
        pkg_name = name_item.data(Qt.UserRole)

        # جلب معلومات الاعتماديات
        r = run_unprivileged(["pacman", "-Qi", pkg_name])
        self.details_text.setPlainText(r.stdout or "لا تفاصيل.")

    def _select_all(self):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if isinstance(w, QCheckBox):
                w.setChecked(True)

    def _deselect_all(self):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if isinstance(w, QCheckBox):
                w.setChecked(False)

    def _on_uninstall(self):
        selected = []
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if isinstance(w, QCheckBox) and w.isChecked():
                name = self.table.item(row, 1).data(Qt.UserRole)
                selected.append(name)

        if not selected:
            QMessageBox.warning(self, "تنبيه", "اختر حزمة واحدة على الأقل.")
            return

        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"سيتم إلغاء تثبيت {len(selected)} حزمة/حزم مع الاعتماديات والبقايا.\nهل أنت متأكد؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._worker = UninstallWorker(
            selected, deep_clean=self.deep_clean_check.isChecked(), parent=self
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_uninstall_ok)
        self._worker.failed.connect(self._on_uninstall_failed)
        self._worker.start()

    def _on_progress(self, msg):
        self.progress_bar.setFormat(msg)

    def _on_uninstall_ok(self, msg):
        self.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "تم", "تم إلغاء التثبيت والتنظيف بنجاح.")
        self._load_packages()

    def _on_uninstall_failed(self, err):
        self.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "خطأ", err)
        self._load_packages()
