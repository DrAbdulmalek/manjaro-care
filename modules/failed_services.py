#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""كشف خدمات systemd الفاشلة دون إعادة تشغيل جماعية غير آمنة."""
from __future__ import annotations

from core.module_base import (
    ApplyResult,
    MaintenanceModule,
    PreviewStep,
    RiskLevel,
    ScanFinding,
    ScanResult,
    Severity,
)
from core.privilege import run_unprivileged


def _get_failed_units() -> list[str]:
    result = run_unprivileged(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
    if not result.ok:
        return []
    return [line.split()[0] for line in result.stdout.splitlines() if line.split()]


class FailedServicesModule(MaintenanceModule):
    name = "الخدمات الفاشلة"
    slug = "failed_services"
    description = "كشف خدمات systemd الفاشلة وعرض أوامر فحص سجلاتها دون إعادة تشغيل تلقائي"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "dialog-warning"

    def scan(self) -> ScanResult:
        result = run_unprivileged(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
        if not result.ok:
            return ScanResult(
                module_name=self.name,
                findings=[ScanFinding(
                    title="تعذر قراءة حالة خدمات systemd",
                    detail=result.stderr.strip() or "فشل systemctl --failed.",
                    severity=Severity.INFO,
                    actionable=False,
                )],
                error=result.stderr.strip() or "systemctl failed",
            )
        units = [line.split()[0] for line in result.stdout.splitlines() if line.split()]
        if units:
            finding = ScanFinding(
                title=f"{len(units)} خدمة systemd في حالة failed",
                detail=(
                    "افحص كل خدمة منفردة قبل اتخاذ قرار. لا يُنصح بإعادة تشغيل جميع الخدمات "
                    "دفعة واحدة؛ قد تكون بعض الحالات متوقعة أو غير قابلة لإعادة التشغيل.\n"
                    + "\n".join(f"journalctl -u {unit} -n 40 --no-pager" for unit in units)
                ),
                severity=Severity.WARNING,
                actionable=False,
                raw_value=units,
            )
        else:
            finding = ScanFinding(
                title="لا توجد خدمات systemd فاشلة",
                detail="",
                severity=Severity.OK,
                actionable=False,
            )
        return ScanResult(module_name=self.name, findings=[finding])

    def preview(self) -> list[PreviewStep]:
        units = _get_failed_units()
        if not units:
            return [PreviewStep(description="لا توجد خدمات فاشلة أو تعذر قراءتها؛ لم يُقترح أي تغيير.")]
        return [
            PreviewStep(
                description=f"عرض آخر 40 سطراً من سجل {unit} (قراءة فقط)",
                command=f"journalctl -u {unit} -n 40 --no-pager",
            )
            for unit in units
        ]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="لم تُعَد تشغيل أي خدمة. افحص سجل الخدمة المحددة ثم قرر الإجراء يدوياً.",
        )
