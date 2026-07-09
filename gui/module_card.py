#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/module_card.py
===================
بطاقة واجهة موحّدة لكل وحدة صيانة. تلتزم بنمط "فحص → معاينة → تطبيق"
المفروض من core/module_base.py، بحيث لا يمكن لأي وحدة تجاوز خطوة
المعاينة والذهاب مباشرة للتطبيق دون أن يرى المستخدم ماذا سيحدث بالضبط.

كل عمليات scan()/apply() تُنفَّذ عبر gui/workers.py في خيط خلفي —
هذا يمنع تجمّد الواجهة (GUI freeze) أثناء فحص بطيء (مثل disk_analyzer
على مجلد شخصي ضخم) أو أثناء انتظار مصادقة polkit.

الألوان تعكس severity/risk_level بنفس منطق البطاقات في أدوات مثل
Wise Care 365 — أخضر=سليم، أصفر=تنبيه، أحمر=حرج.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QTextEdit, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from core.module_base import MaintenanceModule, Severity, ScanResult
from gui.workers import FunctionWorker

_SEVERITY_COLORS = {
    Severity.OK: "#2e7d32",        # أخضر
    Severity.INFO: "#1565c0",      # أزرق
    Severity.WARNING: "#e65100",   # برتقالي
    Severity.CRITICAL: "#c62828",  # أحمر
}

_RISK_LABELS = {
    "safe": "آمن",
    "moderate": "متوسط الحساسية",
    "destructive": "حساس — لا يمكن التراجع بسهولة",
}


