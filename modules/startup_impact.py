#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/startup_impact.py — تحليل تأثير خدمات بدء التشغيل."""
from __future__ import annotations
import re
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("startup_impact")


def _systemd_analyze_blame():
    r = run_unprivileged(["systemd-analyze", "blame"])
    services = []
    if r.ok:
        for line in r.stdout.splitlines()[:15]:
            line = line.strip()
            if line:
                # تنسيق: 1.234s service-name.service
                parts = line.split()
                if len(parts) >= 2:
                    time_str = parts[0]
                    svc = parts[1]
                    services.append((time_str, svc))
    return services


def _systemd_analyze_critical_chain():
    r = run_unprivileged(["systemd-analyze", "critical-chain"])
    return r.stdout if r.ok else ""


class StartupImpactModule(MaintenanceModule):
    name = "تحليل تأثير الإقلاع ⏱️"
    slug = "startup_impact"
    description = "يعرض الخدمات الأبطأ في بدء التشغيل عبر systemd-analyze"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "chronometer"

    def scan(self):
        findings = []
        blame = _systemd_analyze_blame()
        total_boot = run_unprivileged(["systemd-analyze"]).stdout.strip()

        if total_boot:
            findings.append(ScanFinding(
                title=f"وقت الإقلاع الإجمالي: {total_boot}",
                detail="",
                severity=Severity.INFO,
                actionable=False,
            ))

        if blame:
            slowest = blame[:5]
            detail = "\n".join(f"  • {svc}: {t}" for t, svc in slowest)
            findings.append(ScanFinding(
                title=f"{len(blame)} خدمة تبطئ الإقلاع",
                detail=detail,
                severity=Severity.WARNING if any("s" in t and float(t.replace("s","")) > 5 for t,_ in slowest) else Severity.INFO,
                actionable=True,
                raw_value=blame,
            ))
        else:
            findings.append(ScanFinding(
                title="لا بيانات عن الإقلاع",
                detail="قد يكون systemd-analyze غير متوفر.",
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [PreviewStep(
            description="تعطيل الخدمات البطيئة غير الضرورية عبر systemctl disable",
        )]

    def apply(self):
        return ApplyResult(
            success=True,
            message="استخدم Startup Manager لتعطيل الخدمات البطيئة.",
        )
