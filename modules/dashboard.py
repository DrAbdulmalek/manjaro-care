#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/dashboard.py — وحدة لوحة القيادة."""
from __future__ import annotations
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.logger import get_logger

log = get_logger("dashboard")


class DashboardModule(MaintenanceModule):
    name = "لوحة قيادة النظام"
    slug = "dashboard"
    description = "عرض إحصائيات حية ورسوم بيانية لأداء النظام"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "utilities-system-monitor"
    has_custom_ui = True

    def scan(self):
        return ScanResult(
            module_name=self.name,
            findings=[
                ScanFinding(
                    title="لوحة القيادة التفاعلية",
                    detail="انقر «إدارة فردية» لفتح الرسوم البيانية الحية.",
                    severity=Severity.INFO,
                    actionable=True,
                )
            ],
        )

    def preview(self):
        return [PreviewStep(description="فتح لوحة القيادة التفاعلية.")]

    def apply(self):
        return ApplyResult(
            success=True,
            message="استخدم زر «إدارة فردية» لفتح لوحة القيادة.",
        )
