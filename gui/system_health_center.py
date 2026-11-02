#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""واجهة مركز صحة النظام الموحد — عرض نتائج الفحص الحالي فقط."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from core.module_base import Severity
from core.scanner import SystemHealthReport
from gui.health_sections import build_health_sections

_LABELS = {
    Severity.CRITICAL: "حرج",
    Severity.WARNING: "تحذير",
    Severity.INFO: "معلومة",
    Severity.OK: "سليم",
}


class SystemHealthCenter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["القسم / النتيجة", "الحالة"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setMinimumHeight(145)
        self.tree.setMaximumHeight(250)
        layout.addWidget(self.tree)
        self.tree.hide()

    def render_report(self, report: SystemHealthReport) -> None:
        self.tree.clear()
        sections = build_health_sections(report)
        if not sections:
            root = QTreeWidgetItem(["لم تُسجّل نتائج أو تنبيهات", "—"])
            self.tree.addTopLevelItem(root)
        for section in sections:
            critical, warning = section["critical"], section["warning"]
            state = f"{critical} حرج · {warning} تحذير" if critical or warning else "لا تحذيرات"
            parent = QTreeWidgetItem([section["title"], state])
            self.tree.addTopLevelItem(parent)
            for finding in section["findings"]:
                label = _LABELS[finding.severity]
                child = QTreeWidgetItem([finding.title, label])
                child.setToolTip(0, finding.detail or finding.title)
                child.setToolTip(1, finding.detail or label)
                parent.addChild(child)
            parent.setExpanded(bool(critical or warning))
        self.tree.show()