class ModuleCard(QFrame):
    """بطاقة واحدة تمثّل وحدة صيانة واحدة ضمن القائمة الرئيسية."""

    apply_requested = pyqtSignal(object)  # يُبعث عند نجاح تطبيق فعلي، يحمل الوحدة

    def __init__(self, module: MaintenanceModule, parent=None):
        super().__init__(parent)
        self.module = module
        self._last_scan: ScanResult | None = None
        # يجب الاحتفاظ بمرجع لكل worker قيد التشغيل، وإلا قد يُجمَّع
        # (garbage collected) قبل انتهائه فينهار التطبيق بصمت
        self._scan_worker: FunctionWorker | None = None
        self._apply_worker: FunctionWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("moduleCard")
        self.setStyleSheet("""
            QFrame#moduleCard {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        # ---- رأس البطاقة: الاسم + مستوى الحساسية ----
        header = QHBoxLayout()
        title = QLabel(self.module.name)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setLayoutDirection(Qt.RightToLeft)
        header.addWidget(title)

        header.addStretch()

        risk_label = QLabel(_RISK_LABELS.get(self.module.risk_level.value, ""))
        risk_label.setStyleSheet("color: #999; font-size: 10pt;")
        header.addWidget(risk_label)
        root.addLayout(header)

        # ---- الوصف ----
        desc = QLabel(self.module.description)
        desc.setWordWrap(True)
        desc.setLayoutDirection(Qt.RightToLeft)
        desc.setStyleSheet("color: #cfcfcf;")
        root.addWidget(desc)

        # ---- منطقة نتائج الفحص (تُملأ بعد الضغط على "فحص") ----
        self.result_label = QLabel("لم يتم الفحص بعد.")
        self.result_label.setWordWrap(True)
        self.result_label.setLayoutDirection(Qt.RightToLeft)
        self.result_label.setStyleSheet("color: #aaaaaa; padding-top: 4px;")
        root.addWidget(self.result_label)

        # ---- منطقة معاينة تفصيلية (مخفية حتى الحاجة) ----
        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setFixedHeight(90)
        self.preview_box.setStyleSheet(
            "background-color: #1e1e1e; color: #9fdc9f; font-family: monospace; font-size: 9pt;"
        )
        self.preview_box.hide()
        root.addWidget(self.preview_box)

        # ---- الأزرار ----
        btn_row = QHBoxLayout()

        self.scan_btn = QPushButton("فحص")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        btn_row.addWidget(self.scan_btn)

        self.preview_btn = QPushButton("معاينة")
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        self.preview_btn.setEnabled(False)
        btn_row.addWidget(self.preview_btn)

        self.apply_btn = QPushButton("تطبيق")
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #37474f; } "
            "QPushButton:disabled { background-color: #2a2a2a; color: #666; }"
        )
        btn_row.addWidget(self.apply_btn)

        if self.module.has_custom_ui:
            self.manage_btn = QPushButton("إدارة فردية")
            self.manage_btn.setStyleSheet("background-color: #1565c0;")
            self.manage_btn.clicked.connect(self._on_manage_clicked)
            btn_row.addWidget(self.manage_btn)

        root.addLayout(btn_row)

    # ---------------------------------------------------------------
    # الفحص — يعمل في خيط خلفي حتى لا يُجمِّد الواجهة
    # ---------------------------------------------------------------
    def _on_scan_clicked(self) -> None:
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("جارٍ الفحص...")

        self._scan_worker = FunctionWorker(self.module.scan)
        self._scan_worker.finished_ok.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_finished(self, result: ScanResult) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("فحص")

        self._last_scan = result
        self._render_scan_result(result)
        has_actionable = any(f.actionable for f in result.findings)
        self.preview_btn.setEnabled(has_actionable)

    def _on_scan_failed(self, error_text: str) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("فحص")
        QMessageBox.critical(self, "خطأ في الفحص", error_text)

    def _render_scan_result(self, result: ScanResult) -> None:
        if result.error:
            self.result_label.setText(f"⚠ فشل الفحص: {result.error}")
            self.result_label.setStyleSheet(f"color: {_SEVERITY_COLORS[Severity.CRITICAL]};")
            return

        lines = [f"● {finding.title}" for finding in result.findings]
        text = "\n".join(lines) if lines else "لا نتائج."
        self.result_label.setText(text)
        self.result_label.setStyleSheet(
            f"color: {_SEVERITY_COLORS.get(result.worst_severity, '#cfcfcf')}; padding-top: 4px;"
        )

    # ---------------------------------------------------------------
    # المعاينة — سريعة عادة (لا تنفّذ أوامر)، تبقى في الخيط الرئيسي
    # ---------------------------------------------------------------
    def _on_preview_clicked(self) -> None:
        try:
            steps = self.module.preview()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "خطأ في المعاينة", str(exc))
            return

        if not steps:
            self.preview_box.setPlainText("لا توجد خطوات لتنفيذها حالياً.")
        else:
            lines = []
            for step in steps:
                lines.append(f"• {step.description}")
                if step.command:
                    lines.append(f"    $ {step.command}")
            self.preview_box.setPlainText("\n".join(lines))

        self.preview_box.show()
        self.apply_btn.setEnabled(True)

    # ---------------------------------------------------------------
    # التطبيق — في خيط خلفي أيضاً (قد ينتظر مصادقة polkit لثوانٍ)
    # ---------------------------------------------------------------
    def _on_apply_clicked(self) -> None:
        confirm = QMessageBox.question(
            self,
            "تأكيد التنفيذ",
            f'سيتم الآن تنفيذ التغييرات الظاهرة في المعاينة لوحدة "{self.module.name}".\n'
            "هل أنت متأكد؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.apply_btn.setEnabled(False)
        self.apply_btn.setText("جارٍ التنفيذ...")

        self._apply_worker = FunctionWorker(self.module.apply)
        self._apply_worker.finished_ok.connect(self._on_apply_finished)
        self._apply_worker.failed.connect(self._on_apply_failed)
        self._apply_worker.start()

    def _on_apply_finished(self, result) -> None:
        self.apply_btn.setText("تطبيق")

        if result.success:
            QMessageBox.information(self, "تم", result.message)
            self._on_scan_clicked()  # إعادة فحص لتحديث الحالة بعد التنفيذ
        else:
            QMessageBox.warning(self, "فشل جزئي أو كلي", result.message)
            self.apply_btn.setEnabled(True)

        self.apply_requested.emit(self.module)

    def _on_apply_failed(self, error_text: str) -> None:
        self.apply_btn.setText("تطبيق")
        self.apply_btn.setEnabled(True)
        QMessageBox.critical(self, "خطأ في التنفيذ", error_text)

    # ---------------------------------------------------------------
    # الوحدات ذات الواجهة المخصصة (مثل startup_manager)
    # ---------------------------------------------------------------
    def _on_manage_clicked(self) -> None:
        from gui.custom_dialogs import get_custom_dialog

        dialog_cls = get_custom_dialog(self.module.slug)
        if dialog_cls is None:
            QMessageBox.information(self, "غير متوفر", "لا توجد نافذة إدارة مخصصة لهذه الوحدة بعد.")
            return

        dialog = dialog_cls(parent=self)
        dialog.exec_()
        self._on_scan_clicked()  # تحديث ملخص البطاقة بعد إغلاق النافذة
