#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/repo_dialog.py
===================
نافذة مخصصة لإدارة مستودعات pacman — تفعيل/تعطيل كل مستودع على حدة
عبر checkboxes، مع إمكانية تثبيت AUR helper (yay/paru).

مستوحاة من Garuda Assistant → Repositories، لكن مبنية حول
/etc/pacman.conf مباشرة بدل سكربتات Garuda.
"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QCheckBox, QMessageBox,
    QHeaderView, QProgressDialog, QApplication,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("repo_dialog")

_PACMAN_CONF = Path("/etc/pacman.conf")


class RepoToggleWorker(QThread):
    """خيط خلفي لتعديل pacman.conf وتشغيل pacman -Sy."""
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, repo_name: str, enable: bool, parent=None):
        super().__init__(parent)
        self.repo_name = repo_name
        self.enable = enable

    def run(self) -> None:
        try:
            # قراءة الملف الحالي
            result = run_privileged(["cat", str(_PACMAN_CONF)])
            if not result.ok:
                self.failed.emit("فشل قراءة pacman.conf")
                return

            lines = result.stdout.splitlines()
            new_lines = []
            inside_repo = False
            modified = False

            for line in lines:
                stripped = line.strip()
                # هل هذا السطر يبدأ قسم المستودع المستهدف؟
                if re.match(rf"^\s*#?\s*\[{re.escape(self.repo_name)}\]\s*$", stripped):
                    inside_repo = True
                    if self.enable:
                        # إزالة #
                        new_line = re.sub(rf"^\s*#\s*(\[{re.escape(self.repo_name)}\])", r"\1", line)
                    else:
                        # إضافة #
                        if not stripped.startswith("#"):
                            new_line = f"#{line}"
                        else:
                            new_line = line
                    if new_line != line:
                        modified = True
                    new_lines.append(new_line)
                elif inside_repo and stripped.startswith("[") and not stripped.startswith("[options]"):
                    # دخلنا قسم مستودع آخر
                    inside_repo = False
                    new_lines.append(line)
                elif inside_repo and self.enable and stripped.startswith("#Include"):
                    # تفعيل Include أيضاً داخل القسم
                    new_line = re.sub(r"^\s*#\s*(Include=)", r"\1", line)
                    if new_line != line:
                        modified = True
                    new_lines.append(new_line)
                elif inside_repo and not self.enable and stripped.startswith("Include="):
                    # تعطيل Include
                    new_line = f"#{line}"
                    if new_line != line:
                        modified = True
                    new_lines.append(new_line)
                else:
                    new_lines.append(line)

            if not modified:
                self.finished_ok.emit(f"المستودع {self.repo_name} كان بالحالة المطلوبة بالفعل.")
                return

            new_text = "\n".join(new_lines) + "\n"
            # كتابة الملف
            w_result = run_privileged(["bash", "-c", f"cat > {_PACMAN_CONF} << 'PACMANEOF'\n{new_text}PACMANEOF"])
            if not w_result.ok:
                self.failed.emit(f"فشل كتابة pacman.conf: {w_result.stderr}")
                return

            # تحديث قاعدة البيانات
            sy_result = run_privileged(["pacman", "-Sy"])
            msg = f"تم {'تفعيل' if self.enable else 'تعطيل'} مستودع {self.repo_name}"
            self.finished_ok.emit(msg)
        except Exception as exc:
            self.failed.emit(str(exc))


class AurInstallWorker(QThread):
    """خيط خلفي لتثبيت yay أو paru."""
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, helper: str, parent=None):
        super().__init__(parent)
        self.helper = helper

    def run(self) -> None:
        try:
            if self.helper == "yay":
                # تثبيت yay من AUR
                cmds = [
                    "pacman -S --needed --noconfirm git base-devel",
                    "cd /tmp && rm -rf yay && git clone https://aur.archlinux.org/yay.git && cd yay && makepkg -si --noconfirm",
                ]
            elif self.helper == "paru":
                cmds = [
                    "pacman -S --needed --noconfirm git base-devel",
                    "cd /tmp && rm -rf paru && git clone https://aur.archlinux.org/paru.git && cd paru && makepkg -si --noconfirm",
                ]
            else:
                self.failed.emit("AUR helper غير معروف")
                return

            for cmd in cmds:
                result = run_privileged(["bash", "-c", cmd])
                if not result.ok and result.returncode != 0:
                    self.failed.emit(f"فشل: {cmd}\n{result.stderr}")
                    return

            self.finished_ok.emit(f"تم تثبيت {self.helper} بنجاح!")
        except Exception as exc:
            self.failed.emit(str(exc))


class RepoManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة مستودعات pacman")
        self.resize(560, 420)
        self.setLayoutDirection(Qt.RightToLeft)

        self._toggle_worker: RepoToggleWorker | None = None
        self._aur_worker: AurInstallWorker | None = None
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "فعّل أو عطّل كل مستودع على حدة. التعديلات تُطبَّق مباشرة على "
            "/etc/pacman.conf مع تحديث قاعدة البيانات."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info)

        # ── جدول المستودعات ──
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["المستودع", "الوصف", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self.table)

        # ── قسم AUR helper ──
        aur_layout = QHBoxLayout()
        self.aur_label = QLabel("")
        self.aur_label.setStyleSheet("color: #cfcfcf;")
        aur_layout.addWidget(self.aur_label)
        aur_layout.addStretch()

        self.yay_btn = QPushButton("ثبّت yay")
        self.yay_btn.setStyleSheet("background-color: #1565c0;")
        self.yay_btn.clicked.connect(lambda: self._install_aur("yay"))
        aur_layout.addWidget(self.yay_btn)

        self.paru_btn = QPushButton("ثبّت paru")
        self.paru_btn.setStyleSheet("background-color: #1565c0;")
        self.paru_btn.clicked.connect(lambda: self._install_aur("paru"))
        aur_layout.addWidget(self.paru_btn)

        layout.addLayout(aur_layout)

        # ── أزرار الإغلاق ──
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _read_conf(self) -> str:
        try:
            return _PACMAN_CONF.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _repo_enabled(self, conf_text: str, repo_name: str) -> bool:
        pattern = rf"^\s*#?\s*\[{re.escape(repo_name)}\]\s*$"
        for line in conf_text.splitlines():
            if re.match(pattern, line):
                return not line.strip().startswith("#")
        return False

    def _reload(self) -> None:
        conf = self._read_conf()
        repos = [
            ("core", "حزم النظام الأساسية"),
            ("extra", "حزم إضافية"),
            ("community", "حزم المجتمع"),
            ("multilib", "دعم البرامج 32-bit"),
        ]

        self.table.setRowCount(len(repos))
        for row, (name, desc) in enumerate(repos):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(desc))

            enabled = self._repo_enabled(conf, name)
            chk = QCheckBox("مفعّل" if enabled else "معطَّل")
            chk.setChecked(enabled)
            chk.setStyleSheet(
                "QCheckBox { color: #2e7d32; } "
                "QCheckBox::indicator:checked { background-color: #2e7d32; }"
            )
            chk.stateChanged.connect(lambda state, n=name: self._on_toggle(n, state == Qt.Checked))
            self.table.setCellWidget(row, 2, chk)

        # AUR helper status
        aur = None
        for h in ("yay", "paru", "trizen"):
            if shutil.which(h):
                aur = h
                break
        if aur:
            self.aur_label.setText(f"AUR helper: {aur} ✔")
            self.yay_btn.setEnabled(False)
            self.yay_btn.setText("yay ✔")
            self.paru_btn.setEnabled(False)
            self.paru_btn.setText("paru ✔")
        else:
            self.aur_label.setText("لا يوجد AUR helper — ثبّت yay أو paru")
            self.yay_btn.setEnabled(True)
            self.paru_btn.setEnabled(True)

    def _on_toggle(self, repo_name: str, enable: bool) -> None:
        self.setEnabled(False)
        self._toggle_worker = RepoToggleWorker(repo_name, enable, parent=self)
        self._toggle_worker.finished_ok.connect(self._on_toggle_ok)
        self._toggle_worker.failed.connect(self._on_toggle_failed)
        self._toggle_worker.start()

    def _on_toggle_ok(self, msg: str) -> None:
        self.setEnabled(True)
        QMessageBox.information(self, "تم", msg)
        self._reload()

    def _on_toggle_failed(self, err_text: str) -> None:
        self.setEnabled(True)
        QMessageBox.critical(self, "خطأ", err_text)
        self._reload()

    def _install_aur(self, helper: str) -> None:
        reply = QMessageBox.question(
            self, "تأكيد",
            f"سيتم تثبيت {helper} من AUR.\nهل أنت متأكد؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.setEnabled(False)
        self._aur_worker = AurInstallWorker(helper, parent=self)
        self._aur_worker.finished_ok.connect(self._on_aur_ok)
        self._aur_worker.failed.connect(self._on_aur_failed)
        self._aur_worker.start()

    def _on_aur_ok(self, msg: str) -> None:
        self.setEnabled(True)
        QMessageBox.information(self, "تم", msg)
        self._reload()

    def _on_aur_failed(self, err_text: str) -> None:
        self.setEnabled(True)
        QMessageBox.critical(self, "خطأ", err_text)
        self._reload()
