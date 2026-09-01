#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/time_manager.py
========================
فحص الوقت والمنطقة الزمنية — هل NTP مفعّل؟ هل الساعة متزامنة؟
مستوحى من Garuda Assistant → Time & Date.
"""
from __future__ import annotations

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("time_manager")


def _time_status() -> tuple[str, bool, bool]:
    """(المنطقة الزمنية, NTP مفعّل؟, RTC في التوقيت المحلي؟)."""
    result = run_unprivileged(["timedatectl", "status"])
    text = result.stdout
    tz = ""
    ntp = False
    rtc_local = False
    for line in text.splitlines():
        if "Time zone:" in line:
            tz = line.split(":", 1)[1].strip().split()[0]
        if "NTP service:" in line or "NTP enabled:" in line:
            ntp = "yes" in line.lower()
        if "RTC in local TZ:" in line:
            rtc_local = "yes" in line.lower()
    return tz, ntp, rtc_local


class TimeManagerModule(MaintenanceModule):
    name = "الوقت والمنطقة الزمنية"
    slug = "time_manager"
    description = "فحص NTP والمنطقة الزمنية — يقترح تفعيل التزامن التلقائي"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "preferences-system-time"

    def scan(self) -> ScanResult:
        tz, ntp, rtc_local = _time_status()
        findings: list[ScanFinding] = []

        findings.append(ScanFinding(
            title=f"المنطقة الزمنية: {tz or 'غير معروفة'}",
            detail="",
            severity=Severity.INFO,
            actionable=False,
        ))

        if not ntp:
            findings.append(ScanFinding(
                title="NTP معطّل",
                detail="الساعة لا تتزامن تلقائياً مع الإنترنت — قد تسبب مشاكل شهادات SSL.",
                severity=Severity.WARNING,
                actionable=True,
            ))
        else:
            findings.append(ScanFinding(
                title="NTP مفعّل",
                detail="الساعة تتزامن تلقائياً.",
                severity=Severity.OK,
                actionable=False,
            ))

        if rtc_local:
            findings.append(ScanFinding(
                title="RTC في التوقيت المحلي",
                detail="يُنصح بضبط RTC على UTC لتفادي مشاكل التوقيت الصيفي.",
                severity=Severity.INFO,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        _, ntp, rtc_local = _time_status()
        steps = []
        if not ntp:
            steps.append(PreviewStep(
                description="تفعيل NTP (التزامن التلقائي للوقت)",
                command="timedatectl set-ntp true",
            ))
        if rtc_local:
            steps.append(PreviewStep(
                description="ضبط RTC على UTC",
                command="timedatectl set-local-rtc 0",
            ))
        return steps or [PreviewStep(description="كل إعدادات الوقت صحيحة.")]

    def apply(self) -> ApplyResult:
        _, ntp, rtc_local = _time_status()
        logs = []
        success = True

        if not ntp:
            r = run_privileged(["timedatectl", "set-ntp", "true"])
            logs.append(r.stdout + r.stderr)
            if not r.ok:
                success = False

        if rtc_local:
            r = run_privileged(["timedatectl", "set-local-rtc", "0"])
            logs.append(r.stdout + r.stderr)
            if not r.ok:
                success = False

        return ApplyResult(
            success=success,
            message="تم ضبط إعدادات الوقت" if success else "فشل جزئي",
            log_output="\n".join(logs),
        )
