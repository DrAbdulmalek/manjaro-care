#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/boot_dialog.py — نافذة مخصصة لإدارة الإقلاع (GRUB).

الميزات:
  - عرض إدخالات الإقلاع وتعيين الافتراضي
  - تعديل GRUB_TIMEOUT (مهلة الاختيار)
  - تعديل GRUB_CMDLINE_LINUX_DEFAULT (معاملات النواة)
  - إخفاء/إظهار قائمة GRUB (GRUB_TIMEOUT_STYLE)
  - تعطيل كشف أنظمة التشغيل الأخرى (os-prober)
  - تعطيل القوائم الفرعية (GRUB_DISABLE_SUBMENU)
  - دقة شاشة الإقلاع (GRUB_GFXMODE) — قائمة منسدلة
  - خلفية القائمة (GRUB_BACKGROUND) — مع متصفح ملفات
  - عرض الثيم الحالي (GRUB_THEME) — للإشارة فقط

كل التعديلات تمر عبر pkexec (polkit) ولا تجمد الواجهة (QThread).
"""
from __future__ import annotations
import re
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QSpinBox, QGroupBox, QFormLayout, QLineEdit, QCheckBox,
    QComboBox, QFileDialog,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("boot_dialog")

_GRUB_CFG = Path("/boot/grub/grub.cfg")
_GRUB_DEFAULT = Path("/etc/default/grub")
_GRUB_THEMES = Path("/boot/grub/themes")


class GrubActionWorker(QThread):
    """خيط خلفي لتنفيذ أوامر GRUB المتسلسلة عبر pkexec."""
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, commands: list[list[str]], parent=None):
        super().__init__(parent)
        self.commands = commands

    def run(self):
        logs = []
        try:
            for cmd in self.commands:
                result = run_privileged(cmd)
                if not result.ok:
                    self.failed.emit(f"فشل: {' '.join(cmd)}\n{result.stderr}")
                    return
                if result.stdout:
                    logs.append(result.stdout)
            self.finished_ok.emit("\n".join(logs) or "تم التنفيذ بنجاح.")
        except Exception as exc:
            self.failed.emit(str(exc))


class BootManagerDialog(QDialog):
    """نافذة إدارة GRUB الكاملة مع دعم الدقة والخلفية."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة الإقلاع (GRUB)")
        self.resize(760, 680)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._entries = []
        self._build_ui()
        self._reload()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── العنوان ──
        title = QLabel("إدارة إعدادات GRUB")
        f = title.font()
        f.setBold(True)
        f.setPointSize(12)
        title.setFont(f)
        layout.addWidget(title)

        # ── جدول الإدخالات ──
        entries_group = QGroupBox("إدخالات الإقلاع المتاحة")
        entries_layout = QVBoxLayout(entries_group)

        self.entries_table = QTableWidget(0, 2)
        self.entries_table.setHorizontalHeaderLabels(["#", "اسم الإدخال"])
        self.entries_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.entries_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.entries_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.entries_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.entries_table.setSelectionMode(QTableWidget.SingleSelection)
        entries_layout.addWidget(self.entries_table)
        layout.addWidget(entries_group)

        # ── الإعدادات الأساسية ──
        settings_group = QGroupBox("الإعدادات العامة")
        settings_layout = QFormLayout(settings_group)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 60)
        self.timeout_spin.setSuffix(" ثانية")
        settings_layout.addRow("مهلة اختيار النواة (GRUB_TIMEOUT):", self.timeout_spin)

        self.default_label = QLabel("—")
        settings_layout.addRow("الإدخال الافتراضي الحالي:", self.default_label)

        self.cmdline_edit = QLineEdit()
        self.cmdline_edit.setPlaceholderText("مثال: quiet splash acpi=force")
        settings_layout.addRow("معاملات النواة (CMDLINE):", self.cmdline_edit)

        self.hide_menu_check = QCheckBox("إخفاء قائمة GRUB (GRUB_TIMEOUT_STYLE=hidden)")
        settings_layout.addRow(self.hide_menu_check)

        self.disable_osprober_check = QCheckBox("تعطيل كشف أنظمة التشغيل الأخرى (os-prober)")
        settings_layout.addRow(self.disable_osprober_check)

        self.disable_submenu_check = QCheckBox("تعطيل القوائم الفرعية (GRUB_DISABLE_SUBMENU)")
        settings_layout.addRow(self.disable_submenu_check)

        layout.addWidget(settings_group)

        # ── إعدادات المظهر (الدقة والخلفية) ──
        gfx_group = QGroupBox("مظهر قائمة الإقلاع")
        gfx_layout = QFormLayout(gfx_group)

        self.gfxmode_combo = QComboBox()
        self.gfxmode_combo.setEditable(True)
        self.gfxmode_combo.addItems([
            "auto",
            "640x480",
            "800x600",
            "1024x768",
            "1280x720",
            "1280x1024",
            "1366x768",
            "1600x900",
            "1920x1080",
            "2560x1440",
            "3840x2160",
        ])
        self.gfxmode_combo.setPlaceholderText("auto")
        gfx_layout.addRow("دقة الشاشة (GRUB_GFXMODE):", self.gfxmode_combo)

        bg_row = QHBoxLayout()
        self.bg_edit = QLineEdit()
        self.bg_edit.setPlaceholderText("مثال: /boot/grub/background.png")
        bg_row.addWidget(self.bg_edit, stretch=1)

        self.bg_browse_btn = QPushButton("تصفّح...")
        self.bg_browse_btn.clicked.connect(self._browse_background)
        bg_row.addWidget(self.bg_browse_btn)

        self.bg_clear_btn = QPushButton("إزالة")
        self.bg_clear_btn.setStyleSheet("color: #c62828;")
        self.bg_clear_btn.clicked.connect(self._clear_background)
        bg_row.addWidget(self.bg_clear_btn)

        gfx_layout.addRow("خلفية القائمة (GRUB_BACKGROUND):", bg_row)

        self.theme_label = QLabel("")
        self.theme_label.setStyleSheet("color: #aaaaaa; font-size: 10pt;")
        gfx_layout.addRow("الثيم الحالي:", self.theme_label)

        layout.addWidget(gfx_group)

        # ── الأزرار ──
        btn_row = QHBoxLayout()

        self.set_default_btn = QPushButton("تعيين كإقلاع افتراضي")
        self.set_default_btn.setStyleSheet("background-color: #1565c0; color: white;")
        self.set_default_btn.clicked.connect(self._on_set_default)
        btn_row.addWidget(self.set_default_btn)

        self.save_settings_btn = QPushButton("حفظ الإعدادات وإعادة التوليد")
        self.save_settings_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        self.save_settings_btn.clicked.connect(self._on_save_settings)
        btn_row.addWidget(self.save_settings_btn)

        btn_row.addStretch()

        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self._reload)
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    # ── قراءة الإعدادات ──

    def _grub_entries(self):
        """استخراج أسماء إدخالات menuentry من grub.cfg."""
        if not _GRUB_CFG.exists():
            return []
        text = _GRUB_CFG.read_text(encoding="utf-8", errors="ignore")
        entries = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("menuentry '"):
                name = line.split("'", 2)[1] if "'" in line else ""
                if name:
                    entries.append(name)
            elif line.startswith('menuentry "'):
                name = line.split('"', 2)[1] if '"' in line else ""
                if name:
                    entries.append(name)
        return entries

    def _read_grub_var(self, key, default):
        """قراءة متغير من /etc/default/grub."""
        if not _GRUB_DEFAULT.exists():
            return default
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*)$")
        for line in _GRUB_DEFAULT.read_text().splitlines():
            m = pattern.match(line)
            if m:
                val = m.group(1).strip().strip('"').strip("'")
                return val
        return default

    def _grub_timeout(self):
        return self._read_grub_var("GRUB_TIMEOUT", "5")

    def _grub_default(self):
        return self._read_grub_var("GRUB_DEFAULT", "")

    def _grub_cmdline(self):
        return self._read_grub_var("GRUB_CMDLINE_LINUX_DEFAULT", "")

    def _grub_timeout_style_hidden(self):
        val = self._read_grub_var("GRUB_TIMEOUT_STYLE", "")
        return val.lower() == "hidden"

    def _grub_osprober_disabled(self):
        val = self._read_grub_var("GRUB_DISABLE_OS_PROBER", "")
        return val.lower() == "true"

    def _grub_submenu_disabled(self):
        val = self._read_grub_var("GRUB_DISABLE_SUBMENU", "")
        return val.lower() == "true"

    def _grub_gfxmode(self):
        return self._read_grub_var("GRUB_GFXMODE", "auto")

    def _grub_background(self):
        return self._read_grub_var("GRUB_BACKGROUND", "")

    def _grub_theme(self):
        return self._read_grub_var("GRUB_THEME", "")

    # ── التحميل ──

    def _reload(self):
        self._entries = self._grub_entries()
        current_default = self._grub_default()
        current_timeout = self._grub_timeout()

        # ملء الجدول
        self.entries_table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            idx_item = QTableWidgetItem(str(row))
            idx_item.setTextAlignment(Qt.AlignCenter)
            self.entries_table.setItem(row, 0, idx_item)
            self.entries_table.setItem(row, 1, QTableWidgetItem(entry))

            # تمييز الافتراضي
            if current_default == str(row) or current_default == entry:
                self.entries_table.selectRow(row)
                self.entries_table.item(row, 1).setBackground(Qt.darkGreen)
                self.entries_table.item(row, 1).setForeground(Qt.white)

        self.default_label.setText(current_default or "0")
        self.timeout_spin.setValue(int(current_timeout) if str(current_timeout).isdigit() else 5)
        self.cmdline_edit.setText(self._grub_cmdline())
        self.hide_menu_check.setChecked(self._grub_timeout_style_hidden())
        self.disable_osprober_check.setChecked(self._grub_osprober_disabled())
        self.disable_submenu_check.setChecked(self._grub_submenu_disabled())

        # تحميل إعدادات المظهر
        gfxmode = self._grub_gfxmode()
        idx = self.gfxmode_combo.findText(gfxmode, Qt.MatchFixedString)
        if idx >= 0:
            self.gfxmode_combo.setCurrentIndex(idx)
        else:
            self.gfxmode_combo.setCurrentText(gfxmode)

        self.bg_edit.setText(self._grub_background())

        theme = self._grub_theme()
        if theme:
            self.theme_label.setText(f"{theme}")
        else:
            self.theme_label.setText("لا يوجد (افتراضي)")

        if not self._entries:
            QMessageBox.information(
                self, "تنبيه",
                "لم يُعثر على grub.cfg — قد يكون النظام يستخدم systemd-boot."
            )

    # ── إجراءات المظهر ──

    def _browse_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "اختر صورة الخلفية",
            "/boot/grub",
            "الصور (*.png *.jpg *.jpeg *.tga);;كل الملفات (*)"
        )
        if path:
            self.bg_edit.setText(path)

    def _clear_background(self):
        self.bg_edit.clear()

    # ── الإجراءات الأساسية ──

    def _on_set_default(self):
        selected = self.entries_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "تنبيه", "اختر إدخالاً من الجدول أولاً.")
            return

        row = self.entries_table.currentRow()
        if row < 0 or row >= len(self._entries):
            return

        entry_name = self._entries[row]
        reply = QMessageBox.question(
            self, "تأكيد",
            f"هل تريد تعيين «{entry_name}» كإقلاع افتراضي؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        commands = [
            ["bash", "-c", f"sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=\"{entry_name}\"/' {_GRUB_DEFAULT}"],
            ["grub-mkconfig", "-o", str(_GRUB_CFG)],
        ]
        self._run_commands(commands)

    def _on_save_settings(self):
        timeout = self.timeout_spin.value()
        cmdline = self.cmdline_edit.text().strip()
        hide_menu = self.hide_menu_check.isChecked()
        disable_osprober = self.disable_osprober_check.isChecked()
        disable_submenu = self.disable_submenu_check.isChecked()
        gfxmode = self.gfxmode_combo.currentText().strip()
        bg_path = self.bg_edit.text().strip()

        sed_cmds = [
            f"sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT={timeout}/' {_GRUB_DEFAULT}",
        ]

        # CMDLINE
        if cmdline:
            escaped = cmdline.replace('"', '\\"')
            sed_cmds.append(
                f"sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT=\"{escaped}\"/' {_GRUB_DEFAULT}"
            )
        else:
            sed_cmds.append(
                f"sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT=\"\"/' {_GRUB_DEFAULT}"
            )

        # TIMEOUT_STYLE
        style_val = "hidden" if hide_menu else "menu"
        sed_cmds.append(
            f"sed -i 's/^#\\?GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE={style_val}/' {_GRUB_DEFAULT}"
        )

        # OS_PROBER
        osprober_val = "true" if disable_osprober else "false"
        sed_cmds.append(
            f"sed -i 's/^#\\?GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER={osprober_val}/' {_GRUB_DEFAULT}"
        )

        # SUBMENU
        submenu_val = "true" if disable_submenu else "false"
        sed_cmds.append(
            f"sed -i 's/^#\\?GRUB_DISABLE_SUBMENU=.*/GRUB_DISABLE_SUBMENU={submenu_val}/' {_GRUB_DEFAULT}"
        )

        # GFXMODE
        if gfxmode:
            sed_cmds.append(
                f"sed -i 's/^#\\?GRUB_GFXMODE=.*/GRUB_GFXMODE={gfxmode}/' {_GRUB_DEFAULT}"
            )
        else:
            sed_cmds.append(
                f"sed -i 's/^#\\?GRUB_GFXMODE=.*/#GRUB_GFXMODE=auto/' {_GRUB_DEFAULT}"
            )

        # BACKGROUND
        if bg_path:
            escaped_bg = bg_path.replace('"', '\\"')
            sed_cmds.append(
                f"sed -i 's|^#\\?GRUB_BACKGROUND=.*|GRUB_BACKGROUND=\"{escaped_bg}\"|' {_GRUB_DEFAULT}"
            )
        else:
            sed_cmds.append(
                f"sed -i 's|^#\\?GRUB_BACKGROUND=.*|#GRUB_BACKGROUND=|' {_GRUB_DEFAULT}"
            )

        commands = [["bash", "-c", cmd] for cmd in sed_cmds]
        commands.append(["grub-mkconfig", "-o", str(_GRUB_CFG)])

        self._run_commands(commands)

    def _run_commands(self, commands):
        self.setEnabled(False)
        self._worker = GrubActionWorker(commands, parent=self)
        self._worker.finished_ok.connect(self._on_cmd_ok)
        self._worker.failed.connect(self._on_cmd_failed)
        self._worker.start()

    def _on_cmd_ok(self, msg):
        self.setEnabled(True)
        if msg.strip():
            QMessageBox.information(self, "تم", msg[:500])
        self._reload()

    def _on_cmd_failed(self, err):
        self.setEnabled(True)
        QMessageBox.critical(self, "خطأ", err[:800])
        self._reload()
