#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/repo_dialog.py
====================
نافذة مخصصة لإدارة مستودعات pacman — تفعيل/تعطيل المستودعات الأساسية
(core, extra, community, multilib) معاً + تثبيت AUR helper.

مستوحى من Garuda Assistant → Repositories.
يعتمد على نفس نمط StartupManagerDialog في:
  - استخدام QTableWidget مع أزرار تبديل لكل صف
  - RTL layout
  - pkexec للتعديلات التي تتطلب صلاحيات
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QMessageBox, QGroupBox, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("repo_dialog")

_PACMAN_CONF = Path("/etc/pacman.conf")

# المستودعات الأساسية بالترتيب الذي تظهر به في pacman.conf
_CORE_REPOS = ["core", "extra", "community", "multilib"]

# مسارات AUR helpers المحتملة
_AUR_HELPERS = ["yay", "paru", "trizen"]


def _read_pacman_conf() -> str:
    """قراءة pacman.conf (للقراءة فقط — لا يحتاج صلاحيات)."""
    try:
        return _PACMAN_CONF.read_text(encoding="utf-8")
    except Exception as e:
        log.warning(f"فشل قراءة pacman.conf: {e}")
        return ""


def _is_repo_enabled(conf_text: str, repo_name: str) -> bool:
    """هل المستودع مفعل (السطر لا يبدأ بـ #)؟"""
    pattern = rf"^\s*#?\s*\[{re.escape(repo_name)}\]\s*$"
    for line in conf_text.splitlines():
        if re.match(pattern, line):
            return not line.strip().startswith("#")
    return False


def _has_aur_helper() -> str | None:
    """تحقق من توفر AUR helper."""
    for helper in _AUR_HELPERS:
        if shutil.which(helper):
            return helper
    return None


def _toggle_repo_in_conf(conf_text: str, repo_name: str, enable: bool) -> str:
    """تعديل نص pacman.conf لتفعيل/تعطيل مستودع معين.

    تعمل على مستوى النص (string manipulation) — لا تكتب للملف.
    """
    lines = conf_text.splitlines()
    new_lines = []
    found = False

    for line in lines:
        pattern = rf"^(\s*#?\s*)\[{re.escape(repo_name)}\]\s*$"
        m = re.match(pattern, line)
        if m:
            found = True
            if enable:
                new_lines.append(f"[{repo_name}]")
            else:
                new_lines.append(f"#[{repo_name}]")
        else:
            new_lines.append(line)

    if not found:
        # المستودع غير موجود — أضفه في النهاية
        new_lines.append("")
        if enable:
            new_lines.append(f"[{repo_name}]")
        else:
            new_lines.append(f"#[{repo_name}]")

    return "\n".join(new_lines) + "\n"


class _ApplyChangesWorker(QThread):
    """Worker thread لتطبيق التغييرات على pacman.conf."""

    finished_signal = pyqtSignal(bool, str)

    def __init__(self, new_conf_text: str):
        super().__init__()
        self.new_conf_text = new_conf_text

    def run(self):
        try:
            # كتابة pacman.conf تتطلب صلاحيات — استخدم pkexec
            # نكتب النص الجديد إلى ملف مؤقت ثم نستخدم pkexec cp
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".conf", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(self.new_conf_text)
                tmp_path = tmp.name

            # نسخ الملف المؤقت إلى pacman.conf عبر pkexec
            result = run_privileged([
                "cp", tmp_path, str(_PACMAN_CONF)
            ])

            # حذف الملف المؤقت
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass

            if result.ok:
                # مزامنة pacman بعد التغيير
                sync_result = run_privileged(["pacman", "-Sy", "--noconfirm"])
                if sync_result.ok:
                    self.finished_signal.emit(
                        True,
                        "تم تحديث المستودعات وإعادة المزامنة بنجاح."
                    )
                else:
                    self.finished_signal.emit(
                        True,
                        f"تم تحديث pacman.conf لكن فشل المزامنة: {sync_result.stderr}"
                    )
            else:
                self.finished_signal.emit(
                    False,
                    f"فشل كتابة pacman.conf: {result.stderr}"
                )
        except Exception as e:
            self.finished_signal.emit(False, f"خطأ غير متوقع: {e}")


