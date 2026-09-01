#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/boot_manager.py
========================
فحص إعدادات الإقلاع (GRUB) — هل grub-mkconfig محدّث؟ هل يوجد نواة بديلة؟
مستوحى من Garuda Assistant → Boot Options.
"""
from __future__ import annotations
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("boot_manager")

_GRUB_CFG = Path("/boot/grub/grub.cfg")
_GRUB_DEFAULT = Path("/etc/default/grub")


def _grub_entries() -> list[str]:
    """يستخرج أسماء إدخالات GRUB من grub.cfg."""
    if not _GRUB_CFG.exists():
        return []
    text = _GRUB_CFG.read_text(encoding="utf-8", errors="ignore")
    entries = []
    for line in text.splitlines():
        if line.strip().startswith("menuentry '"):
            name = line.split("'", 2)[1] if "'" in line else ""
            if name:
                entries.append(name)
    return entries


def _grub_timeout() -> int:
    """يقرأ timeout من /etc/default/grub."""
    if not _GRUB_DEFAULT.exists():
        return -1
    for line in _GRUB_DEFAULT.read_text().splitlines():
        if line.strip().startswith("GRUB_TIMEOUT="):
            try:
                return int(line.split("=", 1)[1].strip().strip('"'))
            except ValueError:
                return -1
    return -1


class BootManagerModule(MaintenanceModule):
    name = "إدارة الإقلاع (GRUB)"
    slug = "boot_manager"
    description = "فحص إعدادات GRUB وعدد إدخالات الإقلاع المتاحة"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "drive-harddisk-system"

    def scan(self) -> ScanResult:
        entries = _grub_entries()
        timeout = _grub_timeout()
        findings: list[ScanFinding] = []

        if not entries:
            findings.append(ScanFinding(
                title="لم يُعثر على grub.cfg",
                detail="قد يكون النظام يستخدم systemd-boot بدل GRUB.",
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        findings.append(ScanFinding(
            title=f"{len(entries)} إدخال/إدخالات إقلاع",
            detail="\n".join(f"  • {e}" for e in entries[:10]),
            severity=Severity.INFO,
            actionable=False,
            raw_value=entries,
        ))

        if timeout == 0:
            findings.append(ScanFinding(
                title="GRUB timeout = 0",
                detail="لا يمكنك اختيار نواة بديلة عند الإقلاع — يُنصح بـ 5 ثوانٍ على الأقل.",
                severity=Severity.WARNING,
                actionable=True,
            ))
        elif timeout > 30:
            findings.append(ScanFinding(
                title=f"GRUB timeout طويل ({timeout} ثانية)",
                detail="يمكن تقليصه لتسريع الإقلاع.",
                severity=Severity.INFO,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        timeout = _grub_timeout()
        steps = []
        if timeout == 0:
            steps.append(PreviewStep(
                description="تعيين GRUB_TIMEOUT إلى 5 ثوانٍ",
                command="sed -i 's/GRUB_TIMEOUT=.*/GRUB_TIMEOUT=5/' /etc/default/grub && grub-mkconfig -o /boot/grub/grub.cfg",
            ))
        elif timeout > 30:
            steps.append(PreviewStep(
                description="تعيين GRUB_TIMEOUT إلى 5 ثوانٍ",
                command="sed -i 's/GRUB_TIMEOUT=.*/GRUB_TIMEOUT=5/' /etc/default/grub && grub-mkconfig -o /boot/grub/grub.cfg",
            ))
        steps.append(PreviewStep(
            description="إعادة توليد إعدادات GRUB",
            command="grub-mkconfig -o /boot/grub/grub.cfg",
        ))
        return steps or [PreviewStep(description="لا إجراء مطلوب.")]

    def apply(self) -> ApplyResult:
        timeout = _grub_timeout()
        logs = []

        if timeout == 0 or timeout > 30:
            r1 = run_privileged(["bash", "-c", "sed -i 's/GRUB_TIMEOUT=.*/GRUB_TIMEOUT=5/' /etc/default/grub"])
            logs.append(r1.stdout + r1.stderr)

        r2 = run_privileged(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
        logs.append(r2.stdout + r2.stderr)

        return ApplyResult(
            success=r2.ok,
            message="تم تحديث إعدادات GRUB" if r2.ok else "فشل تحديث GRUB",
            log_output="\n".join(logs),
        )
