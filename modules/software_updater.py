#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/software_updater.py — التحقق من تحديثات النظام والـ AUR."""
from __future__ import annotations
import shutil
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("software_updater")


def _check_pacman_updates():
    r = run_unprivileged(["checkupdates"])
    if r.returncode == 0:
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    return []


def _check_aur_updates():
    for helper in ["yay", "paru", "trizen"]:
        if shutil.which(helper):
            if helper == "yay":
                r = run_unprivileged(["yay", "-Qua"])
            elif helper == "paru":
                r = run_unprivileged(["paru", "-Qua"])
            else:
                r = run_unprivileged([helper, "-Qua"])
            if r.ok:
                return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    return []


def _check_flatpak_updates():
    if not shutil.which("flatpak"):
        return []
    r = run_unprivileged(["flatpak", "remote-ls", "--updates"])
    if r.ok:
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    return []


class SoftwareUpdaterModule(MaintenanceModule):
    name = "مدير التحديثات 🔄"
    slug = "software_updater"
    description = "يفحص تحديثات pacman, AUR, و Flatpak في مكان واحد"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "system-software-update"

    def scan(self):
        findings = []
        pacman = _check_pacman_updates()
        aur = _check_aur_updates()
        flatpak = _check_flatpak_updates()

        total = len(pacman) + len(aur) + len(flatpak)

        if pacman:
            findings.append(ScanFinding(
                title=f"{len(pacman)} تحديث من المستودعات الرسمية",
                detail="\n".join(f"  • {p}" for p in pacman[:5]) + ("..." if len(pacman) > 5 else ""),
                severity=Severity.INFO,
                actionable=True,
                raw_value={"type": "pacman", "pkgs": pacman},
            ))
        if aur:
            findings.append(ScanFinding(
                title=f"{len(aur)} تحديث من AUR",
                detail="\n".join(f"  • {p}" for p in aur[:5]) + ("..." if len(aur) > 5 else ""),
                severity=Severity.INFO,
                actionable=True,
                raw_value={"type": "aur", "pkgs": aur},
            ))
        if flatpak:
            findings.append(ScanFinding(
                title=f"{len(flatpak)} تحديث Flatpak",
                detail="\n".join(f"  • {p}" for p in flatpak[:5]) + ("..." if len(flatpak) > 5 else ""),
                severity=Severity.INFO,
                actionable=True,
                raw_value={"type": "flatpak", "pkgs": flatpak},
            ))

        if not findings:
            findings.append(ScanFinding(
                title="النظام محدّث ✅",
                detail="لا توجد تحديثات متاحة.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.insert(0, ScanFinding(
                title=f"إجمالي التحديثات: {total}",
                detail="يمكن تحديث الكل دفعة واحدة.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        steps = []
        pacman = _check_pacman_updates()
        aur = _check_aur_updates()
        flatpak = _check_flatpak_updates()

        if pacman:
            steps.append(PreviewStep(
                description=f"تحديث {len(pacman)} حزمة من pacman",
                command="pacman -Syu --noconfirm",
            ))
        if aur:
            steps.append(PreviewStep(
                description=f"تحديث {len(aur)} حزمة من AUR",
                command="yay -Sua --noconfirm",
            ))
        if flatpak:
            steps.append(PreviewStep(
                description=f"تحديث {len(flatpak)} تطبيق Flatpak",
                command="flatpak update -y",
            ))
        return steps or [PreviewStep(description="لا تحديثات.")]

    def apply(self):
        logs = []
        success = True

        pacman = _check_pacman_updates()
        if pacman:
            r = run_privileged(["pacman", "-Syu", "--noconfirm"])
            logs.append(r.stdout + r.stderr)
            if not r.ok:
                success = False

        aur = _check_aur_updates()
        if aur:
            for helper in ["yay", "paru"]:
                if shutil.which(helper):
                    r = run_privileged([helper, "-Sua", "--noconfirm"])
                    logs.append(r.stdout + r.stderr)
                    if not r.ok:
                        success = False
                    break

        flatpak = _check_flatpak_updates()
        if flatpak:
            r = run_privileged(["flatpak", "update", "-y"])
            logs.append(r.stdout + r.stderr)
            if not r.ok:
                success = False

        return ApplyResult(
            success=success,
            message="تم التحديث" if success else "فشل جزئي",
            log_output="\n".join(logs),
        )
