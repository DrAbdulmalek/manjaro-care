#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/journal_vacuum.py
===========================
تقليص سجلات systemd journal التي تتضخم بمرور الوقت (خصوصاً مع
persistent journal المفعّل افتراضياً في مانجارو).

الفحص: journalctl --disk-usage (قراءة فقط).
التطبيق: journalctl --vacuum-size=<حد> — يحذف أقدم السجلات حتى يصل
الحجم للحد المطلوب. الحد الافتراضي هنا 300M (متوازن: يبقي أسابيع من
السجلات لتشخيص المشاكل، ويوفر مساحة حقيقية إن كان الحجم الحالي كبيراً).
"""

from __future__ import annotations
import re

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("journal_vacuum")

# الحد الذي نُبقي عليه بعد التقليص — متوازن بين توفير المساحة والاحتفاظ بتاريخ كافٍ للتشخيص
_TARGET_SIZE = "300M"
_WARN_THRESHOLD_MB = 500
_CRITICAL_THRESHOLD_MB = 1500


def _get_journal_size_mb() -> float:
    result = run_unprivileged(["journalctl", "--disk-usage"])
    if not result.ok:
        return 0.0
    # المخرج عادة: "Archived and active journals take up 512.0M in the file system."
    match = re.search(r"([\d.]+)\s*([KMGT])", result.stdout)
    if not match:
        return 0.0
    value, unit = float(match.group(1)), match.group(2)
    multipliers = {"K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}
    return value * multipliers.get(unit, 1)


class JournalVacuumModule(MaintenanceModule):
    name = "تقليص سجلات systemd"
    slug = "journal_vacuum"
    description = f"يقلّص journal إلى {_TARGET_SIZE} مع الإبقاء على أحدث السجلات للتشخيص"
    needs_root = True
    risk_level = RiskLevel.MODERATE  # يحذف سجلات قديمة نهائياً — لا تراجع
    icon = "text-x-generic"

    def scan(self) -> ScanResult:
        size_mb = _get_journal_size_mb()
        findings: list[ScanFinding] = []

        if size_mb >= _CRITICAL_THRESHOLD_MB:
            findings.append(ScanFinding(
                title=f"سجلات النظام كبيرة جداً: {size_mb:.0f} MB",
                detail=f"يُنصح بالتقليص إلى {_TARGET_SIZE} لتحرير مساحة القرص.",
                severity=Severity.CRITICAL,
                raw_value=size_mb,
            ))
        elif size_mb >= _WARN_THRESHOLD_MB:
            findings.append(ScanFinding(
                title=f"حجم سجلات النظام: {size_mb:.0f} MB",
                detail=f"يمكن تقليصه إلى {_TARGET_SIZE} إن احتجت مساحة إضافية.",
                severity=Severity.WARNING,
                raw_value=size_mb,
            ))
        else:
            findings.append(ScanFinding(
                title=f"حجم سجلات النظام طبيعي: {size_mb:.0f} MB",
                detail="لا حاجة للتقليص حالياً.",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description=f"تقليص journal إلى {_TARGET_SIZE} (حذف أقدم السجلات فقط)",
            command=f"journalctl --vacuum-size={_TARGET_SIZE}",
        )]

    def apply(self) -> ApplyResult:
        result = run_privileged(["journalctl", f"--vacuum-size={_TARGET_SIZE}"])
        if result.ok:
            return ApplyResult(
                success=True,
                message=f"تم تقليص السجلات إلى {_TARGET_SIZE}",
                log_output=result.stdout + result.stderr,
            )
        return ApplyResult(
            success=False,
            message=f"فشل التقليص (كود {result.returncode})",
            log_output=result.stdout + result.stderr,
        )
