#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/locale_manager.py
==========================
فحص إعدادات اللغة واللوكال (locale) — هل العربية مولدة؟ هل UTF-8 مفعّل؟
مستوحى من Garuda Assistant → Locale/Keyboard.
"""
from __future__ import annotations
import re

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("locale_manager")


def _current_locales() -> list[str]:
    result = run_unprivileged(["locale", "-a"])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _active_locale() -> str:
    result = run_unprivileged(["localectl", "status"])
    return result.stdout


class LocaleManagerModule(MaintenanceModule):
    name = "إعدادات اللغة واللوكال"
    slug = "locale_manager"
    description = "فحص اللغات المولدة واللوكال النشط — يقترح توليد ar_SA.UTF-8 إن لم يكن موجوداً"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "preferences-desktop-locale"

    def scan(self) -> ScanResult:
        locales = _current_locales()
        active = _active_locale()
        findings: list[ScanFinding] = []

        has_utf8 = any("utf8" in loc.lower() or "utf-8" in loc.lower() for loc in locales)
        has_ar = any("ar_" in loc for loc in locales)

        if not has_utf8:
            findings.append(ScanFinding(
                title="لا يوجد لوكال UTF-8 مولّد",
                detail="قد تواجه مشاكل مع البرامج الحديثة. يُنصح بتوليد en_US.UTF-8.",
                severity=Severity.WARNING,
                actionable=True,
            ))
        else:
            findings.append(ScanFinding(
                title="UTF-8 متوفر",
                detail="",
                severity=Severity.OK,
                actionable=False,
            ))

        if not has_ar:
            findings.append(ScanFinding(
                title="العربية غير مولّدة",
                detail="ar_SA.UTF-8 غير موجود — يمكن توليده لدعم التطبيقات العربية.",
                severity=Severity.INFO,
                actionable=True,
            ))
        else:
            findings.append(ScanFinding(
                title="العربية مولّدة",
                detail="",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        steps = []
        locales = _current_locales()
        if not any("ar_" in loc for loc in locales):
            steps.append(PreviewStep(
                description="توليد لوكال ar_SA.UTF-8",
                command="echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen && locale-gen",
            ))
        if not any("en_US" in loc for loc in locales):
            steps.append(PreviewStep(
                description="توليد لوكال en_US.UTF-8",
                command="echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen && locale-gen",
            ))
        return steps or [PreviewStep(description="كل اللغات المطلوبة موجودة.")]

    def apply(self) -> ApplyResult:
        locales = _current_locales()
        logs = []
        success = True

        if not any("ar_" in loc for loc in locales):
            r1 = run_privileged(["bash", "-c", "echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen && locale-gen"])
            logs.append(r1.stdout + r1.stderr)
            if not r1.ok:
                success = False

        if not any("en_US" in loc for loc in locales):
            r2 = run_privileged(["bash", "-c", "echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen && locale-gen"])
            logs.append(r2.stdout + r2.stderr)
            if not r2.ok:
                success = False

        return ApplyResult(
            success=success,
            message="تم توليد اللغات المطلوبة" if success else "فشل جزئي — راجع اللوغ",
            log_output="\n".join(logs),
        )
