#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asynchronous, read-only treemap view for the bounded home space inventory."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtWidgets import (
    QDialog, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QVBoxLayout,
)

from gui.workers import BusyCloseGuardMixin, FunctionWorker
from modules.disk_space_map import SpaceEntry, SpaceMapResult, build_space_map, human_size


_PALETTE = [
    QColor("#547a9e"), QColor("#638b70"), QColor("#9a7954"),
    QColor("#806b9e"), QColor("#9b6666"), QColor("#688f91"),
]


def _treemap_rectangles(entries: list[SpaceEntry], bounds: QRectF) -> list[tuple[SpaceEntry, QRectF]]:
    """Binary-split treemap: every tile area is proportional to its byte weight."""
    if not entries or bounds.width() <= 0 or bounds.height() <= 0:
        return []
    weights = [max(1, entry.size_bytes) for entry in entries]
    output: list[tuple[SpaceEntry, QRectF]] = []

    def split(items, item_weights, rect):
        if len(items) == 1:
            output.append((items[0], rect))
            return
        half = sum(item_weights) / 2
        cumulative = 0
        cut = 1
        for index, weight in enumerate(item_weights[:-1], start=1):
            cumulative += weight
            cut = index
            if cumulative >= half:
                break
        first_weight = sum(item_weights[:cut])
        ratio = first_weight / sum(item_weights)
        if rect.width() >= rect.height():
            split_rect = QRectF(rect.x(), rect.y(), rect.width() * ratio, rect.height())
            rest_rect = QRectF(rect.x() + split_rect.width(), rect.y(),
                               rect.width() - split_rect.width(), rect.height())
        else:
            split_rect = QRectF(rect.x(), rect.y(), rect.width(), rect.height() * ratio)
            rest_rect = QRectF(rect.x(), rect.y() + split_rect.height(),
                               rect.width(), rect.height() - split_rect.height())
        split(items[:cut], item_weights[:cut], split_rect)
        split(items[cut:], item_weights[cut:], rest_rect)

    split(entries, weights, bounds)
    return output


class DiskSpaceMapDialog(BusyCloseGuardMixin, QDialog):
    _GUARD_ATTRS = ("_worker",)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("خريطة مساحة مجلد المنزل — قراءة فقط")
        self.resize(940, 680)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        layout = QVBoxLayout(self)
        note = QLabel(
            "خريطة Treemap حقيقية: مساحة كل مستطيل تتناسب مع الحجم المحسوب. "
            "الفحص يعمل في الخلفية، محدود العدد والعمق، ولا يقرأ محتوى الملفات أو يعدّلها."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setMinimumHeight(340)
        layout.addWidget(self.view, 2)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["العنصر", "الحجم", "النوع"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.status = QLabel("جاهز للفحص.")
        row.addWidget(self.status)
        row.addStretch()
        self.refresh_btn = QPushButton("إعادة الفحص")
        self.refresh_btn.clicked.connect(self._start_scan)
        row.addWidget(self.refresh_btn)
        close = QPushButton("إغلاق")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self._start_scan()

    def _start_scan(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.status.setText("جارٍ تحليل مجلد المنزل في خيط خلفي...")
        self._worker = FunctionWorker(build_space_map, parent=self)
        self._worker.finished_ok.connect(self._render_result)
        self._worker.failed.connect(self._render_error)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _worker_finished(self):
        self.refresh_btn.setEnabled(True)

    def _render_error(self, error: str):
        self.scene.clear()
        self.status.setText(f"تعذّر إكمال الفحص: {error}")

    def _render_result(self, result: SpaceMapResult):
        entries = list(result.entries)
        self.table.setRowCount(len(entries))
        for index, entry in enumerate(entries):
            self.table.setItem(index, 0, QTableWidgetItem(entry.name))
            self.table.setItem(index, 1, QTableWidgetItem(human_size(entry.size_bytes)))
            self.table.setItem(index, 2, QTableWidgetItem("مجلد" if entry.kind == "directory" else "ملف"))

        self.scene.clear()
        visible = entries[:30]
        total = sum(max(1, entry.size_bytes) for entry in visible)
        bounds = QRectF(0, 0, 900, 330)
        for index, (entry, rect) in enumerate(_treemap_rectangles(visible, bounds)):
            tile = QGraphicsRectItem(rect.adjusted(1, 1, -1, -1))
            tile.setBrush(QBrush(_PALETTE[index % len(_PALETTE)]))
            tile.setPen(QPen(QColor("#202020"), 1))
            tile.setToolTip(f"{entry.path}\\n{human_size(entry.size_bytes)}")
            self.scene.addItem(tile)
            if rect.width() >= 78 and rect.height() >= 42:
                label = QGraphicsTextItem(f"{entry.name}\\n{human_size(entry.size_bytes)}")
                label.setDefaultTextColor(QColor("white"))
                label.setPos(rect.x() + 5, rect.y() + 4)
                label.setTextWidth(max(20, rect.width() - 10))
                self.scene.addItem(label)
        self.scene.setSceneRect(bounds)
        status = (
            f"العناصر المفحوصة: {result.scanned_entries} | "
            f"العناصر المعروضة: {len(visible)} | "
            f"المستبعدة/المتعذرة: {result.skipped_entries}"
        )
        if result.truncated:
            status += " | النتائج جزئية بسبب حد الفحص"
        self.status.setText(status)
