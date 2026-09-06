#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/ssd_care_dialog.py — نافذة صيانة أقراص SSD.
مستوحاة من Abelssoft SSD Fresh لكن مبنية على آليات لينكس الحقيقية.

تعرض:
  • حالة TRIM (مفعّل/معطّل + آخر تشغيل)
  • جدولة I/O لكل قرص SSD
  • قيمة swappiness الحالية + توصية
  • خيارات fstab (noatime/relatime)
  • صحة S.M.A.R.T + الحرارة + مؤشر التآكل
  • حجم سجلات journald

أزرار الإجراء:
  • تفعيل TRIM الدوري
  • تشغيل TRIM فوري
  • ضبط swappiness إلى 15
  • تحديد حجم journald إلى 200M
  • عرض تقرير كامل

كل العمليات التي تحتاج root تمر عبر pkexec (run_privileged)
في خيط خلفي (QThread) لمنع تجمّد الواجهة.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QProgressBar, QTextEdit, QTabWidget, QWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger
from gui.workers import FunctionWorker

log = get_logger("ssd_care_dialog")


# ---------------------------------------------------------------------------
# Worker: ينفّذ دالة ssd_care في خيط خلفي
# ---------------------------------------------------------------------------

class SSDCareWorker(QThread):
    """خيط خلفي لتنفيذ عميات SSD care (TRIM, swappiness, journald, SMART)."""
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, action: str, parent=None):
        super().__init__(parent)
        self.action = action
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.action == "report":
                result = self._gather_report()
                self.finished_ok.emit(result)
            elif self.action == "enable_trim":
                r = run_privileged(["systemctl", "enable", "--now", "fstrim.timer"])
                self.finished_ok.emit({"action": "enable_trim", "ok": r.ok,
                                       "output": r.stdout + r.stderr})
            elif self.action == "trim_now":
                r = run_privileged(["fstrim", "-av"])
                self.finished_ok.emit({"action": "trim_now", "ok": r.ok,
                                       "output": r.stdout + r.stderr})
            elif self.action == "set_swappiness":
                r1 = run_privileged(["sysctl", "vm.swappiness=15"])
                r2 = run_privileged(["bash", "-c",
                    "echo 'vm.swappiness=15' > /etc/sysctl.d/99-ssd-care.conf"])
                self.finished_ok.emit({"action": "set_swappiness",
                                       "ok": r1.ok and r2.ok,
                                       "output": r1.stdout + r2.stdout})
            elif self.action == "limit_journald":
                r = run_privileged(["bash", "-c",
                    "mkdir -p /etc/systemd/journald.conf.d && "
                    "printf '[Journal]\\nSystemMaxUse=200M\\n' > "
                    "/etc/systemd/journald.conf.d/99-ssd-care.conf"])
                r2 = run_privileged(["systemctl", "restart", "systemd-journald"])
                self.finished_ok.emit({"action": "limit_journald",
                                       "ok": r.ok and r2.ok,
                                       "output": r.stdout + r2.stdout})
            elif self.action == "set_scheduler":
                # handled per-device in _on_set_scheduler
                self.finished_ok.emit({"action": "set_scheduler", "ok": True, "output": ""})
            else:
                self.failed.emit(f"إجراء غير معروف: {self.action}")
        except Exception as exc:
            log.exception("SSD care worker failed")
            self.failed.emit(str(exc))

    def _gather_report(self) -> dict:
        """يجمع كل المعلومات دون تعديل (قراءة فقط)."""
        import shutil as _sh

        report = {
            "trim": {},
            "swappiness": -1,
            "journald_storage": "",
            "fstab": {},
            "ssd_devices": [],
            "smart_available": _sh.which("smartctl") is not None,
        }

        # TRIM
        r = run_unprivileged(["systemctl", "is-enabled", "fstrim.timer"])
        report["trim"]["enabled"] = r.ok and "enabled" in r.stdout
        r2 = run_unprivileged(["systemctl", "is-active", "fstrim.timer"])
        report["trim"]["active"] = r2.ok and "active" in r2.stdout
        r3 = run_unprivileged(["systemctl", "status", "fstrim.timer"])
        for line in r3.stdout.splitlines():
            if "Trigger:" in line:
                report["trim"]["next_run"] = line.split("Trigger:")[-1].strip()

        # Swappiness
        r = run_unprivileged(["sysctl", "-n", "vm.swappiness"])
        try:
            report["swappiness"] = int(r.stdout.strip())
        except ValueError:
            pass

        # Journald
        try:
            with open("/etc/systemd/journald.conf") as f:
                for line in f:
                    if line.strip().startswith("Storage="):
                        report["journald_storage"] = line.split("=")[-1].strip()
        except (FileNotFoundError, PermissionError):
            pass
        if not report["journald_storage"]:
            report["journald_storage"] = "auto (افتراضي)"

        # fstab
        try:
            with open("/etc/fstab") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    mountpoint, options = parts[1], parts[3]
                    report["fstab"][mountpoint] = {
                        "options": options,
                        "noatime": "noatime" in options,
                        "relatime": "relatime" in options,
                    }
        except (FileNotFoundError, PermissionError):
            pass

        # SSD devices + scheduler + SMART
        r = run_unprivileged(["lsblk", "-d", "-n", "-o", "NAME"])
        for dev in r.stdout.split():
            if not dev:
                continue
            rot_path = f"/sys/block/{dev}/queue/rotational"
            try:
                with open(rot_path) as f:
                    is_ssd = f.read().strip() == "0"
            except (FileNotFoundError, PermissionError):
                continue
            if not is_ssd:
                continue

            dev_info = {"name": dev, "scheduler": None, "smart": None}

            # Scheduler
            sched_path = f"/sys/block/{dev}/queue/scheduler"
            try:
                with open(sched_path) as f:
                    content = f.read()
                for token in content.split():
                    if token.startswith("[") and token.endswith("]"):
                        dev_info["scheduler"] = token.strip("[]")
            except (FileNotFoundError, PermissionError):
                pass

            # SMART
            if report["smart_available"]:
                r_h = run_privileged(["smartctl", "-H", f"/dev/{dev}"])
                r_a = run_privileged(["smartctl", "-A", f"/dev/{dev}"])
                smart = {"health": None, "temp": None, "wear": None}
                smart["health"] = "PASSED" if "PASSED" in r_h.stdout or "OK" in r_h.stdout else "FAILED"
                for line in r_a.stdout.splitlines():
                    low = line.lower()
                    if "temperature" in low:
                        digits = [t for t in line.split() if t.isdigit()]
                        if digits:
                            smart["temp"] = int(digits[0])
                    if "wear_leveling" in low or "media_wearout" in low or "percent_lifetime" in low:
                        digits = [t for t in line.split() if t.isdigit()]
                        if digits:
                            smart["wear"] = digits[-1]
                dev_info["smart"] = smart

            report["ssd_devices"].append(dev_info)

        return report


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class SSDCareDialog(QDialog):
    """نافذة صيانة وتحسين أقراص SSD."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ صحة SSD — Manjaro Care")
        self.setMinimumSize(700, 600)
        self._worker: SSDCareWorker | None = None
        self._report: dict = {}

        self._build_ui()
        self._start_report()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("⚡ صيانة وتحسين أقراص SSD")
        title.setFont(QFont("Sans", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("المكافئ الوظيفي لـ SSD Fresh — مبني على آليات لينكس الحقيقية")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(subtitle)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_overview_tab(), "📊 نظرة عامة")
        tabs.addTab(self._build_devices_tab(), "💿 الأقراص")
        tabs.addTab(self._build_log_tab(), "📝 السجل")
        layout.addWidget(tabs)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Action buttons
        btn_row = QHBoxLayout()

        self.btn_enable_trim = QPushButton("🔧 تفعيل TRIM الدوري")
        self.btn_enable_trim.clicked.connect(lambda: self._run_action("enable_trim"))
        btn_row.addWidget(self.btn_enable_trim)

        self.btn_trim_now = QPushButton("⚡ تشغيل TRIM فوري")
        self.btn_trim_now.clicked.connect(lambda: self._run_action("trim_now"))
        btn_row.addWidget(self.btn_trim_now)

        self.btn_swappiness = QPushButton("🔽 خفض swappiness إلى 15")
        self.btn_swappiness.clicked.connect(lambda: self._run_action("set_swappiness"))
        btn_row.addWidget(self.btn_swappiness)

        self.btn_journald = QPushButton("📝 تحديد journald إلى 200M")
        self.btn_journald.clicked.connect(lambda: self._run_action("limit_journald"))
        btn_row.addWidget(self.btn_journald)

        self.btn_refresh = QPushButton("🔄 تحديث")
        self.btn_refresh.clicked.connect(self._start_report)
        btn_row.addWidget(self.btn_refresh)

        layout.addLayout(btn_row)

        # Close
        btn_close = QPushButton("إغلاق")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)

        self.lbl_trim_status = QLabel("جاري الفحص...")
        self.lbl_trim_next = QLabel("—")
        self.lbl_swappiness = QLabel("—")
        self.lbl_journald = QLabel("—")
        self.lbl_fstab = QLabel("—")
        self.lbl_smart_tool = QLabel("—")

        layout.addRow("TRIM الدوري:", self.lbl_trim_status)
        layout.addRow("القادم:", self.lbl_trim_next)
        layout.addRow("vm.swappiness:", self.lbl_swappiness)
        layout.addRow("Journald storage:", self.lbl_journald)
        layout.addRow("خيارات fstab:", self.lbl_fstab)
        layout.addRow("أداة S.M.A.R.T:", self.lbl_smart_tool)

        return tab

    def _build_devices_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.devices_table = QTableWidget(0, 5)
        self.devices_table.setHorizontalHeaderLabels(
            ["الجهاز", "الجدولة", "S.M.A.R.T", "الحرارة", "التآكل"]
        )
        header = self.devices_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        layout.addWidget(self.devices_table)

        # Set scheduler button
        self.btn_set_scheduler = QPushButton("⚙️ ضبط الجدولة إلى 'none' للقرص المحدد")
        self.btn_set_scheduler.clicked.connect(self._on_set_scheduler)
        layout.addWidget(self.btn_set_scheduler)

        return tab

    def _build_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Monospace", 10))
        layout.addWidget(self.log_view)
        return tab

    # ── Actions ──────────────────────────────────────────────────────────

    def _start_report(self):
        """يبدأ جمع التقرير في خيط خلفي."""
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # busy indicator
        self._set_buttons_enabled(False)

        self._worker = SSDCareWorker("report", self)
        self._worker.finished_ok.connect(self._on_report_ready)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _run_action(self, action: str):
        """يشغّل إجراءً يحتاج root في خيط خلفي."""
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._set_buttons_enabled(False)
        self._log(f"▶ بدء الإجراء: {action}")

        self._worker = SSDCareWorker(action, self)
        self._worker.finished_ok.connect(self._on_action_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_set_scheduler(self):
        """يضبط الجدولة إلى 'none' للجهاز المحدد في الجدول."""
        row = self.devices_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر قرضاً من الجدول أولاً.")
            return
        dev_item = self.devices_table.item(row, 0)
        if not dev_item:
            return
        dev = dev_item.text()
        r = run_privileged(["bash", "-c",
            f"echo none > /sys/block/{dev}/queue/scheduler"])
        if r.ok:
            self._log(f"✅ تم ضبط جدولة {dev} إلى 'none'")
            self.devices_table.item(row, 1).setText("none")
        else:
            self._log(f"❌ فشل ضبط جدولة {dev}: {r.stderr}")
            QMessageBox.warning(self, "فشل", f"تعذّر ضبط جدولة {dev}:\n{r.stderr}")

    # ── Callbacks ────────────────────────────────────────────────────────

    def _on_report_ready(self, report: dict):
        self._report = report
        self.progress.setVisible(False)
        self._set_buttons_enabled(True)
        self._populate_overview()
        self._populate_devices()
        self._log("✅ تم جمع التقرير بنجاح")

    def _on_action_done(self, result: dict):
        self.progress.setVisible(False)
        self._set_buttons_enabled(True)
        action = result.get("action", "?")
        ok = result.get("ok", False)
        output = result.get("output", "")
        status = "✅ نجح" if ok else "❌ فشل"
        self._log(f"{status}: {action}")
        if output.strip():
            self._log(output.strip())
        # Refresh report after action
        self._start_report()

    def _on_failed(self, error: str):
        self.progress.setVisible(False)
        self._set_buttons_enabled(True)
        self._log(f"❌ خطأ: {error}")
        QMessageBox.critical(self, "خطأ", error)

    # ── UI population ────────────────────────────────────────────────────

    def _populate_overview(self):
        r = self._report

        # TRIM
        trim = r.get("trim", {})
        if trim.get("enabled"):
            self.lbl_trim_status.setText("مفعّل ✅")
            self.lbl_trim_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_trim_status.setText("معطّل ❌")
            self.lbl_trim_status.setStyleSheet("color: red; font-weight: bold;")
        self.lbl_trim_next.setText(trim.get("next_run", "غير محدد"))

        # Swappiness
        sw = r.get("swappiness", -1)
        if 0 <= sw <= 30:
            self.lbl_swappiness.setText(f"{sw} ✅ (مثالي للـ SSD)")
            self.lbl_swappiness.setStyleSheet("color: green;")
        else:
            self.lbl_swappiness.setText(f"{sw} ⚠️ (يُفضّل خفضه إلى 10-20)")
            self.lbl_swappiness.setStyleSheet("color: orange;")

        # Journald
        js = r.get("journald_storage", "غير معروف")
        self.lbl_journald.setText(js)

        # fstab
        fstab = r.get("fstab", {})
        if fstab:
            lines = []
            for mp, info in fstab.items():
                if info["noatime"]:
                    lines.append(f"  {mp}: noatime ✅")
                elif info["relatime"]:
                    lines.append(f"  {mp}: relatime (مقبول)")
                else:
                    lines.append(f"  {mp}: بدون تحسين ⚠️")
            self.lbl_fstab.setText("\n".join(lines))
        else:
            self.lbl_fstab.setText("تعذّر قراءة fstab")

        # SMART tool
        if r.get("smart_available"):
            self.lbl_smart_tool.setText("متاح ✅ (smartmontools)")
            self.lbl_smart_tool.setStyleSheet("color: green;")
        else:
            self.lbl_smart_tool.setText("غير مثبّت — sudo pacman -S smartmontools")
            self.lbl_smart_tool.setStyleSheet("color: orange;")

    def _populate_devices(self):
        devices = self._report.get("ssd_devices", [])
        self.devices_table.setRowCount(len(devices))

        for i, dev in enumerate(devices):
            self.devices_table.setItem(i, 0, QTableWidgetItem(dev["name"]))

            sched = dev.get("scheduler", "غير معروف")
            sched_item = QTableWidgetItem(sched)
            if sched in ("none", "mq-deadline"):
                sched_item.setForeground(QColor("green"))
            else:
                sched_item.setForeground(QColor("orange"))
            self.devices_table.setItem(i, 1, sched_item)

            smart = dev.get("smart")
            if smart:
                health = smart.get("health", "غير معروف")
                health_item = QTableWidgetItem(f"{'سليم ✅' if health == 'PASSED' else 'تحذير ❌'}")
                health_item.setForeground(QColor("green") if health == "PASSED" else QColor("red"))
                self.devices_table.setItem(i, 2, health_item)

                temp = smart.get("temp")
                self.devices_table.setItem(i, 3, QTableWidgetItem(
                    f"{temp}°C" if temp is not None else "—"))

                wear = smart.get("wear")
                self.devices_table.setItem(i, 4, QTableWidgetItem(
                    f"{wear}%" if wear else "—"))
            else:
                self.devices_table.setItem(i, 2, QTableWidgetItem("غير متاح"))
                self.devices_table.setItem(i, 3, QTableWidgetItem("—"))
                self.devices_table.setItem(i, 4, QTableWidgetItem("—"))

    # ── Helpers ──────────────────────────────────────────────────────────

    def _set_buttons_enabled(self, enabled: bool):
        for btn in [self.btn_enable_trim, self.btn_trim_now,
                    self.btn_swappiness, self.btn_journald, self.btn_refresh,
                    self.btn_set_scheduler]:
            btn.setEnabled(enabled)

    def _log(self, msg: str):
        self.log_view.append(msg)
        log.info(msg)
