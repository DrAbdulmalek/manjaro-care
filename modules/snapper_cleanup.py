#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/snapper_cleanup.py
===========================
تقليص snapshots القديمة عبر snapper cleanup.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged
from core.logger import get_logger

log = get_logger("snapper_cleanup")


class SnapperCleanupModule(MaintenanceModule):
    name = "تنظيف Snapshots القديمة"
    slug = "snapper_cleanup"
    description = "تشغيل snapper cleanup لتقليص snapshots القديمة (number/timeline)"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "edit-clear-history"

    def scan(self) -> ScanResult:
        if not shutil.which("snapper"):
            return ScanResult(
                module_name=self.name,
                findings=[ScanFinding(
                    title="snapper غير مثبت",
                    detail="",
                    severity=Severity.INFO,
                    actionable=False,
                )],
            )
        return ScanResult(
            module_name=self.name,
            findings=[ScanFinding(
                title="snapper مثبت",
                detail="يمكن تشغيل cleanup يدوياً لتقليص snapshots القديمة.",
                severity=Severity.INFO,
                actionable=True,
            )],
        )

    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(description="تنظيف snapshots حسب number", command="snapper -c root cleanup number"),
            PreviewStep(description="تنظيف snapshots حسب timeline", command="snapper -c root cleanup timeline"),
        ]

    def apply(self) -> ApplyResult:
        logs = []
        r1 = run_privileged(["snapper", "-c", "root", "cleanup", "number"])
        logs.append(r1.stdout + r1.stderr)
        r2 = run_privileged(["snapper", "-c", "root", "cleanup", "timeline"])
        logs.append(r2.stdout + r2.stderr)
        return ApplyResult(
            success=r1.ok or r2.ok,
            message="تم تنظيف snapshots",
            log_output="\n".join(logs),
        )
