#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/repo_manager.py
========================
إدارة مستودعات pacman — تفعيل/تعطيل المستودعات الأساسية (core, extra, community, multilib)
وإضافة AUR helper (yay/paru) إن لم يكن مثبتاً.
مستوحى من Garuda Assistant → Repositories.
"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("repo_manager")

_PACMAN_CONF = Path("/etc/pacman.conf")


def _read_pacman_conf() -> str:
    try:
        return _PACMAN_CONF.read_text(encoding="utf-8")
    except Exception:
        return ""


def _repo_enabled(conf_text: str, repo_name: str) -> bool:
    """هل المستودع مفعل (غير معلّق بـ #)؟"""
    pattern = rf"^\s*#?\s*\[{re.escape(repo_name)}\]\s*$"
    for line in conf_text.splitlines():
        if re.match(pattern, line):
            return not line.strip().startswith("#")
    return False


def _has_aur_helper() -> str | None:
    for helper in ("yay", "paru", "trizen"):
        if shutil.which(helper):
            return helper
    return None


class RepoManagerModule(MaintenanceModule):
    name = "إدارة المستودعات"
    slug = "repo_manager"
    description = "فحص مستودعات pacman الأساسية وتوفر AUR helper"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "folder-download"
    has_custom_ui = True  # نافذة مخصصة لتفعيل/تعطيل المستودعات

    def scan(self) -> ScanResult:
        conf = _read_pacman_conf()
        findings: list[ScanFinding] = []

        repos = ["core", "extra", "community", "multilib"]
        disabled = [r for r in repos if not _repo_enabled(conf, r)]

        if disabled:
            findings.append(ScanFinding(
                title=f"{len(disabled)} مستودع/مستودعات معطّلة: {', '.join(disabled)}",
                detail="قد تفوتك حزم مهمة (خاصة multilib للبرامج 32-bit).",
                severity=Severity.WARNING,
                actionable=True,
                raw_value=disabled,
            ))
        else:
            findings.append(ScanFinding(
                title="كل المستودعات الأساسية مفعّلة",
                detail="core, extra, community, multilib جميعها نشطة.",
                severity=Severity.OK,
                actionable=False,
            ))

        aur = _has_aur_helper()
        if aur:
            findings.append(ScanFinding(
                title=f"AUR helper متوفر: {aur}",
                detail="يمكنك تثبيت حزم AUR بسهولة.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="لا يوجد AUR helper",
                detail="ثبّت yay أو paru لتثبيت حزم AUR.",
                severity=Severity.INFO,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="إدارة المستودعات تتم عبر نافذة مخصصة (زر «إدارة فردية»).",
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="استخدم زر «إدارة فردية» للتحكم بالمستودعات.",
        )
