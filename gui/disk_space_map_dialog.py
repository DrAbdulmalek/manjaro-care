#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only treemap-style view for the bounded home space inventory."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtWidgets import (QDialog, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem,
                             QGraphicsView, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QVBoxLayout)

from modules.disk_space_map import build_space_map, human_size


class DiskSpaceMapDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("خريطة مساحة مجلد المنزل — قراءة فقط")
        self.resize(900, 620)
        self.setLayoutDirection(Qt.RightToLeft)
        layout = QVBoxLayout(self)
        note = QLabel("كل مستطيل يمثل مجلداً أو ملفاً مباشراً؛ المساحة نسبية للحجم المحسوب. "
                      "لا يتم فتح محتوى الملفات أو حذفها. الفحص محدود بعدد العناصر والعمق.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setMinimumHeight(300)
        layout.addWidget(self.view, 2)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["العنصر", "الحجم", "النوع"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.status = QLabel()
        row.addWidget(self.status)
        row.addStretch()
        close = QPushButton("إغلاق")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self._load()

    def _load(self):
        result = build_space_map()
        entries = list(result.entries)
        self.table.setRowCount(len(entries))
        for index, entry in enumerate(entries):
            self.table.setItem(index, 0, QTableWidgetItem(entry.name))
            self.table.setItem(index, 1, QTableWidgetItem(human_size(entry.size_bytes)))
            self.table.setItem(index, 2, QTableWidgetItem("مجلد" if entry.kind == "directory" else "ملف"))
        self.scene.clear()
        total = sum(e.size_bytes for e in entries) or 1
        x = 0.0
        width, height = 820.0, 260.0
        palette = [QColor("#547a9e"), QColor("#638b70"), QColor("#9a7954"),
                   QColor("#806b9e"), QColor("#9b6666"), QColor("#688f91")]
        for index, entry in enumerate(entries[:24]):
            tile_width = max(3.0, width * entry.size_bytes / total)
            rect = QGraphicsRectItem(QRectF(x, 0, tile_width, height))
            rect.setBrush(QBrush(palette[index % len(palette)]))
            rect.setPen(QPen(QColor("#202020"), 1))
            self.scene.addItem(rect)
            if tile_width >= 55:
                label = QGraphicsTextItem(f"{entry.name}\n{human_size(entry.size_bytes)}")
                label.setDefaultTextColor(QColor("white"))
                label.setPos(x + 5, 5)
                label.setTextWidth(max(20, tile_width - 10))
                self.scene.addItem(label)
            x += tile_width
            if x >= width:
                break
        self.scene.setSceneRect(0, 0, max(width, x), height)
        status = f"العناصر المفحوصة: {result.scanned_entries} | المستبعدة/المتعذرة: {result.skipped_entries}"
        if result.truncated:
            status += " | تنبيه: الفحص جزئي بسبب بلوغ الحد الوقائي"
        self.status.setText(status)
