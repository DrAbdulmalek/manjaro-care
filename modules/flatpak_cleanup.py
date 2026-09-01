#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/flatpak_cleanup.py
===========================
تنظيف إصدارات Flatpak القديمة غير المستخدمة.
مستوحى من Garuda Toolbox → System Maintenance.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("flatpak_cleanup")


def _flatpak_list_unused() -> list[str]:
    if not shutil.which("flatpak"):
        return []
    r = run_unprivileged(["flatpak", "list", "--app", "--columns=application"])
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def _flatpak_unused_refs() -> list[str]:
    if not shutil.which("flatpak"):
        return []
    r = run_unprivileged(["flatpak", "unused"])
    lines = []
    for line in r.stdout.splitlines():
        if line.strip() and not line.startswith("Ref") and not line.startswith("-"):
            lines.append(line.strip())
    return lines


class FlatpakCleanupModule(MaintenanceModule):
    name = "تنظيف Flatpak"
    slug = "flatpak_cleanup"
    description = "حذف إصدارات Flatpak القديمة غير المستخدمة (runtime بقايا)"
    needs_root = False
    risk_level = RiskLevel.MODERATE
    icon = "application-x-flatpak"

    def scan(self) -> ScanResult:
        if not shutil.which("flatpak"):
            return ScanResult(
                module_name=self.name,
                findings=[ScanFinding(
                    title="Flatpak غير مثبت",
                    detail="",
                    severity=Severity.INFO,
                    actionable=False,
                )],
            )

        unused = _flatpak_unused_refs()
        if unused:
            return ScanResult(
                module_name=self.name,
                findings=[ScanFinding(
                    title=f"{len(unused)} runtime غير مستخدم",
                    detail="\n".join(unused[:20]),
                    severity=Severity.WARNING,
                    actionable=True,
                    raw_value=unused,
                )],
            )
        return ScanResult(
            module_name=self.name,
            findings=[ScanFinding(
                title="لا بقايا Flatpak",
                detail="",
                severity=Severity.OK,
                actionable=False,
            )],
        )

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="حذف runtime غير المستخدم",
            command="flatpak uninstall --unused -y",
        )]

    def apply(self) -> ApplyResult:
        result = run_unprivileged(["flatpak", "uninstall", "--unused", "-y"])
        return ApplyResult(
            success=result.ok,
            message="تم تنظيف Flatpak" if result.ok else f"فشل (كود {result.returncode})",
            log_output=result.stdout + result.stderr,
        )
