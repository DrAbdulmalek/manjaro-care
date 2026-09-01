#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/btrfs_snapper.py
=========================
فحص snapshots النظام (BTRFS via snapper أو timeshift).
وحدة إخبارية بحتة — الحذف يدوي فقط.
مستوحى من Garuda Assistant → BTRFS Assistant / Snapper.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("btrfs_snapper")


def _has_btrfs_root() -> bool:
    r = run_unprivileged(["findmnt", "-n", "-o", "FSTYPE", "/"])
    return r.stdout.strip() == "btrfs"


def _snapper_list() -> list[tuple[str, str]]:
    """يُرجع قائمة (رقم, وصف)."""
    if not shutil.which("snapper"):
        return []
    r = run_unprivileged(["snapper", "-c", "root", "list"])
    snapshots = []
    for line in r.stdout.splitlines()[2:]:  # تخطي العنوان
        parts = line.split("|")
        if len(parts) >= 4:
            num = parts[0].strip()
            desc = parts[3].strip()
            snapshots.append((num, desc))
    return snapshots


def _timeshift_list() -> str:
    if not shutil.which("timeshift"):
        return ""
    r = run_unprivileged(["timeshift", "--list"])
    return r.stdout


class BtrfsSnapperModule(MaintenanceModule):
    name = "لقطات النظام (Snapshots)"
    slug = "btrfs_snapper"
    description = "فحص لقطات BTRFS عبر snapper/timeshift — للاطلاع فقط"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "drive-multidisk"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        if not _has_btrfs_root():
            findings.append(ScanFinding(
                title="الجذر ليس BTRFS",
                detail="Snapshots متوفرة فقط على أنظمة الملفات BTRFS.",
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        snaps = _snapper_list()
        if snaps:
            findings.append(ScanFinding(
                title=f"{len(snaps)} snapshot عبر snapper",
                detail="\n".join(f"  #{n}: {d}" for n, d in snaps[-10:]),
                severity=Severity.INFO,
                actionable=False,
                raw_value=snaps,
            ))

        ts = _timeshift_list()
        if ts:
            findings.append(ScanFinding(
                title="Timeshift مثبت",
                detail=ts[:800] + "..." if len(ts) > 800 else ts,
                severity=Severity.INFO,
                actionable=False,
            ))

        if not snaps and not ts:
            findings.append(ScanFinding(
                title="لا أداة snapshots مثبتة",
                detail="ثبّت timeshift أو snapper لحماية نظامك.",
                severity=Severity.WARNING,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="وحدة إخبارية — راجع النتائج واستخدم timeshift/snapper يدوياً.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="لا إجراء تلقائي — استخدم timeshift/snapper يدوياً.")
