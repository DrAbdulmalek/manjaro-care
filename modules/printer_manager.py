#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/printer_manager.py
===========================
فحص حالة CUPS والطابعات المتصلة.
وحدة إخبارية بحتة.
مستوحى من Garuda Assistant → Printer & Scanner.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("printer_manager")


def _cups_status() -> tuple[bool, str]:
    r = run_unprivileged(["systemctl", "is-active", "cups"])
    active = r.ok and r.stdout.strip() == "active"
    printers = run_unprivileged(["lpstat", "-p"])
    return active, printers.stdout


class PrinterManagerModule(MaintenanceModule):
    name = "الطابعات والمسح"
    slug = "printer_manager"
    description = "فحص حالة CUPS والطابعات المتصلة — إخباري فقط"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "printer"

    def scan(self) -> ScanResult:
        active, printers = _cups_status()
        findings: list[ScanFinding] = []

        if not shutil.which("cupsd"):
            findings.append(ScanFinding(
                title="CUPS غير مثبت",
                detail="ثبّت cups و system-config-printer لدعم الطباعة.",
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        if active:
            findings.append(ScanFinding(
                title="CUPS يعمل",
                detail=printers or "لا طابعات مضافة حالياً.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="CUPS متوقف",
                detail="خدمة الطباعة غير نشطة.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="تشغيل CUPS: systemctl start cups")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="استخدم systemctl start cups يدوياً إن احتجت.")
