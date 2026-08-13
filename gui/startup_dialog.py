#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/startup_dialog.py
========================
نافذة مخصصة لإدارة برامج بدء التشغيل فردياً — مكافئ تبويب "Startup"
في Windows Task Manager/msconfig. كل صف مستقل تماماً عن البقية،
ولذلك لا يستخدم نمط فحص/معاينة/تطبيق الجماعي المتّبع في بقية الوحدات.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox,
)
from PyQt5.QtCore import Qt

from modules.startup_manager import list_entries, toggle_entry, AutostartEntry


class StartupManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة برامج بدء التشغيل")
        self.resize(560, 420)
        self.setLayoutDirection(Qt.RightToLeft)

        self.entries: list[AutostartEntry] = []
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "فعّل أو عطّل كل برنامج على حدة. التعطيل لا يحذف البرنامج، "
            "فقط يمنعه من العمل تلقائياً عند تسجيل الدخول."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["البرنامج", "الوصف", "المصدر", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self.table)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _reload(self) -> None:
        self.entries = list_entries()
        self.table.setRowCount(len(self.entries))

        for row, entry in enumerate(self.entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.display_name))
            self.table.setItem(row, 1, QTableWidgetItem(entry.comment))
            source_text = "النظام" if entry.is_system else "المستخدم"
            self.table.setItem(row, 2, QTableWidgetItem(source_text))

            toggle_btn = QPushButton("مفعّل ✔" if entry.enabled else "معطَّل ✘")
            toggle_btn.setCheckable(True)
            toggle_btn.setChecked(entry.enabled)
            toggle_btn.setStyleSheet(
                "QPushButton { background-color: #2e7d32; } "
                "QPushButton:!checked { background-color: #4a4a4a; color: #999; }"
            )
            # نلتقط basename بدل الاعتماد على row لتفادي مشاكل إن تغيّر الترتيب لاحقاً
            toggle_btn.clicked.connect(
                lambda checked, basename=entry.basename: self._on_toggle(basename)
            )
            self.table.setCellWidget(row, 3, toggle_btn)

    def _on_toggle(self, basename: str) -> None:
        entry = next((e for e in self.entries if e.basename == basename), None)
        if entry is None:
            return
        try:
            toggle_entry(entry)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "خطأ", f"تعذّر تعديل {entry.display_name}:\n{exc}")
        self._reload()
