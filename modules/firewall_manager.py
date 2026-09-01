#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/firewall_manager.py — إدارة الجدار الناري."""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("firewall_manager")


def _detect_firewall():
    if shutil.which("firewalld") or shutil.which("firewall-cmd"):
        return "firewalld"
    if shutil.which("ufw"):
        return "ufw"
    return None


def _firewalld_status():
    result = run_unprivileged(["systemctl", "is-active", "firewalld"])
    active = result.ok and result.stdout.strip() == "active"
    zones = []
    if active:
        z = run_unprivileged(["firewall-cmd", "--get-active-zones"])
        zones = [line.strip() for line in z.stdout.splitlines() if line.strip() and not line.startswith("  ")]
    return active, zones


def _ufw_status():
    result = run_unprivileged(["ufw", "status", "verbose"])
    active = "Status: active" in result.stdout
    return active, result.stdout


class FirewallManagerModule(MaintenanceModule):
    name = "إدارة الجدار الناري"
    slug = "firewall_manager"
    description = "فحص حالة firewalld/ufw وتفعيله أو تعطيله حسب الحاجة"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "security-high"
    has_custom_ui = True

    def scan(self):
        fw = _detect_firewall()
        findings = []

        if not fw:
            findings.append(ScanFinding(
                title="لا يوجد جدار ناري مثبت",
                detail="ثبّت firewalld أو ufw إن أردت حماية إضافية.",
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        if fw == "firewalld":
            active, zones = _firewalld_status()
            if active:
                findings.append(ScanFinding(
                    title=f"firewalld نشط — المناطق: {', '.join(zones) or 'افتراضية'}",
                    detail="الجدار الناري يعمل. يمكنك تعطيله مؤقتاً إن واجهت مشاكل شبكة.",
                    severity=Severity.OK,
                    actionable=True,
                    raw_value="firewalld",
                ))
            else:
                findings.append(ScanFinding(
                    title="firewalld متوقف",
                    detail="الجدار الناري غير نشط — النظام غير محمي.",
                    severity=Severity.WARNING,
                    actionable=True,
                    raw_value="firewalld",
                ))
        else:
            active, text = _ufw_status()
            if active:
                findings.append(ScanFinding(
                    title="ufw نشط",
                    detail="الجدار الناري يعمل.",
                    severity=Severity.OK,
                    actionable=True,
                    raw_value="ufw",
                ))
            else:
                findings.append(ScanFinding(
                    title="ufw متوقف",
                    detail="الجدار الناري غير نشط — النظام غير محمي.",
                    severity=Severity.WARNING,
                    actionable=True,
                    raw_value="ufw",
                ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [PreviewStep(
            description="إدارة الجدار الناري تتم عبر نافذة مخصصة (زر «إدارة فردية»).",
        )]

    def apply(self):
        return ApplyResult(
            success=True,
            message="استخدم زر «إدارة فردية» للتحكم بالجدار الناري.",
        )