class _InstallAurHelperWorker(QThread):
    """Worker thread لتثبيت AUR helper (yay)."""

    finished_signal = pyqtSignal(bool, str)

    def run(self):
        try:
            # تحقق أولاً إن كان مثبتاً
            if shutil.which("yay"):
                self.finished_signal.emit(True, "yay مثبت بالفعل.")
                return

            # yay متوفر في مستودعات Manjaro الرسمية (ليس في AUR فقط)
            result = run_privileged(["pacman", "-S", "--noconfirm", "yay"])
            if result.ok:
                self.finished_signal.emit(True, "تم تثبيت yay بنجاح.")
            else:
                self.finished_signal.emit(
                    False,
                    f"فشل تثبيت yay: {result.stderr}"
                )
        except Exception as e:
            self.finished_signal.emit(False, f"خطأ غير متوقع: {e}")


class RepoManagerDialog(QDialog):
    """نافذة إدارة مستودعات pacman.

    تعرض جدولاً بالمستودعات الأساسية مع checkbox لكل منها،
    وزراً لتثبيت AUR helper، وزراً لتطبيق التغييرات.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة مستودعات pacman")
        self.resize(600, 480)
        self.setLayoutDirection(Qt.RightToLeft)

        self._original_conf = _read_pacman_conf()
        self._current_conf = self._original_conf
        self._apply_worker = None
        self._aur_worker = None

        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── معلومات توضيحية ──
        info = QLabel(
            "فعّل أو عطّل المستودعات الأساسية. التعطيل قد يمنع تثبيت حزم مهمة "
            "(خاصة multilib للبرامج 32-bit)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaaaaa; padding: 4px;")
        layout.addWidget(info)

        # ── مجموعة المستودعات ──
        repos_group = QGroupBox("المستودعات الأساسية")
        repos_layout = QVBoxLayout(repos_group)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["المستودع", "الحالة", "تبديل"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        repos_layout.addWidget(self.table)

        layout.addWidget(repos_group)

        # ── مجموعة AUR helper ──
        aur_group = QGroupBox("AUR Helper")
        aur_layout = QHBoxLayout(aur_group)

        self.aur_label = QLabel("جاري الفحص...")
        self.aur_label.setStyleSheet("padding: 4px;")
        aur_layout.addWidget(self.aur_label)

        aur_layout.addStretch()

        self.install_aur_btn = QPushButton("تثبيت yay")
        self.install_aur_btn.clicked.connect(self._install_aur_helper)
        aur_layout.addWidget(self.install_aur_btn)

        layout.addWidget(aur_group)

        # ── أزرار التحكم ──
        buttons_row = QHBoxLayout()

        self.apply_btn = QPushButton("تطبيق التغييرات")
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #2d5f2d; color: white; "
            "padding: 8px 16px; font-weight: bold; }"
        )
        self.apply_btn.clicked.connect(self._apply_changes)
        buttons_row.addWidget(self.apply_btn)

        buttons_row.addStretch()

        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self._reload)
        buttons_row.addWidget(refresh_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        buttons_row.addWidget(close_btn)

        layout.addLayout(buttons_row)

        # ── شريط الحالة ──
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(self.status_label)

    def _reload(self) -> None:
        """إعادة تحميل الحالة الحالية من pacman.conf."""
        self._original_conf = _read_pacman_conf()
        self._current_conf = self._original_conf
        self.table.setRowCount(len(_CORE_REPOS))

        for row, repo in enumerate(_CORE_REPOS):
            enabled = _is_repo_enabled(self._current_conf, repo)

            # اسم المستودع
            name_item = QTableWidgetItem(repo)
            name_item.setFont(QFont("", weight=QFont.Bold))
            self.table.setItem(row, 0, name_item)

            # الحالة
            status_text = "مفعّل ✔" if enabled else "معطَّل ✘"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(
                Qt.green if enabled else Qt.red
            )
            self.table.setItem(row, 1, status_item)

            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(enabled)
            checkbox.stateChanged.connect(
                lambda state, r=row: self._on_toggle(r, state)
            )
            self.table.setCellWidget(row, 2, checkbox)

        # AUR helper status
        aur = _has_aur_helper()
        if aur:
            self.aur_label.setText(f"✓ AUR helper متوفر: {aur}")
            self.aur_label.setStyleSheet("color: #4a9; padding: 4px;")
            self.install_aur_btn.setEnabled(False)
            self.install_aur_btn.setText("yay مثبت ✓")
        else:
            self.aur_label.setText("✗ لا يوجد AUR helper")
            self.aur_label.setStyleSheet("color: #a55; padding: 4px;")
            self.install_aur_btn.setEnabled(True)

        self.status_label.setText("جاهز — عدّل المستودعات ثم اضغط «تطبيق التغييرات».")
        self.apply_btn.setEnabled(False)  # لا تغييرات بعد

    def _on_toggle(self, row: int, state: int) -> None:
        """عند تبديل checkbox لمستودع."""
        repo_name = _CORE_REPOS[row]
        enable = state == Qt.Checked

        # تحديث الحالة في الجدول
        status_item = self.table.item(row, 1)
        if status_item:
            status_item.setText("مفعّل ✔" if enable else "معطَّل ✘")
            status_item.setForeground(Qt.green if enable else Qt.red)

        # تحديث النص الحالي
        self._current_conf = _toggle_repo_in_conf(
            self._current_conf, repo_name, enable
        )

        # تفعيل زر التطبيق
        changed = self._current_conf != self._original_conf
        self.apply_btn.setEnabled(changed)
        if changed:
            self.status_label.setText(
                f"تغييرات معلّقة — اضغط «تطبيق التغييرات» للحفظ."
            )
        else:
            self.status_label.setText("لا تغييرات معلّقة.")

    def _apply_changes(self) -> None:
        """تطبيق التغييرات على pacman.conf عبر pkexec."""
        if self._current_conf == self._original_conf:
            QMessageBox.information(self, "لا تغييرات", "لا توجد تغييرات للتطبيق.")
            return

        # تأكيد
        reply = QMessageBox.question(
            self,
            "تأكيد التغييرات",
            "سيتم تعديل /etc/pacman.conf وإعادة مزامنة pacman.\n"
            "هل أنت متأكد؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.apply_btn.setEnabled(False)
        self.apply_btn.setText("جاري التطبيق...")
        self.status_label.setText("جاري كتابة pacman.conf وإعادة المزامنة...")

        self._apply_worker = _ApplyChangesWorker(self._current_conf)
        self._apply_worker.finished_signal.connect(self._on_apply_finished)
        self._apply_worker.start()

    def _on_apply_finished(self, success: bool, message: str) -> None:
        """عند انتهاء تطبيق التغييرات."""
        self.apply_btn.setText("تطبيق التغييرات")
        self.apply_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "نجح", message)
            self._reload()  # إعادة تحميل الحالة الجديدة
        else:
            QMessageBox.critical(self, "فشل", message)
            self.status_label.setText(f"فشل: {message}")

        self._apply_worker = None

    def _install_aur_helper(self) -> None:
        """تثبيت yay عبر pacman."""
        reply = QMessageBox.question(
            self,
            "تثبيت AUR helper",
            "سيتم تثبيت yay من المستودعات الرسمية لـ Manjaro.\n"
            "هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.install_aur_btn.setEnabled(False)
        self.install_aur_btn.setText("جاري التثبيت...")
        self.aur_label.setText("جاري تثبيت yay...")
        self.aur_label.setStyleSheet("color: #888; padding: 4px;")

        self._aur_worker = _InstallAurHelperWorker()
        self._aur_worker.finished_signal.connect(self._on_aur_finished)
        self._aur_worker.start()

    def _on_aur_finished(self, success: bool, message: str) -> None:
        """عند انتهاء تثبيت AUR helper."""
        if success:
            QMessageBox.information(self, "نجح", message)
        else:
            QMessageBox.critical(self, "فشل", message)

        self._reload()  # إعادة تحديث حالة AUR
        self._aur_worker = None
