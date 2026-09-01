#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/file_shredder_dialog.py — نافذة الحذف الآمن (Secure File Shredder).
مستوحاة من Ashampoo WinOptimizer / Eraser.
"""
from __future__ import annotations
import os
import random
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QSpinBox, QGroupBox, QFormLayout, QFileDialog, QProgressBar,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged
from core.logger import get_logger

log = get_logger("file_shredder_dialog")


class ShredWorker(QThread):
    progress = pyqtSignal(int)
    step = pyqtSignal(str)
    finished_ok = pyqtSignal(int, str)
    failed = pyqtSignal(str)

    def __init__(self, paths: list, passes: int = 3, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.passes = passes
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            total_files = 0
            total_bytes = 0
            all_files = self._collect_files()

            if not all_files:
                self.failed.emit("لا توجد ملفات صالحة للحذف.")
                return

            for i, fpath in enumerate(all_files):
                if self._cancelled:
                    self.step.emit("تم الإلغاء.")
                    break
                pct = int((i / len(all_files)) * 100)
                self.progress.emit(pct)
                self.step.emit(f"جاري حذف: {Path(fpath).name}")
                size = Path(fpath).stat().st_size
                if self._secure_delete(fpath):
                    total_files += 1
                    total_bytes += size
                else:
                    log.warning(f"فشل حذف: {fpath}")

            self.progress.emit(100)
            self.finished_ok.emit(total_files, self._human_size(total_bytes))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _collect_files(self):
        files = []
        for p in self.paths:
            path = Path(p)
            if not path.exists():
                continue
            if path.is_file():
                files.append(str(path))
            elif path.is_dir():
                for root, _, fnames in os.walk(path):
                    for fname in fnames:
                        fpath = Path(root) / fname
                        if fpath.is_file() and not fpath.is_symlink():
                            files.append(str(fpath))
        return files

    def _secure_delete(self, fpath):
        try:
            p = Path(fpath)
            size = p.stat().st_size
            if size == 0:
                p.unlink()
                return True
            with open(p, "r+b") as f:
                for _ in range(self.passes):
                    if self._cancelled:
                        break
                    f.seek(0)
                    chunk_size = 1024 * 1024
                    written = 0
                    while written < size:
                        to_write = min(chunk_size, size - written)
                        f.write(os.urandom(to_write))
                        written += to_write
                    f.flush()
                    os.fsync(f.fileno())
            parent = p.parent
            for _ in range(3):
                rand_name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=16))
                new_path = parent / rand_name
                try:
                    p.rename(new_path)
                    p = new_path
                except OSError:
                    break
            p.unlink()
            return True
        except Exception as exc:
            log.error(f"secure_delete error: {exc}")
            return False

    @staticmethod
    def _human_size(size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class FileShredderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الحذف الآمن")
        self.resize(700, 550)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("الحذف الآمن للملفات والمجلدات")
        f = title.font()
        f.setBold(True)
        f.setPointSize(13)
        title.setFont(f)
        layout.addWidget(title)

        info = QLabel(
            "يستبدل هذا الأداة محتوى الملفات ببيانات عشوائية ثم يحذفها نهائياً.\n"
            "لا يمكن استعادة الملفات بعد الحذف!"
        )
        info.setStyleSheet("color: #ff9800;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["الاسم", "المسار", "الحجم"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree)

        top_btns = QHBoxLayout()
        add_files_btn = QPushButton("إضافة ملفات")
        add_files_btn.clicked.connect(self._add_files)
        top_btns.addWidget(add_files_btn)
        add_folder_btn = QPushButton("إضافة مجلد")
        add_folder_btn.clicked.connect(self._add_folder)
        top_btns.addWidget(add_folder_btn)
        remove_btn = QPushButton("إزالة المحدد")
        remove_btn.clicked.connect(self._remove_selected)
        top_btns.addWidget(remove_btn)
        clear_btn = QPushButton("تفريغ القائمة")
        clear_btn.clicked.connect(self.tree.clear)
        top_btns.addWidget(clear_btn)
        top_btns.addStretch()
        layout.addLayout(top_btns)

        settings_group = QGroupBox("إعدادات الحذف الآمن")
        settings_layout = QFormLayout(settings_group)
        self.passes_spin = QSpinBox()
        self.passes_spin.setRange(1, 35)
        self.passes_spin.setValue(3)
        self.passes_spin.setSuffix(" مرات")
        settings_layout.addRow("عدد مرات الكتابة العشوائية:", self.passes_spin)
        self.total_label = QLabel("0 ملفات | 0 B")
        settings_layout.addRow("إجمالي المحدد:", self.total_label)
        layout.addWidget(settings_group)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.shred_btn = QPushButton("بدء الحذف الآمن")
        self.shred_btn.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold; font-size: 12pt; padding: 8px;"
        )
        self.shred_btn.clicked.connect(self._start_shred)
        btn_row.addWidget(self.shred_btn)
        self.cancel_btn = QPushButton("إلغاء")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.cancel_btn)
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        self.tree.itemChanged.connect(self._update_totals)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختر ملفات للحذف الآمن", str(Path.home()), "كل الملفات (*)"
        )
        for f in files:
            self._add_tree_item(f)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "اختر مجلد", str(Path.home()))
        if folder:
            self._add_tree_item(folder, is_dir=True)

    def _add_tree_item(self, path, is_dir=False):
        p = Path(path)
        if not p.exists():
            return
        item = QTreeWidgetItem()
        item.setText(0, p.name + ("/" if is_dir else ""))
        item.setText(1, str(p))
        item.setText(2, self._calc_size(p))
        item.setData(0, Qt.UserRole, str(p))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        self.tree.addTopLevelItem(item)
        self._update_totals()

    def _calc_size(self, path):
        try:
            if path.is_file():
                return self._hs(path.stat().st_size)
            total = 0
            for root, _, files in os.walk(path):
                for f in files:
                    fp = Path(root) / f
                    if fp.is_file():
                        total += fp.stat().st_size
            return self._hs(total)
        except Exception:
            return "—"

    def _remove_selected(self):
        for item in self.tree.selectedItems():
            idx = self.tree.indexOfTopLevelItem(item)
            self.tree.takeTopLevelItem(idx)
        self._update_totals()

    def _update_totals(self):
        count = 0
        total_size = 0
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                path = Path(item.data(0, Qt.UserRole))
                count += 1
                try:
                    if path.is_file():
                        total_size += path.stat().st_size
                    else:
                        for root, _, files in os.walk(path):
                            for f in files:
                                fp = Path(root) / f
                                if fp.is_file():
                                    total_size += fp.stat().st_size
                except Exception:
                    pass
        self.total_label.setText(f"{count} ملف/مجلد | {self._hs(total_size)}")

    def _start_shred(self):
        paths = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                paths.append(item.data(0, Qt.UserRole))
        if not paths:
            QMessageBox.warning(self, "تنبيه", "اختر ملفاً أو مجلداً على الأقل.")
            return
        passes = self.passes_spin.value()
        reply = QMessageBox.warning(
            self, "تنبيه نهائي",
            f"سيتم حذف {len(paths)} عنصر/عناصر بشكل نهائي بعد {passes} مرات كتابة عشوائية.\n\n"
            "لا يمكن التراجع عن هذا الإجراء!\n\nهل أنت متأكد تماماً؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.cancel_btn.setVisible(True)
        self.shred_btn.setEnabled(False)
        self._worker = ShredWorker(paths, passes, parent=self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.step.connect(self.status_label.setText)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
        self.status_label.setText("جاري الإلغاء...")

    def _on_done(self, count, size):
        self.setEnabled(True)
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.shred_btn.setEnabled(True)
        self.tree.clear()
        self._update_totals()
        QMessageBox.information(self, "تم", f"تم حذف {count} ملف بشكل آمن.\nالمساحة المحررة: {size}")

    def _on_fail(self, err):
        self.setEnabled(True)
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.shred_btn.setEnabled(True)
        QMessageBox.critical(self, "خطأ", err)

    @staticmethod
    def _hs(size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
