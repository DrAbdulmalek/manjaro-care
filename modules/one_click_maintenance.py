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
from modules.pacman_maintenance import PacmanMaintenanceModule

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
        # اجعل الفحص الشامل يعكس بوابة Pacman نفسها، حتى لا يظهر
        # "النظام سليم" بينما سيؤدي apply() إلى التوقف بسبب مشكلة Pacman.
        pacman_scan = PacmanMaintenanceModule().scan()
        findings.extend(pacman_scan.findings)

        # نقوم بفحص سريع لبقية الوحدات الفرعية
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

        if not findings:
            findings.append(ScanFinding(
                title="النظام في حالة ممتازة ✅",
                detail="لا توجد مهام صيانة مطلوبة.",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [
            PreviewStep(description="1. فحص/إصلاح قفل pacman وإعداد المستودعات عند الحاجة", command="pacman-guard: no active pacman; remove stale db.lck only after fuser check"),
            PreviewStep(description="2. تحديث المرايا", command="pacman-mirrors --fasttrack 5"),
            PreviewStep(description="3. مزامنة قواعد البيانات وترقية النظام", command="pacman -Syu"),
            PreviewStep(description="4. تنظيف الحزم اليتيمة", command="pacman -Rns $(pacman -Qdtq) --noconfirm"),
            PreviewStep(description="5. تقليص سجلات journal", command="journalctl --vacuum-time=7d"),
            PreviewStep(description="6. تنظيف cache pacman", command="paccache -rk2"),
            PreviewStep(description="7. تنظيف Flatpak unused", command="flatpak uninstall --unused -y"),
            PreviewStep(description="8. fstrim", command="fstrim -v /"),
        ]

    def apply(self):
        logs = []
        success = True

        # Pacman guard + mirror refresh + full system update first.
        pm = PacmanMaintenanceModule().apply()
        logs.append("🛠️ Pacman: " + pm.message + "\n" + pm.log_output)
        if not pm.success:
            return ApplyResult(False, "توقفت الصيانة قبل التنظيف لأن صيانة Pacman لم تنجح.", "\n".join(logs))

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
        r = run_privileged(["fstrim", "-v", "/"])
        logs.append(r.stdout[:200] if r.stdout else "💿 fstrim: تم")

        # 6. sync
        run_privileged(["sync"])

        return ApplyResult(
            success=success,
            message="✅ تمت صيانة النظام بنقرة واحدة!",
            log_output="\n".join(logs),
        )
