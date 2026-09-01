#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/oneclick_dialog.py — صيانة بنقرة واحدة (One-Click Maintenance).
مستوحاة من Glary Utilities 1-Click Maintenance.
"""
from __future__ import annotations
import shutil
from dataclasses import dataclass
from typing import Callable

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QTextEdit, QGroupBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("oneclick_dialog")


@dataclass
class MaintenanceTask:
    name: str
    description: str
    check_fn: Callable
    run_fn: Callable


class OneClickWorker(QThread):
    step_started = pyqtSignal(str, str)
    step_progress = pyqtSignal(int)
    step_done = pyqtSignal(str, bool, str)
    all_done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("صيانة بنقرة واحدة")
        self.resize(750, 600)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._build_ui()
        self._scan_tasks()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("صيانة بنقرة واحدة")
        f = title.font()
        f.setBold(True)
        f.setPointSize(14)
        title.setFont(f)
        layout.addWidget(title)

        info = QLabel("يقوم بفحص وتنظيف وتحسين النظام في خطوة واحدة.")
        info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info)

        self.main_progress = QProgressBar()
        self.main_progress.setRange(0, 100)
        self.main_progress.setValue(0)
        self.main_progress.setFormat("جاري الفحص...")
        layout.addWidget(self.main_progress)

        self.tasks_tree = QTreeWidget()
        self.tasks_tree.setHeaderLabels(["المهمة", "الحالة", "التفاصيل"])
        self.tasks_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tasks_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tasks_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tasks_tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.tasks_tree.setSelectionMode(QTreeWidget.NoSelection)
        layout.addWidget(self.tasks_tree)

        log_group = QGroupBox("سجل التنفيذ")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("فحص سريع")
        self.scan_btn.clicked.connect(self._scan_tasks)
        btn_row.addWidget(self.scan_btn)
        self.fix_btn = QPushButton("إصلاح الكل")
        self.fix_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; font-size: 12pt; padding: 8px;")
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
        layout.addLayout(btn_row)

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
                item.setText(1, "مطلوب")
                item.setForeground(1, Qt.red)
                item.setText(2, desc)
                issues_found += 1
            else:
                item.setText(1, "جيد")
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

    def _on_step_start(self, name, desc):
        self.main_progress.setFormat(f"جاري: {name}...")
        self.log_text.append(f"> {name}: {desc}")

    def _on_step_done(self, name, ok, log_text):
        item = self._task_items.get(name)
        if item:
            if ok:
                item.setText(1, "تم")
                item.setForeground(1, Qt.darkGreen)
            else:
                item.setText(1, "فشل")
                item.setForeground(1, Qt.red)
            item.setText(2, log_text[:80] + "..." if len(log_text) > 80 else log_text)
        self.log_text.append(f"{'OK' if ok else 'FAIL'} {name}: {log_text[:200]}")

    def _on_all_done(self, msg):
        self.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.fix_btn.setEnabled(True)
        self.main_progress.setFormat(msg)
        QMessageBox.information(self, "تم", f"{msg}\n\nراجع سجل التنفيذ للتفاصيل.")

    def _on_fail(self, err):
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

    def _check_orphans(self):
        r = run_unprivileged(["pacman", "-Qdtq"])
        return r.ok and bool(r.stdout.strip())

    def _check_journal(self):
        r = run_unprivileged(["journalctl", "--disk-usage"])
        if not r.ok: return False
        if "M" in r.stdout:
            try:
                size_str = r.stdout.split()[0]
                size = float(size_str.replace("M", ""))
                return size > 500
            except ValueError: pass
        return False

    def _check_paccache(self):
        if not shutil.which("paccache"): return False
        r = run_unprivileged(["paccache", "-dk2"])
        return r.ok and "candidate" in r.stdout.lower()

    def _check_flatpak(self):
        if not shutil.which("flatpak"): return False
        r = run_unprivileged(["flatpak", "unused"])
        return r.ok and bool(r.stdout.strip())

    def _check_fstrim(self):
        r = run_unprivileged(["findmnt", "-n", "-o", "FSTYPE", "/"])
        return r.ok and r.stdout.strip() in ("ext4", "btrfs", "xfs")

    def _check_sync(self): return True

    def _check_tmp(self):
        from pathlib import Path
        tmp = Path("/tmp")
        if not tmp.exists(): return False
        count = sum(1 for _ in tmp.iterdir() if _.is_file())
        return count > 50

    def _fix_orphans(self):
        r = run_privileged(["bash", "-c", "pacman -Rns $(pacman -Qdtq) --noconfirm 2>/dev/null || true"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_journal(self):
        r = run_privileged(["journalctl", "--vacuum-time=7d"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_paccache(self):
        if not shutil.which("paccache"): return False, "paccache غير مثبت"
        r = run_privileged(["paccache", "-rk2"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_flatpak(self):
        if not shutil.which("flatpak"): return False, "flatpak غير مثبت"
        r = run_privileged(["flatpak", "uninstall", "--unused", "-y"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_fstrim(self):
        r = run_privileged(["fstrim", "-av", "/"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_sync(self):
        r = run_privileged(["pacman", "-Sy"])
        return r.ok, r.stdout[:200] or "تم"

    def _fix_tmp(self):
        r = run_privileged(["bash", "-c", "find /tmp -type f -atime +3 -delete 2>/dev/null || true"])
        return True, "تم تنظيف /tmp"
