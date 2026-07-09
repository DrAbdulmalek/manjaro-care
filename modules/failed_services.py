#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/failed_services.py
============================
يكتشف خدمات systemd الفاشلة (systemctl --failed) ويقترح إعادة تشغيلها
أو عرض سجلّها. هذه الوحدة تعطي "شعور ذكاء" فوري للمستخدم القادم من
Windows، حيث لا يوجد مكافئ مباشر ومرئي لهذا في واجهة سطح المكتب.

الفحص آمن تماماً (قراءة فقط). التطبيق (restart) يحتاج جذر لأنه systemctl
restart، لكن هذا إجراء اعتيادي ومنخفض الخطورة (safe) لأنه لا يحذف شيئاً.
"""

from __future__ import annotations

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("failed_services")


def _get_failed_units() -> list[str]:
    result = run_unprivileged(
        ["systemctl", "--failed", "--no-legend", "--plain"]
    )
    if not result.stdout.strip():
        return []
    units = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            units.append(parts[0])
    return units


class FailedServicesModule(MaintenanceModule):
    name = "الخدمات الفاشلة"
    slug = "failed_services"
    description = "كشف خدمات systemd المتوقفة عن العمل بسبب خطأ، واقتراح إعادة تشغيلها"
    needs_root = True
    risk_level = RiskLevel.SAFE  # إعادة تشغيل خدمة لا تحذف شيئاً
    icon = "dialog-warning"

    def scan(self) -> ScanResult:
        units = _get_failed_units()
        findings: list[ScanFinding] = []

        if units:
            findings.append(ScanFinding(
                title=f"{len(units)} خدمة نظام متوقفة بخطأ",
                detail="خدمات systemd في حالة failed:\n" + "\n".join(units),
                severity=Severity.CRITICAL if len(units) > 2 else Severity.WARNING,
                raw_value=units,
            ))
        else:
            findings.append(ScanFinding(
                title="كل خدمات النظام تعمل بشكل طبيعي",
                detail="لا توجد خدمات systemd فاشلة حالياً.",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        units = _get_failed_units()
        return [
            PreviewStep(
                description=f"إعادة تشغيل الخدمة: {unit}",
                command=f"systemctl restart {unit}",
            )
            for unit in units
        ]

    def apply(self) -> ApplyResult:
        units = _get_failed_units()
        if not units:
            return ApplyResult(success=True, message="لا توجد خدمات لإعادة تشغيلها")

        logs = []
        failed_restarts = []
        for unit in units:
            result = run_privileged(["systemctl", "restart", unit])
            logs.append(f"$ systemctl restart {unit}\n{result.stdout}{result.stderr}")
            if not result.ok:
                failed_restarts.append(unit)

        if failed_restarts:
            hint = (" — بعض الخدمات (مثل tlp) تفشل إعادة تشغيلها لأسباب بنيوية "
                    "ولا تحتاج تدخلاً، راجع: journalctl -u <اسم_الخدمة> -n 20")
            return ApplyResult(
                success=False,
                message=f"فشلت إعادة تشغيل: {', '.join(failed_restarts)}{hint}",
                log_output="\n".join(logs),
            )

        return ApplyResult(
            success=True,
            message=f"تمت إعادة تشغيل {len(units)} خدمة بنجاح",
            log_output="\n".join(logs),
        )
