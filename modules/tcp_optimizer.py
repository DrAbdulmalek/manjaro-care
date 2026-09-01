#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/tcp_optimizer.py — تحسين إعدادات الشبكة والإنترنت."""
from __future__ import annotations
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("tcp_optimizer")


def _get_current_tcp_settings():
    settings = {}
    for param in ["net.ipv4.tcp_fastopen", "net.core.rmem_max", "net.core.wmem_max",
                  "net.ipv4.tcp_congestion_control", "net.ipv4.tcp_notsent_lowat"]:
        r = run_unprivileged(["sysctl", "-n", param])
        settings[param] = r.stdout.strip() if r.ok else "غير معروف"
    return settings


class TcpOptimizerModule(MaintenanceModule):
    name = "تحسين الإنترنت 🌐"
    slug = "tcp_optimizer"
    description = "تحسين إعدادات TCP للألعاب والتنزيلات السريعة"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "network-workgroup"

    def scan(self):
        settings = _get_current_tcp_settings()
        findings = []

        cc = settings.get("net.ipv4.tcp_congestion_control", "")
        if cc != "bbr":
            findings.append(ScanFinding(
                title=f"خوارزمية التحكم: {cc}",
                detail="يُنصح بـ BBR لتحسين سرعة التنزيل والألعاب.",
                severity=Severity.INFO,
                actionable=True,
            ))
        else:
            findings.append(ScanFinding(
                title="BBR مفعّل ✅",
                detail="أفضل خوارزمية للتحكم في الازدحام.",
                severity=Severity.OK,
                actionable=False,
            ))

        fastopen = settings.get("net.ipv4.tcp_fastopen", "0")
        if fastopen == "0":
            findings.append(ScanFinding(
                title="TCP Fast Open معطّل",
                detail="تفعيله يُسرّع فتح المواقع.",
                severity=Severity.INFO,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [
            PreviewStep(description="تفعيل BBR", command="sysctl -w net.ipv4.tcp_congestion_control=bbr"),
            PreviewStep(description="تفعيل TCP Fast Open", command="sysctl -w net.ipv4.tcp_fastopen=3"),
            PreviewStep(description="زيادة buffer الشبكة", command="sysctl -w net.core.rmem_max=134217728 net.core.wmem_max=134217728"),
        ]

    def apply(self):
        logs = []
        cmds = [
            "sysctl -w net.ipv4.tcp_congestion_control=bbr",
            "sysctl -w net.ipv4.tcp_fastopen=3",
            "sysctl -w net.core.rmem_max=134217728",
            "sysctl -w net.core.wmem_max=134217728",
            "sysctl -w net.ipv4.tcp_notsent_lowat=16384",
        ]
        for cmd in cmds:
            r = run_privileged(["bash", "-c", cmd])
            logs.append(r.stdout + r.stderr)

        # جعلها دائمة
        sysctl_conf = "/etc/sysctl.d/99-network-tune.conf"
        conf_text = "\n".join([
            "net.ipv4.tcp_congestion_control=bbr",
            "net.ipv4.tcp_fastopen=3",
            "net.core.rmem_max=134217728",
            "net.core.wmem_max=134217728",
            "net.ipv4.tcp_notsent_lowat=16384",
        ])
        r = run_privileged(["bash", "-c", f"cat > {sysctl_conf} << 'EOF'\n{conf_text}\nEOF"])
        logs.append(r.stdout + r.stderr)

        return ApplyResult(
            success=True,
            message="تم تحسين شبكة الإنترنت 🚀",
            log_output="\n".join(logs),
        )
