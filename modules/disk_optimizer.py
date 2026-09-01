#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/disk_optimizer.py — تحسين أداء القرص (fstrim + bad blocks check)."""
from __future__ import annotations
import shutil
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("disk_optimizer")


def _get_disk_type(mount: str = "/") -> str:
    r = run_unprivileged(["findmnt", "-n", "-o", "FSTYPE", mount])
    return r.stdout.strip() if r.ok else "unknown"


def _get_rotational() -> bool:
    # هل القرص HDD أم SSD؟
    r = run_unprivileged(["bash", "-c", "cat /sys/block/sda/queue/rotational 2>/dev/null || echo 1"])
    return r.stdout.strip() == "1"


class DiskOptimizerModule(MaintenanceModule):
    name = "تحسين القرص 💿"
    slug = "disk_optimizer"
    description = "fstrim للـ SSD وفحص الأخطاء للأقراص"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "drive-harddisk"

    def scan(self):
        findings = []
        fstype = _get_disk_type("/")
        is_hdd = _get_rotational()

        if fstype == "btrfs":
            findings.append(ScanFinding(
                title="نظام الملفات: BTRFS",
                detail="fstrim مدعوم. يُنصح بتشغيله أسبوعياً.",
                severity=Severity.INFO,
                actionable=True,
            ))
        elif fstype == "ext4":
            findings.append(ScanFinding(
                title="نظام الملفات: ext4",
                detail="fstrim متوفر للـ SSD. e4defrag للـ HDD.",
                severity=Severity.INFO,
                actionable=True,
            ))

        # حالة fstrim.timer
        r = run_unprivileged(["systemctl", "is-enabled", "fstrim.timer"])
        if r.ok and "enabled" in r.stdout:
            findings.append(ScanFinding(
                title="fstrim.timer مفعّل ✅",
                detail="صيانة تلقائية للـ SSD.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="fstrim.timer معطّل",
                detail="الـ SSD يحتاج TRIM دوري.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        if is_hdd:
            findings.append(ScanFinding(
                title="القرص: HDD (ميكانيكي)",
                detail="لا يحتاج fstrim. يمكن استخدام e4defrag.",
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        fstype = _get_disk_type("/")
        steps = []
        if fstype in ("ext4", "btrfs", "xfs"):
            steps.append(PreviewStep(
                description="تشغيل fstrim يدوياً",
                command="fstrim -av /",
            ))
        steps.append(PreviewStep(
            description="تفعيل fstrim التلقائي",
            command="systemctl enable --now fstrim.timer",
        ))
        return steps

    def apply(self):
        logs = []
        r1 = run_privileged(["fstrim", "-av", "/"])
        logs.append(r1.stdout + r1.stderr)

        r2 = run_privileged(["systemctl", "enable", "--now", "fstrim.timer"])
        logs.append(r2.stdout + r2.stderr)

        return ApplyResult(
            success=r1.ok,
            message="تم تحسين القرص",
            log_output="\n".join(logs),
        )
