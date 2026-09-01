#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/app_uninstaller.py — إدارة إلغاء التثبيت (IObit Uninstaller Style)."""
from __future__ import annotations
import shutil
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("app_uninstaller")


class AppUninstallerModule(MaintenanceModule):
    name = "إلغاء تثبيت البرامج 🗑️"
    slug = "app_uninstaller"
    description = "إلغاء تثبيت قوي مع إزالة البقايا والاعتماديات"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "application-x-executable"
    has_custom_ui = True

    def scan(self):
        findings = []
        # الحزم اليتيمة
        r = run_unprivileged(["pacman", "-Qdtq"])
        orphans = r.stdout.strip().splitlines() if r.ok else []
        if orphans:
            findings.append(ScanFinding(
                title=f"{len(orphans)} حزمة يتيمة",
                detail="حزم لا حاجة لها.\n" + "\n".join(f"  • {o}" for o in orphans[:10]),
                severity=Severity.WARNING,
                actionable=True,
                raw_value=orphans,
            ))
        else:
            findings.append(ScanFinding(
                title="لا حزم يتيمة",
                detail="كل الاعتماديات سليمة.",
                severity=Severity.OK,
                actionable=False,
            ))

        # عدد الحزم الإجمالي
        total_r = run_unprivileged(["pacman", "-Qq"])
        total = len(total_r.stdout.splitlines()) if total_r.ok else 0
        findings.insert(0, ScanFinding(
            title=f"{total} حزمة مثبتة",
            detail="استخدم النافذة المخصصة لإدارة الحزم.",
            severity=Severity.INFO,
            actionable=True,
        ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [PreviewStep(
            description="إدارة إلغاء التثبيت تتم عبر النافذة المخصصة.",
        )]

    def apply(self):
        return ApplyResult(
            success=True,
            message="استخدم زر «إدارة فردية» لإلغاء التثبيت الدفعاتي.",
        )
