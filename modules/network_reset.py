#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/network_reset.py
==========================
تغليف reset-net (الأداة الموجودة فعلاً على النظام) كوحدة ضمن
manjaro-care. هذه الوحدة لا تُعيد تنفيذ منطق reset-net — بل تستدعي
الثنائي /usr/local/bin/reset-net أو /usr/bin/reset-net مباشرة عبر
pkexec، تماماً كما يفعل reset-net-tray الحالي.

هذا يثبت أن بنية manjaro-care تستوعب أدوات خارجية جاهزة بسهولة، لا
فقط منطقاً مكتوباً من الصفر.

ملاحظة: هذه الوحدة "خاصة" — scan() لا يفحص شيئاً في النظام، بل يتحقق
فقط من وجود reset-net نفسه؛ لأن مشكلة الشبكة بعد فصل VPN لا يمكن
اكتشافها موثوقاً بفحص سلبي (قد يكون الاتصال يعمل فعلاً). لذلك تُعرض
كأداة "شغّلها عند الحاجة" لا كاقتراح تلقائي — نفس فلسفة الأيقونة في
علبة النظام.
"""

from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged
from core.logger import get_logger

log = get_logger("network_reset")


def _find_reset_net_binary() -> str | None:
    for path in ("/usr/local/bin/reset-net", "/usr/bin/reset-net"):
        if shutil.which(path) or __import__("os").path.isfile(path):
            return path
    return None


class NetworkResetModule(MaintenanceModule):
    name = "إعادة ضبط الشبكة"
    slug = "network_reset"
    description = "يصلح مشاكل الاتصال بعد فصل Outline VPN (iptables، DNS، المسارات، TUN)"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "network-wired"

    def scan(self) -> ScanResult:
        binary = _find_reset_net_binary()
        findings: list[ScanFinding] = []

        if binary:
            findings.append(ScanFinding(
                title="أداة reset-net متوفرة",
                detail=f"جاهزة للتشغيل عند الحاجة (بعد فصل VPN مثلاً): {binary}",
                severity=Severity.OK,
                actionable=True,   # قابلة للتشغيل اليدوي رغم أنها ليست "مشكلة"
            ))
        else:
            findings.append(ScanFinding(
                title="أداة reset-net غير مثبتة",
                detail="ثبّتها عبر AUR (yay -S reset-net) أو install.sh من مستودع المشروع.",
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        binary = _find_reset_net_binary() or "reset-net"
        return [PreviewStep(
            description="تشغيل reset-net لإعادة ضبط إعدادات الشبكة (iptables/DNS/المسارات/TUN)",
            command=binary,
        )]

    def apply(self) -> ApplyResult:
        binary = _find_reset_net_binary()
        if not binary:
            return ApplyResult(success=False, message="reset-net غير مثبت على هذا النظام")

        result = run_privileged([binary])
        if result.ok:
            return ApplyResult(
                success=True,
                message="تمت إعادة ضبط الشبكة بنجاح",
                log_output=result.stdout + result.stderr,
            )
        return ApplyResult(
            success=False,
            message=f"فشلت إعادة الضبط (كود {result.returncode}) — راجع /var/log/reset-net.log",
            log_output=result.stdout + result.stderr,
        )
