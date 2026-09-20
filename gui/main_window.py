#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/main_window.py
===================
النافذة الرئيسية: شريط علوي بملخص صحة النظام (تحاكي الشاشة الأولى في
Advanced SystemCare)، وتحته قائمة قابلة للتمرير من بطاقات الوحدات
المسجّلة في modules/registry.py.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.logger import get_logger, log_file_path
from core.scanner import SystemHealthReport, run_full_scan
from gui.module_card import ModuleCard
from gui.workers import FunctionWorker
from modules.registry import get_all_modules

log = get_logger("main_window")


class MainWindow(QMainWindow):
    def __init__(self, dry_run: bool = False):
        super().__init__()
        self.dry_run = bool(dry_run)
        title_suffix = "  — [dry-run]" if self.dry_run else ""
        self.setWindowTitle("Manjaro Care — مركز صيانة النظام" + title_suffix)
        self.resize(760, 640)
        self.setLayoutDirection(Qt.RightToLeft)

        self.modules = get_all_modules()
        self.cards: list[ModuleCard] = []
        # يجب الاحتفاظ بمرجع للـ worker قيد التشغيل، وإلا قد يُجمَّع
        # (garbage collected) قبل انتهائه
        self._scan_all_worker: FunctionWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        # ---- شريط وضع المعاينة الجافة (dry-run) ----
        # القاعدة: في هذا الوضع لا يُنفَّذ أي تعديل إطلاقاً — يُعرض فقط
        # ما كان سيُنفَّذ (معاينات البطاقات + سطر [DRY-RUN] في اللوغ)،
        # وزر «تطبيق» معطّل في كل البطاقات (طبقة 2 من 3 — راجع core/runtime.py).
        if self.dry_run:
            dry_banner = QLabel(
                "⚠ وضع المعاينة الجافة (dry-run): لن يُنفَّذ أي تعديل على النظام. "
                "اضغط «فحص» ثم «معاينة» في أي بطاقة لرؤية ما كان سيُنفَّذ — زر «تطبيق» معطّل."
            )
            dry_banner.setWordWrap(True)
            dry_banner.setLayoutDirection(Qt.RightToLeft)
            dry_banner.setStyleSheet(
                "background-color: #4a3a10; color: #ffca28; border: 1px solid #ffca28; "
                "border-radius: 8px; padding: 8px; font-weight: bold;"
            )
            outer.addWidget(dry_banner)

        # ---- لوحة الصحة العامة ----
        health_frame = QFrame()
        health_frame.setStyleSheet(
            "QFrame { background-color: #1e1e1e; border-radius: 12px; }"
        )
        health_layout = QVBoxLayout(health_frame)
        health_layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("مركز صيانة Manjaro")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        health_layout.addWidget(title)

        self.summary_label = QLabel("اضغط \"فحص شامل\" لبدء تقييم حالة النظام.")
        self.summary_label.setStyleSheet("color: #bbbbbb;")
        self.summary_label.setWordWrap(True)
        health_layout.addWidget(self.summary_label)

        scan_all_row = QHBoxLayout()
        self.scan_all_btn = QPushButton("فحص شامل للنظام")
        self.scan_all_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; padding: 8px 16px; font-weight: bold; }"
        )
        self.scan_all_btn.clicked.connect(self._on_scan_all)
        scan_all_row.addWidget(self.scan_all_btn)
        scan_all_row.addStretch()

        log_btn = QPushButton("فتح ملف اللوغ")
        log_btn.clicked.connect(self._open_log_location)
        scan_all_row.addWidget(log_btn)

        health_layout.addLayout(scan_all_row)
        outer.addWidget(health_frame)

        # ---- قائمة الوحدات القابلة للتمرير ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        modules_container = QWidget()
        modules_layout = QVBoxLayout(modules_container)
        modules_layout.setSpacing(12)

        for module in self.modules:
            card = ModuleCard(module)
            if self.dry_run:
                card.set_dry_run()
            self.cards.append(card)
            modules_layout.addWidget(card)

        modules_layout.addStretch()
        scroll.setWidget(modules_container)
        outer.addWidget(scroll, stretch=1)

    # ------------------------------------------------------------
    def _on_scan_all(self) -> None:
        self.scan_all_btn.setEnabled(False)
        self.scan_all_btn.setText("جارٍ الفحص...")

        self._scan_all_worker = FunctionWorker(lambda: run_full_scan(self.modules))
        self._scan_all_worker.finished_ok.connect(self._on_scan_all_finished)
        self._scan_all_worker.failed.connect(self._on_scan_all_failed)
        self._scan_all_worker.start()

    def _on_scan_all_finished(self, report: SystemHealthReport) -> None:
        self._render_summary(report)

        # حدّث كل بطاقة بنتيجتها الخاصة دون طلب فحص جديد منها (نتفادى
        # تشغيل نفس الفحص مرتين)
        for card, result in zip(self.cards, report.results, strict=False):
            card._last_scan = result
            card._render_scan_result(result)
            has_actionable = any(f.actionable for f in result.findings)
            card.preview_btn.setEnabled(has_actionable)

        self.scan_all_btn.setEnabled(True)
        self.scan_all_btn.setText("فحص شامل للنظام")

    def _on_scan_all_failed(self, error_text: str) -> None:
        from PyQt5.QtWidgets import QMessageBox
        self.scan_all_btn.setEnabled(True)
        self.scan_all_btn.setText("فحص شامل للنظام")
        QMessageBox.critical(self, "خطأ في الفحص الشامل", error_text)

    def _render_summary(self, report: SystemHealthReport) -> None:
        if report.critical_count:
            text = f"⚠ تم رصد {report.critical_count} مشكلة حرجة و{report.warning_count} تنبيهاً — راجع البطاقات أدناه."
            color = "#ef5350"
        elif report.warning_count:
            text = f"يوجد {report.warning_count} تنبيهاً يستحق المراجعة."
            color = "#ffa726"
        else:
            text = "النظام في حالة جيدة — لا مشاكل حرجة أو تنبيهات."
            color = "#66bb6a"

        self.summary_label.setText(text)
        self.summary_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _open_log_location(self) -> None:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "موقع ملف اللوغ", f"سجل التطبيق محفوظ في:\n{log_file_path()}"
        )
