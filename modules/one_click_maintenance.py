#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/one_click_maintenance.py — صيانة بنقرة واحدة تجمع كل شيء."""
from __future__ import annotations
import shutil
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("one_click_maintenance")


class OneClickMaintenanceModule(MaintenanceModule):
    name = "صيانة بنقرة واحدة ⚡"
    slug = "one_click_maintenance"
    description = "تشغيل كل عمليات التنظيف والتحسين دفعة واحدة"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "dialog-ok-apply"

    def scan(self):
        findings = []
        # نقوم بفحص سريع لكل الوحدات الفرعية
        checks = []

        # 1. حزم يتيمة
        r = run_unprivileged(["pacman", "-Qdtq"])
        if r.ok and r.stdout.strip():
            checks.append("حزم يتيمة")

        # 2. journal كبير
        jr = run_unprivileged(["journalctl", "--disk-usage"])
        if jr.ok:
            checks.append("سجلات systemd")

        # 3. cache
        if shutil.which("paccache"):
            checks.append("ذاكرة pacman")

        # 4. flatpak unused
        if shutil.which("flatpak"):
            checks.append("Flatpak unused")

        if checks:
            findings.append(ScanFinding(
                title=f"{len(checks)} مهام صيانة مطلوبة",
                detail="، ".join(checks),
                severity=Severity.WARNING,
                actionable=True,
            ))
        else:
            findings.append(ScanFinding(
                title="النظام في حالة ممتازة ✅",
                detail="لا توجد مهام صيانة مطلوبة.",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [
            PreviewStep(description="1. تنظيف الحزم اليتيمة", command="pacman -Rns $(pacman -Qdtq) --noconfirm"),
            PreviewStep(description="2. تقليص سجلات journal", command="journalctl --vacuum-time=7d"),
            PreviewStep(description="3. تنظيف cache pacman", command="paccache -rk2"),
            PreviewStep(description="4. تنظيف Flatpak unused", command="flatpak uninstall --unused -y"),
            PreviewStep(description="5. fstrim", command="fstrim -av /"),
            PreviewStep(description="6. تحديث قاعدة البيانات", command="pacman -Sy"),
        ]

    def apply(self):
        logs = []
        success = True

        # 1. حزم يتيمة
        r = run_privileged(["bash", "-c", "pacman -Rns $(pacman -Qdtq) --noconfirm 2>/dev/null || true"])
        logs.append("🗑️ الحزم اليتيمة: " + (r.stdout[:200] if r.stdout else "تم"))

        # 2. journal
        r = run_privileged(["journalctl", "--vacuum-time=7d"])
        logs.append(r.stdout[:200] if r.stdout else "📋 Journal: تم")

        # 3. paccache
        if shutil.which("paccache"):
            r = run_privileged(["paccache", "-rk2"])
            logs.append(r.stdout[:200] if r.stdout else "📦 Cache: تم")

        # 4. flatpak
        if shutil.which("flatpak"):
            r = run_privileged(["flatpak", "uninstall", "--unused", "-y"])
            logs.append(r.stdout[:200] if r.stdout else "📦 Flatpak: تم")

        # 5. fstrim
        r = run_privileged(["fstrim", "-av", "/"])
        logs.append(r.stdout[:200] if r.stdout else "💿 fstrim: تم")

        # 6. sync
        run_privileged(["sync"])

        return ApplyResult(
            success=success,
            message="✅ تمت صيانة النظام بنقرة واحدة!",
            log_output="\n".join(logs),
        )
