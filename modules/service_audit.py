#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تدقيق خدمات systemd المتوقفة وبقايا الخدمات المخصصة — قراءة فقط."""
from __future__ import annotations

from pathlib import Path

from core.module_base import (
    ApplyResult, MaintenanceModule, PreviewStep, RiskLevel,
    ScanFinding, ScanResult, Severity,
)
from core.privilege import run_unprivileged


class ServiceAuditModule(MaintenanceModule):
    name = "تدقيق الخدمات وبقاياها"
    slug = "service_audit"
    description = (
        "يعرض خدمات systemd الفاشلة وحالة وحدات التحديث المخصصة المتقاعدة؛ "
        "لا يعيد تشغيل الخدمات ولا يحذف ملفات أو سجلات"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "applications-system"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        failed = run_unprivileged(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
        if failed.ok:
            units = [line.split()[0] for line in failed.stdout.splitlines() if line.split()]
            if units:
                findings.append(ScanFinding(
                    title=f"{len(units)} خدمة systemd في حالة failed",
                    detail=(
                        "لا تُعِد تشغيلها دفعة واحدة؛ قد تكون بعض الحالات متوقعة أو مرتبطة "
                        "بعتاد/إعداد غير مستخدم. افحص سجل كل خدمة أولاً:\n"
                        + "\n".join(f"journalctl -u {unit} -n 40 --no-pager" for unit in units)
                    ),
                    severity=Severity.WARNING if len(units) < 3 else Severity.CRITICAL,
                    actionable=False, raw_value=units,
                ))
            else:
                findings.append(ScanFinding(
                    title="لا توجد خدمات systemd فاشلة",
                    detail="", severity=Severity.OK, actionable=False,
                ))
        else:
            findings.append(ScanFinding(
                title="تعذر قراءة حالة خدمات systemd",
                detail=failed.stderr.strip() or "systemctl --failed لم ينجح.",
                severity=Severity.INFO, actionable=False,
            ))

        unit = run_unprivileged([
            "systemctl", "show", "update_shutdown.service",
            "--property=LoadState", "--property=ActiveState", "--property=FragmentPath", "--no-pager",
        ])
        unit_state = {}
        for line in unit.stdout.splitlines():
            key, sep, value = line.partition("=")
            if sep:
                unit_state[key] = value
        fragment = unit_state.get("FragmentPath", "")
        candidates = [
            Path("/etc/systemd/system/update_shutdown.service"),
            Path("/usr/lib/systemd/system/update_shutdown.service"),
            Path("/lib/systemd/system/update_shutdown.service"),
        ]
        existing = [str(path) for path in candidates if path.exists()]
        script_exists = Path("/usr/local/bin/update_shutdown").exists()
        load_state = unit_state.get("LoadState", "unknown")
        active_state = unit_state.get("ActiveState", "unknown")

        if load_state == "not-found" and not existing:
            detail = "الوحدة غير محمّلة ولا توجد ملفات unit قياسية."
            if script_exists:
                detail += " يوجد سكربت update_shutdown محفوظ؛ وجوده وحده لا يعني أن الخدمة تعمل، ولا يُحذف."
            findings.append(ScanFinding(
                title="update_shutdown.service غير موجودة (متقاعدة)",
                detail=detail, severity=Severity.OK, actionable=False,
            ))
        elif load_state == "loaded" or existing:
            findings.append(ScanFinding(
                title="عُثر على بقايا/وحدة update_shutdown",
                detail=(
                    f"LoadState={load_state}; ActiveState={active_state}; "
                    f"FragmentPath={fragment or 'غير معروف'}\n"
                    + "\n".join(existing)
                    + ("\nيوجد السكربت /usr/local/bin/update_shutdown." if script_exists else "")
                    + "\nهذه نتيجة تدقيق فقط؛ لا تعطيل ولا حذف تلقائي."
                ),
                severity=Severity.WARNING, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="حالة update_shutdown غير محسومة",
                detail=f"LoadState={load_state}; ActiveState={active_state}",
                severity=Severity.INFO, actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="قراءة حالة الخدمات وملفات الوحدة فقط؛ لا توجد أوامر تغيير.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="تدقيق الخدمات للقراءة فقط؛ لم يُعَد تشغيل أي خدمة ولم يُحذف أي ملف.")
