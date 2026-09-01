#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/system_info.py
=======================
معلومات النظام — inxi / fastfetch / neofetch.
وحدة إخبارية بحتة (لا apply).
مستوحى من Garuda Assistant → System Information.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("system_info")


def _fetch_info() -> str:
    if shutil.which("fastfetch"):
        return run_unprivileged(["fastfetch", "--pipe", "false"]).stdout
    if shutil.which("inxi"):
        return run_unprivileged(["inxi", "-Fazy"]).stdout
    if shutil.which("neofetch"):
        return run_unprivileged(["neofetch", "--stdout"]).stdout
    # fallback
    uname = run_unprivileged(["uname", "-a"]).stdout.strip()
    return f"Kernel: {uname}\n(ثبّت fastfetch أو inxi لمعلومات أكثر)"


class SystemInfoModule(MaintenanceModule):
    name = "معلومات النظام"
    slug = "system_info"
    description = "عرض معلومات الجهاز والنواة والبيئة — إخباري فقط"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "computer"

    def scan(self) -> ScanResult:
        info = _fetch_info()
        return ScanResult(
            module_name=self.name,
            findings=[ScanFinding(
                title="معلومات النظام",
                detail=info or "لا يوجد معلومات.",
                severity=Severity.INFO,
                actionable=False,
            )],
        )

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="وحدة إخبارية — لا يوجد إجراء.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="لا إجراء لهذه الوحدة.")
