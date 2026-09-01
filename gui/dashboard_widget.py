#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/dashboard_widget.py — لوحة قيادة النظام التفاعلية مع التنبيهات الذكية.
"""
from __future__ import annotations
import json
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import psutil
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QGridLayout, QFrame, QSizePolicy, QSplitter,
    QTextEdit, QListWidget, QListWidgetItem, QSpinBox,
    QFormLayout, QGroupBox, QCheckBox, QTabWidget, QSystemTrayIcon,
    QAction, QMenu, QMessageBox, QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QColor, QFont, QIcon, QPalette

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("dashboard_widget")

HISTORY_FILE = Path.home() / ".config" / "manjaro-care" / "stats_history.json"
ALERTS_FILE = Path.home() / ".config" / "manjaro-care" / "alerts_log.json"
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 60


class AlertManager:
    """يدير التنبيهات والعتبات."""
    DEFAULT_THRESHOLDS = {
        "cpu": 90,
        "ram": 85,
        "disk": 90,
        "temp": 85,
    }

    def __init__(self):
        self.thresholds = dict(self.DEFAULT_THRESHOLDS)
        self.enabled = {"cpu": True, "ram": True, "disk": True, "temp": True}
        self._last_alert_time = {}
        self._cooldown = 60
        self.alerts_log = deque(maxlen=100)
        self._load_alerts()

    def check(self, stats):
        alerts = []
        now = time.time()

        if self.enabled["cpu"] and stats["cpu"] > self.thresholds["cpu"]:
            key = "cpu"
            if now - self._last_alert_time.get(key, 0) > self._cooldown:
                alerts.append({
                    "type": "cpu",
                    "level": "critical" if stats["cpu"] > 95 else "warning",
                    "message": f"CPU مرتفع: {stats['cpu']:.1f}%",
                    "value": stats["cpu"],
                    "threshold": self.thresholds["cpu"],
                    "time": datetime.now().strftime("%H:%M:%S"),
                })
                self._last_alert_time[key] = now

        if self.enabled["ram"] and stats["ram_percent"] > self.thresholds["ram"]:
            key = "ram"
            if now - self._last_alert_time.get(key, 0) > self._cooldown:
                alerts.append({
                    "type": "ram",
                    "level": "critical" if stats["ram_percent"] > 95 else "warning",
                    "message": f"RAM ممتلئة: {stats['ram_percent']:.1f}%",
                    "value": stats["ram_percent"],
                    "threshold": self.thresholds["ram"],
                    "time": datetime.now().strftime("%H:%M:%S"),
                })
                self._last_alert_time[key] = now

        if self.enabled["disk"] and stats["disk_percent"] > self.thresholds["disk"]:
            key = "disk"
            if now - self._last_alert_time.get(key, 0) > self._cooldown:
                alerts.append({
                    "type": "disk",
                    "level": "critical",
                    "message": f"القرص ممتلئ: {stats['disk_percent']:.1f}%",
                    "value": stats["disk_percent"],
                    "threshold": self.thresholds["disk"],
                    "time": datetime.now().strftime("%H:%M:%S"),
                })
                self._last_alert_time[key] = now

        temps = stats.get("temps", {})
        if self.enabled["temp"] and temps:
            max_temp = max(temps.values())
            if max_temp > self.thresholds["temp"]:
                key = "temp"
                if now - self._last_alert_time.get(key, 0) > self._cooldown:
                    alerts.append({
                        "type": "temp",
                        "level": "critical" if max_temp > 90 else "warning",
                        "message": f"حرارة مرتفعة: {max_temp:.1f}C",
                        "value": max_temp,
                        "threshold": self.thresholds["temp"],
                        "time": datetime.now().strftime("%H:%M:%S"),
                    })
                    self._last_alert_time[key] = now

        for alert in alerts:
            self.alerts_log.appendleft(alert)
        return alerts

    def _load_alerts(self):
        if ALERTS_FILE.exists():
            try:
                with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for a in data.get("alerts", [])[-100:]:
                    self.alerts_log.append(a)
            except Exception as exc:
                log.error(f"load_alerts: {exc}")

    def save(self):
        try:
            with open(ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump({"alerts": list(self.alerts_log)}, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.error(f"save_alerts: {exc}")


class StatsCollector(QThread):
    stats_ready = pyqtSignal(dict)

    def run(self):
        while True:
            stats = self._collect()
            self.stats_ready.emit(stats)
            time.sleep(2)

    def _collect(self):
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        cpu_perc = psutil.cpu_percent(interval=1)
        temps = {}
        try:
            for name, entries in psutil.sensors_temperatures().items():
                for entry in entries:
                    temps[entry.label or name] = entry.current
        except Exception:
            pass

        return {
            "timestamp": datetime.now().isoformat(),
            "cpu": cpu_perc,
            "ram_used": mem.used,
            "ram_total": mem.total,
            "ram_percent": mem.percent,
            "disk_used": disk.used,
            "disk_total": disk.total,
            "disk_percent": disk.percent,
            "net_sent": net.bytes_sent,
            "net_recv": net.bytes_recv,
            "temps": temps,
        }


class DashboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = {
            "cpu": deque(maxlen=MAX_HISTORY),
            "ram": deque(maxlen=MAX_HISTORY),
            "disk": deque(maxlen=MAX_HISTORY),
            "net_sent": deque(maxlen=MAX_HISTORY),
            "net_recv": deque(maxlen=MAX_HISTORY),
            "timestamps": deque(maxlen=MAX_HISTORY),
        }
        self._last_net = {"sent": 0, "recv": 0, "time": time.time()}
        self._load_history()
        self.alert_manager = AlertManager()
        self._paused = False
        self._build_ui()
        self._start_collector()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("لوحة قيادة النظام")
        f = title.font()
        f.setBold(True)
        f.setPointSize(14)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        cards = QHBoxLayout()
        self.card_cpu = self._create_card("CPU", "0%", "#1565c0")
        self.card_ram = self._create_card("RAM", "0%", "#2e7d32")
        self.card_disk = self._create_card("القرص", "0%", "#c62828")
        self.card_net = self._create_card("الشبكة", "0 / 0", "#ff9800")
        self.card_temp = self._create_card("الحرارة", "—", "#7b1fa2")
        cards.addWidget(self.card_cpu)
        cards.addWidget(self.card_ram)
        cards.addWidget(self.card_disk)
        cards.addWidget(self.card_net)
        cards.addWidget(self.card_temp)
        layout.addLayout(cards)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=1)

        charts_tab = QWidget()
        charts_layout = QVBoxLayout(charts_tab)
        charts_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Vertical)
        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.cpu_fig = self._create_figure("استخدام CPU", "#1565c0")
        self.ram_fig = self._create_figure("استخدام RAM", "#2e7d32")
        top_layout.addWidget(self.cpu_fig)
        top_layout.addWidget(self.ram_fig)
        splitter.addWidget(top_row)

        mid_row = QWidget()
        mid_layout = QHBoxLayout(mid_row)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        self.disk_fig = self._create_pie_figure("القرص")
        self.net_fig = self._create_net_figure("الشبكة")
        mid_layout.addWidget(self.disk_fig)
        mid_layout.addWidget(self.net_fig)
        splitter.addWidget(mid_row)

        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.sys_info = QTextEdit()
        self.sys_info.setReadOnly(True)
        self.sys_info.setMaximumHeight(100)
        self.sys_info.setStyleSheet("background: #1e1e1e; color: #e0e0e0; border-radius: 4px;")
        bottom_layout.addWidget(self.sys_info)
        splitter.addWidget(bottom)

        splitter.setSizes([200, 200, 80])
        charts_layout.addWidget(splitter)
        self.tabs.addTab(charts_tab, "الرسوم البيانية")

        alerts_tab = QWidget()
        alerts_layout = QVBoxLayout(alerts_tab)

        alerts_top = QHBoxLayout()
        self.alert_count_label = QLabel("0 تنبيهات نشطة")
        alerts_top.addWidget(self.alert_count_label)
        alerts_top.addStretch()
        clear_alerts_btn = QPushButton("مسح السجل")
        clear_alerts_btn.clicked.connect(self._clear_alerts)
        alerts_top.addWidget(clear_alerts_btn)
        alerts_layout.addLayout(alerts_top)

        self.alerts_list = QListWidget()
        self.alerts_list.setStyleSheet("""
            QListWidget { background: #1e1e1e; border-radius: 4px; color: #e0e0e0; }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background: #1565c0; }
        """)
        alerts_layout.addWidget(self.alerts_list)

        thresh_group = QGroupBox("إعدادات العتبات")
        thresh_layout = QFormLayout(thresh_group)

        self.thresh_cpu = QSpinBox()
        self.thresh_cpu.setRange(50, 100)
        self.thresh_cpu.setValue(self.alert_manager.thresholds["cpu"])
        self.thresh_cpu.valueChanged.connect(lambda v: self.alert_manager.thresholds.update({"cpu": v}))
        thresh_layout.addRow("CPU %:", self.thresh_cpu)

        self.thresh_ram = QSpinBox()
        self.thresh_ram.setRange(50, 100)
        self.thresh_ram.setValue(self.alert_manager.thresholds["ram"])
        self.thresh_ram.valueChanged.connect(lambda v: self.alert_manager.thresholds.update({"ram": v}))
        thresh_layout.addRow("RAM %:", self.thresh_ram)

        self.thresh_disk = QSpinBox()
        self.thresh_disk.setRange(50, 100)
        self.thresh_disk.setValue(self.alert_manager.thresholds["disk"])
        self.thresh_disk.valueChanged.connect(lambda v: self.alert_manager.thresholds.update({"disk": v}))
        thresh_layout.addRow("Disk %:", self.thresh_disk)

        self.thresh_temp = QSpinBox()
        self.thresh_temp.setRange(40, 110)
        self.thresh_temp.setValue(self.alert_manager.thresholds["temp"])
        self.thresh_temp.valueChanged.connect(lambda v: self.alert_manager.thresholds.update({"temp": v}))
        thresh_layout.addRow("Temp C:", self.thresh_temp)

        alerts_layout.addWidget(thresh_group)
        self.tabs.addTab(alerts_tab, "التنبيهات")

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("حفظ التقرير")
        self.save_btn.clicked.connect(self._save_report)
        btn_row.addWidget(self.save_btn)

        self.export_btn = QPushButton("تصدير JSON")
        self.export_btn.clicked.connect(self._export_json)
        btn_row.addWidget(self.export_btn)

        btn_row.addStretch()

        self.pause_btn = QPushButton("إيقاف مؤقت")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self.pause_btn)
        layout.addLayout(btn_row)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("Manjaro Care Dashboard")
        self.tray_menu = QMenu(self)
        show_action = QAction("عرض", self)
        show_action.triggered.connect(self.window().showNormal)
        self.tray_menu.addAction(show_action)
        quit_action = QAction("خروج", self)
        quit_action.triggered.connect(self.window().close)
        self.tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

    def _create_card(self, title, value, color):
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(self._card_style(color))
        layout = QVBoxLayout(card)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #aaaaaa; font-size: 10pt;")
        layout.addWidget(lbl_title)
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(f"color: {color}; font-size: 16pt; font-weight: bold;")
        lbl_value.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_value)
        card._value_label = lbl_value
        return card

    def _card_style(self, color):
        return f"""
            QFrame {{
                background-color: #2a2a2a;
                border-left: 4px solid {color};
                border-radius: 6px;
                padding: 8px;
            }}
        """

    def _create_figure(self, title, color):
        fig = Figure(figsize=(4, 2.5), dpi=100, facecolor="#1e1e1e")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#1e1e1e")
        ax.set_title(title, color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3, color="#555555")
        line, = ax.plot([], [], color=color, linewidth=1.5)
        fig._line = line
        fig._ax = ax
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return canvas

    def _create_pie_figure(self, title):
        fig = Figure(figsize=(3, 2.5), dpi=100, facecolor="#1e1e1e")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#1e1e1e")
        ax.set_title(title, color="white", fontsize=10)
        wedges, texts, autotexts = ax.pie(
            [1, 1], labels=["مستخدم", "متاح"], autopct="%1.1f%%",
            colors=["#c62828", "#2e7d32"], textprops={"color": "white", "fontsize": 8}
        )
        fig._wedges = wedges
        fig._autotexts = autotexts
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return canvas

    def _create_net_figure(self, title):
        fig = Figure(figsize=(4, 2.5), dpi=100, facecolor="#1e1e1e")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#1e1e1e")
        ax.set_title(title, color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(True, alpha=0.3, color="#555555")
        line_down, = ax.plot([], [], color="#2e7d32", linewidth=1.5, label="استقبال")
        line_up, = ax.plot([], [], color="#ff9800", linewidth=1.5, label="إرسال")
        ax.legend(loc="upper left", facecolor="#1e1e1e", edgecolor="white", labelcolor="white", fontsize=7)
        fig._line_down = line_down
        fig._line_up = line_up
        fig._ax = ax
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return canvas

    def _start_collector(self):
        self._collector = StatsCollector(parent=self)
        self._collector.stats_ready.connect(self._on_stats)
        self._collector.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_plots)
        self._timer.start(2000)

    def _on_stats(self, stats):
        if self._paused:
            return
        self.card_cpu._value_label.setText(f"{stats['cpu']:.1f}%")
        self.card_ram._value_label.setText(
            f"{self._hs(stats['ram_used'])} / {self._hs(stats['ram_total'])} ({stats['ram_percent']:.0f}%)"
        )
        self.card_disk._value_label.setText(
            f"{self._hs(stats['disk_used'])} / {self._hs(stats['disk_total'])} ({stats['disk_percent']:.0f}%)"
        )
        now = time.time()
        dt = now - self._last_net["time"]
        sent_speed = (stats["net_sent"] - self._last_net["sent"]) / dt if dt > 0 else 0
        recv_speed = (stats["net_recv"] - self._last_net["recv"]) / dt if dt > 0 else 0
        self.card_net._value_label.setText(f"v {self._hs_speed(recv_speed)} | ^ {self._hs_speed(sent_speed)}")
        self._last_net = {"sent": stats["net_sent"], "recv": stats["net_recv"], "time": now}

        temps = stats.get("temps", {})
        if temps:
            avg_temp = sum(temps.values()) / len(temps)
            self.card_temp._value_label.setText(f"{avg_temp:.1f}C")
            max_t = max(temps.values())
            if max_t > self.alert_manager.thresholds["temp"]:
                self.card_temp.setStyleSheet(self._card_style("#c62828"))
            elif max_t > 70:
                self.card_temp.setStyleSheet(self._card_style("#ff9800"))
            else:
                self.card_temp.setStyleSheet(self._card_style("#7b1fa2"))
        else:
            self.card_temp._value_label.setText("—")

        if stats["cpu"] > self.alert_manager.thresholds["cpu"]:
            self.card_cpu.setStyleSheet(self._card_style("#c62828"))
        else:
            self.card_cpu.setStyleSheet(self._card_style("#1565c0"))

        if stats["ram_percent"] > self.alert_manager.thresholds["ram"]:
            self.card_ram.setStyleSheet(self._card_style("#c62828"))
        else:
            self.card_ram.setStyleSheet(self._card_style("#2e7d32"))

        self.history["cpu"].append(stats["cpu"])
        self.history["ram"].append(stats["ram_percent"])
        self.history["disk"].append(stats["disk_percent"])
        self.history["net_sent"].append(sent_speed)
        self.history["net_recv"].append(recv_speed)
        self.history["timestamps"].append(datetime.now().strftime("%H:%M:%S"))

        self._update_sys_info(stats, temps)
        alerts = self.alert_manager.check(stats)
        if alerts:
            self._handle_alerts(alerts)

    def _handle_alerts(self, alerts):
        for alert in alerts:
            item = QListWidgetItem(f"[{alert['time']}] {alert['message']}")
            if alert["level"] == "critical":
                item.setBackground(QColor("#c62828"))
                item.setForeground(QColor("white"))
            else:
                item.setBackground(QColor("#ff9800"))
                item.setForeground(QColor("black"))
            self.alerts_list.insertItem(0, item)
        self.alert_count_label.setText(f"{len(self.alert_manager.alerts_log)} تنبيه مسجل")
        if alerts:
            latest = alerts[-1]
            self.tray_icon.showMessage(
                f"Manjaro Care — {latest['level'].upper()}",
                latest["message"],
                QSystemTrayIcon.Critical if latest["level"] == "critical" else QSystemTrayIcon.Warning,
                5000,
            )
        self.alert_manager.save()

    def _clear_alerts(self):
        self.alerts_list.clear()
        self.alert_manager.alerts_log.clear()
        self.alert_count_label.setText("0 تنبيهات")
        self.alert_manager.save()

    def _update_plots(self):
        if not self.history["timestamps"]:
            return
        t = list(self.history["timestamps"])
        ax = self.cpu_fig._ax
        self.cpu_fig._line.set_data(range(len(t)), list(self.history["cpu"]))
        ax.set_xlim(0, max(len(t), MAX_HISTORY))
        self.cpu_fig.draw()
        ax = self.ram_fig._ax
        self.ram_fig._line.set_data(range(len(t)), list(self.history["ram"]))
        ax.set_xlim(0, max(len(t), MAX_HISTORY))
        self.ram_fig.draw()
        if self.history["disk"]:
            last_disk = self.history["disk"][-1]
            self.disk_fig._wedges[0].set_theta1(0)
            self.disk_fig._wedges[0].set_theta2(last_disk * 3.6)
            self.disk_fig._wedges[1].set_theta1(last_disk * 3.6)
            self.disk_fig._wedges[1].set_theta2(360)
            self.disk_fig._autotexts[0].set_text(f"{last_disk:.1f}%")
            self.disk_fig.draw()
        ax = self.net_fig._ax
        self.net_fig._line_down.set_data(range(len(t)), list(self.history["net_recv"]))
        self.net_fig._line_up.set_data(range(len(t)), list(self.history["net_sent"]))
        ax.set_xlim(0, max(len(t), MAX_HISTORY))
        all_net = list(self.history["net_recv"]) + list(self.history["net_sent"])
        if all_net:
            max_val = max(all_net) * 1.2
            ax.set_ylim(0, max(max_val, 1))
        self.net_fig.draw()

    def _update_sys_info(self, stats, temps):
        uptime = ""
        try:
            with open("/proc/uptime") as f:
                secs = float(f.readline().split()[0])
                hours = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                uptime = f"{hours}h {mins}m"
        except Exception:
            pass
        temp_str = ", ".join(f"{k}: {v:.1f}C" for k, v in list(temps.items())[:3]) if temps else "—"
        info = f"Uptime: {uptime} | RAM: {self._hs(stats['ram_used'])} used | Disk: {self._hs(stats['disk_used'])} used | Temps: {temp_str}"
        self.sys_info.setPlainText(info)

    def _toggle_pause(self, checked):
        self._paused = checked
        self.pause_btn.setText("استئناف" if checked else "إيقاف مؤقت")

    def _save_history(self):
        data = {
            "saved_at": datetime.now().isoformat(),
            "cpu": list(self.history["cpu"]),
            "ram": list(self.history["ram"]),
            "disk": list(self.history["disk"]),
            "timestamps": list(self.history["timestamps"]),
        }
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as exc:
            log.error(f"save_history: {exc}")

    def _load_history(self):
        if not HISTORY_FILE.exists():
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.history["cpu"].extend(data.get("cpu", [])[-MAX_HISTORY:])
            self.history["ram"].extend(data.get("ram", [])[-MAX_HISTORY:])
            self.history["disk"].extend(data.get("disk", [])[-MAX_HISTORY:])
            self.history["timestamps"].extend(data.get("timestamps", [])[-MAX_HISTORY:])
        except Exception as exc:
            log.error(f"load_history: {exc}")

    def _save_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "حفظ التقرير", str(Path.home() / "manjaro-care-report.txt"), "Text (*.txt)"
        )
        if not path:
            return
        lines = [
            "Manjaro Care Dashboard Report",
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        if self.history["cpu"]:
            lines.append(f"CPU Average: {sum(self.history['cpu'])/len(self.history['cpu']):.1f}%")
        if self.history["ram"]:
            lines.append(f"RAM Average: {sum(self.history['ram'])/len(self.history['ram']):.1f}%")
        if self.history["disk"]:
            lines.append(f"Disk Usage: {self.history['disk'][-1]:.1f}%")
        lines.append("")
        lines.append("--- Alerts ---")
        for alert in list(self.alert_manager.alerts_log)[:20]:
            lines.append(f"[{alert['time']}] {alert['message']}")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "تم", "تم حفظ التقرير.")

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير JSON", str(Path.home() / "manjaro-care-stats.json"), "JSON (*.json)"
        )
        if not path:
            return
        data = {
            "exported_at": datetime.now().isoformat(),
            "cpu": list(self.history["cpu"]),
            "ram": list(self.history["ram"]),
            "disk": list(self.history["disk"]),
            "net_sent": list(self.history["net_sent"]),
            "net_recv": list(self.history["net_recv"]),
            "timestamps": list(self.history["timestamps"]),
            "alerts": list(self.alert_manager.alerts_log),
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        QMessageBox.information(self, "تم", "تم تصدير البيانات.")

    def closeEvent(self, event):
        self._save_history()
        self.alert_manager.save()
        self._collector.terminate()
        self.tray_icon.hide()
        event.accept()

    @staticmethod
    def _hs(size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @staticmethod
    def _hs_speed(size):
        for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB/s"


class DashboardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("لوحة قيادة النظام")
        self.resize(950, 750)
        self.setLayoutDirection(Qt.RightToLeft)
        layout = QVBoxLayout(self)
        self.dashboard = DashboardWidget(self)
        layout.addWidget(self.dashboard)
        btn = QPushButton("إغلاق")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
