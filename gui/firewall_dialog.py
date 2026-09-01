#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/firewall_dialog.py — نافذة مخصصة لإدارة الجدار الناري (firewalld/ufw).
"""
from __future__ import annotations
import shutil
import re

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QCheckBox, QMessageBox,
    QHeaderView, QLineEdit, QComboBox, QGroupBox, QTabWidget,
    QWidget, QFormLayout,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("firewall_dialog")


class FirewallActionWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command

    def run(self):
        try:
            result = run_privileged(self.command)
            if result.ok:
                self.finished_ok.emit(result.stdout or "تم التنفيذ بنجاح.")
            else:
                self.failed.emit(f"فشل (كود {result.returncode}): {result.stderr}")
        except Exception as exc:
            self.failed.emit(str(exc))


class FirewallManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة الجدار الناري")
        self.resize(640, 520)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self.fw_type = self._detect_firewall()
        self._build_ui()
        self._reload()

    def _detect_firewall(self):
        if shutil.which("firewall-cmd"):
            return "firewalld"
        if shutil.which("ufw"):
            return "ufw"
        return None

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel(f"الجدار الناري المكتشف: {self.fw_type or 'غير مثبت'}")
        f = title.font(); f.setBold(True); f.setPointSize(12); title.setFont(f)
        layout.addWidget(title)

        if not self.fw_type:
            info = QLabel("لا يوجد جدار ناري مثبت.\nثبّت firewalld أو ufw إن أردت حماية إضافية.")
            info.setStyleSheet("color: #aaaaaa;")
            layout.addWidget(info)
            close_btn = QPushButton("إغلاق")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)
            return

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        if self.fw_type == "firewalld":
            self._build_firewalld_tabs()
        else:
            self._build_ufw_tab()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self._reload)
        btn_row.addWidget(refresh_btn)
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_firewalld_tabs(self):
        # تبويب الحالة
        status_tab = QWidget()
        st_layout = QVBoxLayout(status_tab)
        self.fw_status_label = QLabel("")
        self.fw_status_label.setStyleSheet("font-size: 11pt; padding: 8px;")
        st_layout.addWidget(self.fw_status_label)

        svc_row = QHBoxLayout()
        self.start_fw_btn = QPushButton("تشغيل firewalld")
        self.start_fw_btn.setStyleSheet("background-color: #2e7d32;")
        self.start_fw_btn.clicked.connect(lambda: self._run_cmd(["systemctl", "start", "firewalld"]))
        svc_row.addWidget(self.start_fw_btn)

        self.stop_fw_btn = QPushButton("إيقاف firewalld")
        self.stop_fw_btn.setStyleSheet("background-color: #c62828;")
        self.stop_fw_btn.clicked.connect(lambda: self._run_cmd(["systemctl", "stop", "firewalld"]))
        svc_row.addWidget(self.stop_fw_btn)

        self.enable_fw_btn = QPushButton("تفعيل عند الإقلاع")
        self.enable_fw_btn.clicked.connect(lambda: self._run_cmd(["systemctl", "enable", "firewalld"]))
        svc_row.addWidget(self.enable_fw_btn)
        svc_row.addStretch()
        st_layout.addLayout(svc_row)
        st_layout.addStretch()
        self.tabs.addTab(status_tab, "الحالة")

        # تبويب Zones
        zones_tab = QWidget()
        z_layout = QVBoxLayout(zones_tab)
        z_info = QLabel("المناطق (Zones) النشطة — يمكنك تفعيل/تعطيل كل منطقة:")
        z_info.setStyleSheet("color: #aaaaaa;")
        z_layout.addWidget(z_info)

        self.zones_table = QTableWidget(0, 3)
        self.zones_table.setHorizontalHeaderLabels(["المنطقة", "الواجهات", "الحالة"])
        self.zones_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.zones_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.zones_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.zones_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.zones_table.setSelectionMode(QTableWidget.NoSelection)
        z_layout.addWidget(self.zones_table)
        self.tabs.addTab(zones_tab, "المناطق")

        # تبويب Ports & Services
        ports_tab = QWidget()
        p_layout = QVBoxLayout(ports_tab)

        svc_group = QGroupBox("Services المفعّلة")
        svc_layout = QVBoxLayout(svc_group)
        self.services_label = QLabel("")
        self.services_label.setWordWrap(True)
        self.services_label.setStyleSheet("color: #cfcfcf; font-family: monospace;")
        svc_layout.addWidget(self.services_label)
        p_layout.addWidget(svc_group)

        ports_group = QGroupBox("Ports المفتوحة")
        ports_layout = QVBoxLayout(ports_group)
        self.ports_label = QLabel("")
        self.ports_label.setWordWrap(True)
        self.ports_label.setStyleSheet("color: #cfcfcf; font-family: monospace;")
        ports_layout.addWidget(self.ports_label)
        p_layout.addWidget(ports_group)

        add_group = QGroupBox("إضافة Port / Service")
        add_layout = QFormLayout(add_group)
        self.add_type_combo = QComboBox()
        self.add_type_combo.addItems(["port", "service"])
        add_layout.addRow("النوع:", self.add_type_combo)
        self.add_value_input = QLineEdit()
        self.add_value_input.setPlaceholderText("مثال: 8080/tcp أو http")
        add_layout.addRow("القيمة:", self.add_value_input)
        self.add_zone_combo = QComboBox()
        add_layout.addRow("المنطقة:", self.add_zone_combo)
        add_btn = QPushButton("إضافة")
        add_btn.setStyleSheet("background-color: #1565c0;")
        add_btn.clicked.connect(self._on_add_port)
        add_layout.addRow(add_btn)
        p_layout.addWidget(add_group)
        p_layout.addStretch()
        self.tabs.addTab(ports_tab, "Ports & Services")

    def _build_ufw_tab(self):
        ufw_tab = QWidget()
        u_layout = QVBoxLayout(ufw_tab)
        self.ufw_status_label = QLabel("")
        self.ufw_status_label.setStyleSheet("font-size: 11pt; padding: 8px;")
        u_layout.addWidget(self.ufw_status_label)

        btn_row = QHBoxLayout()
        enable_btn = QPushButton("تفعيل ufw")
        enable_btn.setStyleSheet("background-color: #2e7d32;")
        enable_btn.clicked.connect(lambda: self._run_cmd(["ufw", "--force", "enable"]))
        btn_row.addWidget(enable_btn)

        disable_btn = QPushButton("تعطيل ufw")
        disable_btn.setStyleSheet("background-color: #c62828;")
        disable_btn.clicked.connect(lambda: self._run_cmd(["ufw", "--force", "disable"]))
        btn_row.addWidget(disable_btn)

        reset_btn = QPushButton("إعادة ضبط ufw")
        reset_btn.clicked.connect(lambda: self._run_cmd(["ufw", "--force", "reset"]))
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        u_layout.addLayout(btn_row)
        u_layout.addStretch()
        self.tabs.addTab(ufw_tab, "ufw")

    def _reload(self):
        if not self.fw_type:
            return
        if self.fw_type == "firewalld":
            self._reload_firewalld()
        else:
            self._reload_ufw()

    def _reload_firewalld(self):
        r = run_unprivileged(["systemctl", "is-active", "firewalld"])
        active = r.ok and r.stdout.strip() == "active"
        self.fw_status_label.setText(
            f"الحالة: {'<span style=\"color:#2e7d32;\">نشط</span>' if active else '<span style=\"color:#c62828;\">متوقف</span>'}"
        )

        zones_result = run_unprivileged(["firewall-cmd", "--get-active-zones"])
        active_zones = {}
        current_zone = None
        for line in zones_result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("interfaces:") and not line.startswith("sources:"):
                current_zone = line
                active_zones[current_zone] = []
            elif line.startswith("interfaces:") and current_zone:
                active_zones[current_zone].append(line.replace("interfaces:", "").strip())

        all_zones = run_unprivileged(["firewall-cmd", "--get-zones"]).stdout.strip().split()
        self.zones_table.setRowCount(len(all_zones))
        self.add_zone_combo.clear()

        for row, zone in enumerate(sorted(all_zones)):
            self.zones_table.setItem(row, 0, QTableWidgetItem(zone))
            interfaces = ", ".join(active_zones.get(zone, [])) or "—"
            self.zones_table.setItem(row, 1, QTableWidgetItem(interfaces))

            is_active = zone in active_zones
            chk = QCheckBox("نشطة" if is_active else "معطَّلة")
            chk.setChecked(is_active)
            chk.setEnabled(active)
            if is_active:
                chk.setStyleSheet("color: #2e7d32;")
            chk.stateChanged.connect(lambda state, z=zone: self._on_zone_toggle(z, state == Qt.Checked))
            self.zones_table.setCellWidget(row, 2, chk)
            self.add_zone_combo.addItem(zone)

        svc_result = run_unprivileged(["firewall-cmd", "--list-services"])
        self.services_label.setText(svc_result.stdout.strip() or "لا services مفعّلة.")

        port_result = run_unprivileged(["firewall-cmd", "--list-ports"])
        self.ports_label.setText(port_result.stdout.strip() or "لا ports مفتوحة.")

    def _reload_ufw(self):
        r = run_unprivileged(["ufw", "status", "verbose"])
        self.ufw_status_label.setText(f"<pre>{r.stdout}</pre>")

    def _on_zone_toggle(self, zone, enable):
        if enable:
            self._run_cmd(["firewall-cmd", "--permanent", "--zone", zone, "--set-target=default"])
            self._run_cmd(["firewall-cmd", "--reload"])
        else:
            reply = QMessageBox.question(
                self, "تأكيد",
                f"تعطيل المنطقة {zone} سيغير سلوكها إلى 'drop' (حظر كل الاتصالات).\nهل أنت متأكد؟",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._run_cmd(["firewall-cmd", "--permanent", "--zone", zone, "--set-target=DROP"])
                self._run_cmd(["firewall-cmd", "--reload"])

    def _on_add_port(self):
        ptype = self.add_type_combo.currentText()
        value = self.add_value_input.text().strip()
        zone = self.add_zone_combo.currentText()
        if not value:
            QMessageBox.warning(self, "تنبيه", "أدخل قيمة صحيحة.")
            return
        if ptype == "port":
            if not re.match(r"^\d+/(tcp|udp)$", value):
                QMessageBox.warning(self, "تنبيه", "صيغة port يجب أن تكون: 8080/tcp أو 53/udp")
                return
            self._run_cmd(["firewall-cmd", "--permanent", "--zone", zone, "--add-port", value])
        else:
            self._run_cmd(["firewall-cmd", "--permanent", "--zone", zone, "--add-service", value])
        self._run_cmd(["firewall-cmd", "--reload"])
        self.add_value_input.clear()

    def _run_cmd(self, cmd):
        self.setEnabled(False)
        self._worker = FirewallActionWorker(cmd, parent=self)
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
