#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/report_export_dialog.py — نافذة «إدارة فردية» لتصدير التقرير:
معاينة النص المنقّى كاملاً قبل الحفظ، ثم «حفظ باسم…» — الحفظ الوحيد
المسموح (لا تعديل أي شيء آخر في النظام)."""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QMessageBox, QFileDialog,
)
from PyQt5.QtCore import Qt

from core.logger import get_logger
from modules.report_export import build_report_text, default_report_path

log = get_logger("report_export_dialog")


class ReportExportDialog(QDialog):
    """معاينة التقرير المنقّى + حفظ باسم — كل شيء مرئي قبل الحفظ."""

    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self.setWindowTitle(f"{module.name} — معاينة قبل الحفظ")
        self.resize(720, 560)
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        note = QLabel(
            "هذه المعاينة هي بالضبط ما سيُحفظ — التنقيح مطبق عليها بالفعل "
            "(مستخدم/جهاز/IP/MAC/تسلسلات/home). لا يُعدَّل أي إعداد نظام."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #ffca28;")
        layout.addWidget(note)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlainText(build_report_text())
        self.preview.setStyleSheet(
            "background-color: #1e1e1e; color: #e0e0e0; font-family: monospace; font-size: 9pt;"
        )
        layout.addWidget(self.preview, stretch=1)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("حفظ باسم…")
        save_btn.setStyleSheet("background-color: #2e7d32; font-weight: bold;")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "حفظ التقرير المنقّى", default_report_path(),
            "Markdown (*.md);;Text (*.txt);;All files (*)",
        )
        if not target:
            return  # المستخدم ألغى — لا شيء يُكتب
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(self.preview.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "فشل الحفظ", str(exc))
            return
        log.info("تم حفظ التقرير: %s", target)
        QMessageBox.information(self, "تم", f"حُفظ التقرير المنقّى في:\n{target}")
