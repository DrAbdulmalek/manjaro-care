#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/oneclick_dialog.py — صيانة بنقرة واحدة (One-Click Maintenance).
مستوحاة من Glary Utilities 1-Click Maintenance.
⏰ يدعم الجدولة التلقائية عبر systemd timer.
"""
from __future__ import annotations
import shutil
import re
from dataclasses import dataclass
from typing import Callable

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QTextEdit, QGroupBox, QFormLayout,
    QComboBox, QSpinBox, QCheckBox, QTimeEdit, QTabWidget,
    QWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTime

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("oneclick_dialog")


@dataclass
class MaintenanceTask:
    name: str
    description: str
    check_fn: Callable[[], bool]
    run_fn: Callable[[], tuple[bool, str]]


class OneClickWorker(QThread):
    step_started = pyqtSignal(str, str)
    step_progress = pyqtSignal(int)
    step_done = pyqtSignal(str, bool, str)
    all_done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, tasks: list[MaintenanceTask], parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        logs = []
        completed = 0

        for task in self.tasks:
            if self._cancelled:
                self.step_done.emit(task.name, False, "تم الإلغاء.")
                break

            self.step_started.emit(task.name, task.description)
            try:
                ok, log_text = task.run_fn()
                self.step_done.emit(task.name, ok, log_text)
                if ok:
                    completed += 1
            except Exception as exc:
                self.step_done.emit(task.name, False, str(exc))

            pct = int((self.tasks.index(task) + 1) / len(self.tasks) * 100)
            self.step_progress.emit(pct)

        self.all_done.emit(f"تم إنجاز {completed}/{len(self.tasks)} مهمة.")


class OneClickMaintenanceDialog(QDialog):
    TIMER_NAME = "manjaro-care-oneclick"
    TIMER_PATH = f"/etc/systemd/system/{TIMER_NAME}.timer"
    SERVICE_PATH = f"/etc/systemd/system/{TIMER_NAME}.service"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("صيانة بنقرة واحدة ⚡")
        self.resize(800, 700)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._build_ui()
        self._scan_tasks()
        self._load_schedule()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("⚡ صيانة بنقرة واحدة")
        f = title.font()
        f.setBold(True)
        f.setPointSize(14)
        title.setFont(f)
        layout.addWidget(title)

        info = QLabel("يقوم بفحص وتنظيف وتحسين النظام في خطوة واحدة.")
        info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info)

        # تبويبات
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ── تبويب الصيانة ──
        maint_tab = QWidget()
        maint_layout = QVBoxLayout(maint_tab)

        self.main_progress = QProgressBar()
        self.main_progress.setRange(0, 100)
        self.main_progress.setValue(0)
        self.main_progress.setFormat("جاري الفحص...")
        maint_layout.addWidget(self.main_progress)

        self.tasks_tree = QTreeWidget()
        self.tasks_tree.setHeaderLabels(["المهمة", "الحالة", "التفاصيل"])
        self.tasks_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tasks_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tasks_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tasks_tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.tasks_tree.setSelectionMode(QTreeWidget.NoSelection)
        maint_layout.addWidget(self.tasks_tree)

        log_group = QGroupBox("سجل التنفيذ")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        log_layout.addWidget(self.log_text)
        maint_layout.addWidget(log_group)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("🔍 فحص سريع")
        self.scan_btn.clicked.connect(self._scan_tasks)
        btn_row.addWidget(self.scan_btn)

        self.fix_btn = QPushButton("⚡ إصلاح الكل")
        self.fix_btn.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; font-size: 12pt; padding: 8px;"
        )
        self.fix_btn.clicked.connect(self._run_maintenance)
        btn_row.addWidget(self.fix_btn)

        self.cancel_btn = QPushButton("إيقاف")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.cancel_btn)

        btn_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        maint_layout.addLayout(btn_row)

        self.tabs.addTab(maint_tab, "الصيانة")

        # ── تبويب الجدولة ⏰ ──
        sched_tab = QWidget()
        sched_layout = QVBoxLayout(sched_tab)

        sched_info = QLabel("⏰ جدولة الصيانة التلقائية عبر systemd timer")
        sched_info.setStyleSheet("color: #1565c0; font-size: 11pt;")
        sched_layout.addWidget(sched_info)

        sched_form = QFormLayout()

        self.sched_enable = QCheckBox("تفعيل الجدولة التلقائية")
        self.sched_enable.stateChanged.connect(self._toggle_schedule)
        sched_form.addRow(self.sched_enable)

        self.sched_freq = QComboBox()
        self.sched_freq.addItems(["يومياً", "أسبوعياً", "شهرياً"])
        self.sched_freq.setEnabled(False)
        sched_form.addRow("التكرار:", self.sched_freq)

        self.sched_time = QTimeEdit()
        self.sched_time.setTime(QTime(3, 0))
        self.sched_time.setEnabled(False)
        sched_form.addRow("الوقت:", self.sched_time)

        self.sched_day = QComboBox()
        self.sched_day.addItems([
            "الأحد", "الإثنين", "الثلاثاء", "الأربعاء",
            "الخميس", "الجمعة", "السبت",
        ])
        self.sched_day.setEnabled(False)
        self.sched_day.setVisible(False)
        sched_form.addRow("اليوم (للأسبوعي):", self.sched_day)

        self.sched_freq.currentTextChanged.connect(self._on_freq_changed)

        sched_layout.addLayout(sched_form)

        # حالة الجدولة الحالية
        self.sched_status = QLabel("الحالة: غير معروفة")
        self.sched_status.setStyleSheet("padding: 10px; background: #1e1e1e; border-radius: 4px;")
        sched_layout.addWidget(self.sched_status)

        sched_btns = QHBoxLayout()
        self.save_sched_btn = QPushButton("💾 حفظ الجدولة")
        self.save_sched_btn.setStyleSheet("background-color: #1565c0; color: white;")
        self.save_sched_btn.clicked.connect(self._save_schedule)
        self.save_sched_btn.setEnabled(False)
        sched_btns.addWidget(self.save_sched_btn)

        self.remove_sched_btn = QPushButton("🗑️ إلغاء الجدولة")
        self.remove_sched_btn.setStyleSheet("background-color: #c62828; color: white;")
        self.remove_sched_btn.clicked.connect(self._remove_schedule)
        sched_btns.addWidget(self.remove_sched_btn)

        sched_btns.addStretch()
        sched_layout.addLayout(sched_btns)
        sched_layout.addStretch()

        self.tabs.addTab(sched_tab, "⏰ الجدولة")

    def _on_freq_changed(self, text):
        self.sched_day.setVisible(text == "أسبوعياً")

    def _toggle_schedule(self, state):
        enabled = state == Qt.Checked
        self.sched_freq.setEnabled(enabled)
        self.sched_time.setEnabled(enabled)
        if self.sched_freq.currentText() == "أسبوعياً":
            self.sched_day.setEnabled(enabled)
            self.sched_day.setVisible(enabled)
        self.save_sched_btn.setEnabled(enabled)

    def _load_schedule(self):
        r = run_unprivileged(["systemctl", "is-enabled", self.TIMER_NAME])
        is_enabled = r.ok and "enabled" in r.stdout

        r2 = run_unprivileged(["cat", self.TIMER_PATH])
        timer_content = r2.stdout if r2.ok else ""

        if is_enabled:
            self.sched_enable.setChecked(True)
            self.sched_status.setText("✅ الجدولة مفعّلة\n" + timer_content[:300])
            self._parse_timer_content(timer_content)
        else:
            self.sched_status.setText("🔴 لا توجد جدولة.\nانقر «حفظ الجدولة» لتفعيلها.")

    def _parse_timer_content(self, content: str):
        if "OnCalendar=daily" in content:
            self.sched_freq.setCurrentText("يومياً")
        elif "OnCalendar=weekly" in content:
            self.sched_freq.setCurrentText("أسبوعياً")
        elif "OnCalendar=monthly" in content:
            self.sched_freq.setCurrentText("شهرياً")

        # استخراج الوقت
        m = re.search(r"OnCalendar=.*?(\d{2}):(\d{2})", content)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            self.sched_time.setTime(QTime(hour, minute))

    def _save_schedule(self):
        freq = self.sched_freq.currentText()
        time = self.sched_time.time()
        time_str = f"{time.hour():02d}:{time.minute():02d}:00"

        if freq == "يومياً":
            calendar = f"*-*-* {time_str}"
        elif freq == "أسبوعياً":
            day_map = {
                "الأحد": "Sun", "الإثنين": "Mon", "الثلاثاء": "Tue",
                "الأربعاء": "Wed", "الخميس": "Thu", "الجمعة": "Fri", "السبت": "Sat",
            }
            day = day_map.get(self.sched_day.currentText(), "Sun")
            calendar = f"{day} *-*-* {time_str}"
        else:  # شهرياً
            calendar = f"*-*-01 {time_str}"

        # محتوى الـ timer
        timer_content = f"""[Unit]
