#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/firewall_manager.py
============================
إدارة الجدار الناري — firewalld أو ufw.
يعرض الحالة الحالية ويقترح تفعيل/تعطيل أو إضافة قواعد أساسية.
مستوحى من Garuda Assistant → Firewall.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("firewall_manager")


def _detect_firewall() -> str | None:
    """يكتشف أي جدار ناري مثبت: 'firewalld' أو 'ufw' أو None."""
    if shutil.which("firewalld") or shutil.which("firewall-cmd"):
        return "firewalld"
    if shutil.which("ufw"):
        return "ufw"
    return None


def _firewalld_status() -> tuple[bool, list[str]]:
    """(نشط؟, قائمة zones المفتوحة)."""
    result = run_unprivileged(["systemctl", "is-active", "firewalld"])
    active = result.ok and result.stdout.strip() == "active"
    zones = []
    if active:
        z = run_unprivileged(["firewall-cmd", "--get-active-zones"])
        zones = [line.strip() for line in z.stdout.splitlines() if line.strip() and not line.startswith("  ")]
    return active, zones


def _ufw_status() -> tuple[bool, str]:
    """(نشط؟, نص الحالة)."""
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

    def scan(self) -> ScanResult:
        fw = _detect_firewall()
        findings: list[ScanFinding] = []

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
        else:  # ufw
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

    def preview(self) -> list[PreviewStep]:
        fw = _detect_firewall()
        if not fw:
            return [PreviewStep(description="لا يوجد جدار ناري مثبت — لا إجراء.")]

        if fw == "firewalld":
            active, _ = _firewalld_status()
            if active:
                return [PreviewStep(
                    description="إيقاف firewalld",
                    command="systemctl stop firewalld",
                )]
            return [PreviewStep(
                description="تشغيل firewalld وتفعيله عند الإقلاع",
                command="systemctl enable --now firewalld",
            )]
        else:
            active, _ = _ufw_status()
            if active:
                return [PreviewStep(description="تعطيل ufw", command="ufw disable")]
            return [PreviewStep(description="تفعيل ufw", command="ufw enable")]

    def apply(self) -> ApplyResult:
        fw = _detect_firewall()
        if not fw:
            return ApplyResult(success=True, message="لا يوجد جدار ناري مثبت.")

        if fw == "firewalld":
            active, _ = _firewalld_status()
            if active:
                result = run_privileged(["systemctl", "stop", "firewalld"])
                return ApplyResult(
                    success=result.ok,
                    message="تم إيقاف firewalld" if result.ok else f"فشل (كود {result.returncode})",
                    log_output=result.stdout + result.stderr,
                )
            result = run_privileged(["systemctl", "enable", "--now", "firewalld"])
            return ApplyResult(
                success=result.ok,
                message="تم تفعيل firewalld" if result.ok else f"فشل (كود {result.returncode})",
                log_output=result.stdout + result.stderr,
            )
        else:
            active, _ = _ufw_status()
            cmd = "disable" if active else "enable"
            result = run_privileged(["ufw", "--force", cmd])
            return ApplyResult(
                success=result.ok,
                message=f"تم {cmd} ufw" if result.ok else f"فشل (كود {result.returncode})",
                log_output=result.stdout + result.stderr,
            )
