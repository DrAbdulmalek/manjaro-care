#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/game_mode_dialog.py — وضع الألعاب (مستوحى من Razer Cortex + ASC Turbo Boost).
يقوم بتعليق العمليات غير الضرورية، تفعيل gamemode، وتغيير governor إلى performance.
"""
from __future__ import annotations
import shutil
import psutil

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGroupBox, QCheckBox, QProgressBar, QTextEdit,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("game_mode_dialog")


class GameModeWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, enable: bool, suspend_apps: list[str] = None, parent=None):
        super().__init__(parent)
        self.enable = enable
        self.suspend_apps = suspend_apps or []

    def run(self):
        try:
            if self.enable:
                self.progress.emit("تفعيل GameMode...")
                # 1. تفعيل gamemode إن وجد
                if shutil.which("gamemoded"):
                    run_privileged(["systemctl", "start", "gamemoded"])
                    run_privileged(["gamemoderun", "echo", "gamemode active"])
                    self.progress.emit("✅ GameMode Daemon نشط")

                # 2. تغيير CPU governor إلى performance
                run_privileged(["bash", "-c", "cpupower frequency-set -g performance 2>/dev/null || echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null"])

                # 3. تقليل swappiness
                run_privileged(["sysctl", "vm.swappiness=10"])

                # 4. تعليق العمليات المحددة (SIGSTOP)
                for proc_name in self.suspend_apps:
                    self.progress.emit(f"⏸️ تعليق {proc_name}...")
                    run_privileged(["bash", "-c", f"pkill -STOP -x {proc_name} 2>/dev/null; true"])

                self.finished_ok.emit("🎮 وضع الألعاب مفعّل!\nCPU: performance | Swappiness: 10 | العمليات المحددة موقفة.")
            else:
                self.progress.emit("إيقاف وضع الألعاب...")
                # إرجاع الإعدادات
                run_privileged(["bash", "-c", "cpupower frequency-set -g ondemand 2>/dev/null || echo ondemand | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null"])
                run_privileged(["sysctl", "vm.swappiness=60"])

                # استئناف العمليات (SIGCONT)
                for proc_name in self.suspend_apps:
                    run_privileged(["bash", "-c", f"pkill -CONT -x {proc_name} 2>/dev/null; true"])

                if shutil.which("gamemoded"):
                    run_privileged(["systemctl", "stop", "gamemoded"])

                self.finished_ok.emit("✅ تم إيقاف وضع الألعاب واستعادة الإعدادات.")
        except Exception as exc:
            self.failed.emit(str(exc))


class GameModeDialog(QDialog):
    # العمليات الشائعة التي يمكن تعليقها أثناء اللعب
    DEFAULT_SUSPENDABLE = [
        ("firefox", "Firefox 🦊"),
        ("chromium", "Chromium 🌐"),
        ("chrome", "Chrome 🌐"),
        ("thunderbird", "Thunderbird 📧"),
        ("discord", "Discord 💬"),
        ("telegram-desktop", "Telegram 📱"),
        ("spotify", "Spotify 🎵"),
        ("dropbox", "Dropbox ☁️"),
        ("nextcloud", "NextCloud ☁️"),
        ("syncthing", "Syncthing 🔄"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎮 وضع الألعاب (Game Mode)")
        self.resize(600, 500)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._is_active = False
        self._build_ui()
        self._check_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🎮 وضع الألعاب — Turbo Boost")
        f = title.font()
        f.setBold(True)
        f.setPointSize(14)
        title.setFont(f)
        layout.addWidget(title)

        info = QLabel("يقوم هذا الوضع بتعليق العمليات غير الضرورية، تفعيل GameMode،\nوتغيير معالج CPU إلى وضع الأداء الأقصى.")
        info.setStyleSheet("color: #aaaaaa;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # حالة النظام
        status_group = QGroupBox("حالة النظام الحالية")
        status_layout = QVBoxLayout(status_group)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(80)
        status_layout.addWidget(self.status_text)
        layout.addWidget(status_group)

        # جدول العمليات القابلة للتعليق
        proc_group = QGroupBox("العمليات التي سيتم تعليقها أثناء اللعب")
        proc_layout = QVBoxLayout(proc_group)

        self.proc_table = QTableWidget(0, 2)
        self.proc_table.setHorizontalHeaderLabels(["", "التطبيق"])
        self.proc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.proc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.proc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.proc_table.setSelectionMode(QTableWidget.NoSelection)

        for row, (proc_name, display_name) in enumerate(self.DEFAULT_SUSPENDABLE):
            self.proc_table.insertRow(row)
            chk = QCheckBox()
            chk.setChecked(True)
            # تحقق مما إذا كان التطبيق يعمل حالياً
            running = any(p.name() == proc_name for p in psutil.process_iter(['name']))
            if not running:
                display_name += " (غير نشط)"
                chk.setEnabled(False)

            self.proc_table.setCellWidget(row, 0, chk)
            self.proc_table.setItem(row, 1, QTableWidgetItem(display_name))
            # تخزين اسم العملية
            self.proc_table.item(row, 1).setData(Qt.UserRole, proc_name)

        proc_layout.addWidget(self.proc_table)
        layout.addWidget(proc_group)

        # شريط التقدم
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # الأزرار
        btn_row = QHBoxLayout()

        self.toggle_btn = QPushButton("🚀 تفعيل وضع الألعاب")
        self.toggle_btn.setStyleSheet("background-color: #1565c0; color: white; font-weight: bold; font-size: 12pt; padding: 10px;")
        self.toggle_btn.clicked.connect(self._toggle_game_mode)
        btn_row.addWidget(self.toggle_btn)

        btn_row.addStretch()

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _check_status(self):
        # التحقق من حالة gamemoded
        r = run_unprivileged(["systemctl", "is-active", "gamemoded"])
        self._is_active = r.ok and "active" in r.stdout

        # CPU governor
        gov_r = run_unprivileged(["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"])
        governor = gov_r.stdout.strip() if gov_r.ok else "غير معروف"

        status = f"GameMode: {'🟢 نشط' if self._is_active else '🔴 متوقف'} | CPU Governor: {governor}"
        self.status_text.setPlainText(status)

        if self._is_active:
            self.toggle_btn.setText("⏹️ إيقاف وضع الألعاب")
            self.toggle_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold; font-size: 12pt; padding: 10px;")
        else:
            self.toggle_btn.setText("🚀 تفعيل وضع الألعاب")
            self.toggle_btn.setStyleSheet("background-color: #1565c0; color: white; font-weight: bold; font-size: 12pt; padding: 10px;")

    def _toggle_game_mode(self):
        if self._is_active:
            # إيقاف
            selected = self._get_selected_procs()
            self._run_worker(enable=False, suspend_apps=selected)
        else:
            # تفعيل
            selected = self._get_selected_procs()
            if not selected:
                reply = QMessageBox.question(
                    self, "تنبيه",
                    "لم تختر أي عمليات للتعليق. هل تريد المتابعة؟",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
            self._run_worker(enable=True, suspend_apps=selected)

    def _get_selected_procs(self) -> list[str]:
        selected = []
        for row in range(self.proc_table.rowCount()):
            w = self.proc_table.cellWidget(row, 0)
            if isinstance(w, QCheckBox) and w.isChecked() and w.isEnabled():
                proc_name = self.proc_table.item(row, 1).data(Qt.UserRole)
                selected.append(proc_name)
        return selected

    def _run_worker(self, enable: bool, suspend_apps: list[str]):
        self.setEnabled(False)
        self.progress.setVisible(True)
        self._worker = GameModeWorker(enable, suspend_apps, parent=self)
        self._worker.progress.connect(lambda msg: self.progress.setFormat(msg))
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, msg):
        self.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.information(self, "تم", msg)
        self._check_status()

    def _on_fail(self, err):
        self.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "خطأ", err)
        self._check_status()