Description=Manjaro Care — One-Click Maintenance
[Timer]
OnCalendar={calendar}
Persistent=true
[Install]
WantedBy=timers.target
"""

        # محتوى الـ service
        service_content = f"""[Unit]
Description=Manjaro Care One-Click Maintenance
[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 -m manjaro_care --oneclick
"""

        # كتابة الملفات
        r1 = run_privileged(["bash", "-c", f"cat > {self.TIMER_PATH} << 'EOF'\n{timer_content}EOF"])
        r2 = run_privileged(["bash", "-c", f"cat > {self.SERVICE_PATH} << 'EOF'\n{service_content}EOF"])

        if not (r1.ok and r2.ok):
            QMessageBox.critical(self, "خطأ", "فشل كتابة ملفات systemd.")
            return

        r3 = run_privileged(["systemctl", "daemon-reload"])
        r4 = run_privileged(["systemctl", "enable", "--now", self.TIMER_NAME])

        if r4.ok:
            QMessageBox.information(self, "تم", f"✅ تم حفظ الجدولة: {freq} في {time_str[:5]}")
            self._load_schedule()
        else:
            QMessageBox.critical(self, "خطأ", f"فشل تفعيل الجدولة:\n{r4.stderr}")

    def _remove_schedule(self):
        reply = QMessageBox.question(
            self, "تأكيد",
            "هل تريد إلغاء الجدولة التلقائية؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        r1 = run_privileged(["systemctl", "disable", "--now", self.TIMER_NAME])
        r2 = run_privileged(["rm", "-f", self.TIMER_PATH, self.SERVICE_PATH])
        r3 = run_privileged(["systemctl", "daemon-reload"])

        if r3.ok:
            self.sched_enable.setChecked(False)
            self._load_schedule()
            QMessageBox.information(self, "تم", "🔴 تم إلغاء الجدولة.")
        else:
            QMessageBox.critical(self, "خطأ", "فشل إلغاء الجدولة.")

    def _scan_tasks(self):
        self.tasks_tree.clear()
        self._task_items = {}

        tasks_defs = self._get_task_definitions()
        issues_found = 0

        for name, desc, check_fn, _ in tasks_defs:
            needed = check_fn()
            item = QTreeWidgetItem()
            item.setText(0, name)
            item.setCheckState(0, Qt.Checked if needed else Qt.Unchecked)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

            if needed:
                item.setText(1, "⚠️ مطلوب")
                item.setForeground(1, Qt.red)
                item.setText(2, desc)
                issues_found += 1
            else:
                item.setText(1, "✅ جيد")
                item.setForeground(1, Qt.darkGreen)
                item.setText(2, "لا يوجد مشكلة.")

            self.tasks_tree.addTopLevelItem(item)
            self._task_items[name] = item

        self.main_progress.setValue(100)
        self.main_progress.setFormat(f"فحص مكتمل — {issues_found} مشكلة/مشاكل")

    def _run_maintenance(self):
        selected_tasks = []
        for name, item in self._task_items.items():
            if item.checkState(0) == Qt.Checked:
                for t in self._get_task_definitions():
                    if t[0] == name:
                        selected_tasks.append(MaintenanceTask(name=t[0], description=t[1], check_fn=t[2], run_fn=t[3]))
                        break

        if not selected_tasks:
            QMessageBox.information(self, "تنبيه", "لا توجد مهام محددة.")
            return

        self.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.fix_btn.setEnabled(False)
        self.main_progress.setValue(0)
        self.log_text.clear()

        self._worker = OneClickWorker(selected_tasks, parent=self)
        self._worker.step_started.connect(self._on_step_start)
        self._worker.step_progress.connect(self.main_progress.setValue)
        self._worker.step_done.connect(self._on_step_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_step_start(self, name: str, desc: str):
        self.main_progress.setFormat(f"جاري: {name}...")
        self.log_text.append(f"▶️ {name}: {desc}")

    def _on_step_done(self, name: str, ok: bool, log: str):
        item = self._task_items.get(name)
        if item:
            if ok:
                item.setText(1, "✅ تم")
                item.setForeground(1, Qt.darkGreen)
            else:
                item.setText(1, "❌ فشل")
                item.setForeground(1, Qt.red)
            item.setText(2, log[:80] + "..." if len(log) > 80 else log)
        icon = "✅" if ok else "❌"
        self.log_text.append(f"{icon} {name}: {log[:200]}")

    def _on_all_done(self, msg: str):
        self.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.fix_btn.setEnabled(True)
        self.main_progress.setFormat(msg)
        QMessageBox.information(self, "تم", f"✅ {msg}\n\nراجع سجل التنفيذ للتفاصيل.")

    def _on_fail(self, err: str):
        self.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.fix_btn.setEnabled(True)
        QMessageBox.critical(self, "خطأ", err)

    def _cancel(self):
        if self._worker:
            self._worker.cancel()

    def _get_task_definitions(self):
        return [
            ("الحزم اليتيمة", "حذف الحزم التي لا حاجة لها", self._check_orphans, self._fix_orphans),
            ("تقليص سجلات Journal", "تقليص سجلات systemd إلى 7 أيام", self._check_journal, self._fix_journal),
            ("تنظيف ذاكرة pacman", "حذف إصدارات الحزم القديمة من cache", self._check_paccache, self._fix_paccache),
            ("تنظيف Flatpak", "حذف runtime غير المستخدم", self._check_flatpak, self._fix_flatpak),
            ("fstrim", "تحسين أداء SSD", self._check_fstrim, self._fix_fstrim),
            ("تحديث قاعدة البيانات", "مزامنة مستودعات pacman", self._check_sync, self._fix_sync),
            ("تنظيف /tmp", "حذف الملفات المؤقتة القديمة", self._check_tmp, self._fix_tmp),
        ]

    # ─── فحص ───
    def _check_orphans(self) -> bool:
        r = run_unprivileged(["pacman", "-Qdtq"])
        return r.ok and bool(r.stdout.strip())

    def _check_journal(self) -> bool:
        r = run_unprivileged(["journalctl", "--disk-usage"])
        if not r.ok:
            return False
        if "M" in r.stdout:
            try:
                size = float(r.stdout.split()[0].replace("M", ""))
                return size > 500
            except ValueError:
                pass
        return False

    def _check_paccache(self) -> bool:
        if not shutil.which("paccache"):
            return False
        r = run_unprivileged(["paccache", "-dk2"])
        return r.ok and "candidate" in r.stdout.lower()

    def _check_flatpak(self) -> bool:
        if not shutil.which("flatpak"):
            return False
        r = run_unprivileged(["flatpak", "unused"])
        return r.ok and bool(r.stdout.strip())

    def _check_fstrim(self) -> bool:
        r = run_unprivileged(["findmnt", "-n", "-o", "FSTYPE", "/"])
        return r.ok and r.stdout.strip() in ("ext4", "btrfs", "xfs")

    def _check_sync(self) -> bool:
        return True

    def _check_tmp(self) -> bool:
        import os
        tmp = Path("/tmp")
        if not tmp.exists():
            return False
        return sum(1 for _ in tmp.iterdir() if _.is_file()) > 50

    # ─── إصلاح ───
    def _fix_orphans(self) -> tuple[bool, str]:
        r = run_privileged(["bash", "-c", "pacman -Rns $(pacman -Qdtq) --noconfirm 2>/dev/null || true"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_journal(self) -> tuple[bool, str]:
        r = run_privileged(["journalctl", "--vacuum-time=7d"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_paccache(self) -> tuple[bool, str]:
        if not shutil.which("paccache"):
            return False, "paccache غير مثبت"
        r = run_privileged(["paccache", "-rk2"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_flatpak(self) -> tuple[bool, str]:
        if not shutil.which("flatpak"):
            return False, "flatpak غير مثبت"
        r = run_privileged(["flatpak", "uninstall", "--unused", "-y"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_fstrim(self) -> tuple[bool, str]:
        r = run_privileged(["fstrim", "-av", "/"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_sync(self) -> tuple[bool, str]:
        r = run_privileged(["pacman", "-Sy"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_tmp(self) -> tuple[bool, str]:
        r = run_privileged(["bash", "-c", "find /tmp -type f -atime +3 -delete 2>/dev/null || true"])
        return True, "تم تنظيف /tmp"
