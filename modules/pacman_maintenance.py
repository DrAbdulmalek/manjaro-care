#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/pacman_maintenance.py — قفل pacman، إصلاح repo غير الصالح، والمرايا والتحديث."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged

PACMAN_CONF = Path("/etc/pacman.conf")
MIRRORLIST = Path("/etc/pacman.d/mirrorlist")
LOCK = Path("/var/lib/pacman/db.lck")


def _empty_community_section() -> bool:
    if not PACMAN_CONF.exists():
        return False
    section = None
    has_server_or_include = False
    for raw in PACMAN_CONF.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\[([^]]+)\]\s*$", raw)
        if m:
            if section == "community" and not has_server_or_include:
                return True
            section = m.group(1)
            has_server_or_include = False
            continue
        if section == "community" and re.match(r"^\s*(Server|Include)\s*=", raw):
            has_server_or_include = True
    return section == "community" and not has_server_or_include


def _pacman_running() -> bool:
    r = run_unprivileged(["pgrep", "-x", "pacman"])
    return r.returncode == 0


class PacmanMaintenanceModule(MaintenanceModule):
    name = "إصلاح وصيانة Pacman 🛠️"
    slug = "pacman_maintenance"
    description = "يفحص قفل pacman، يعالج [community] الفارغ، يجدّد المرايا ثم يحدّث النظام"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "system-software-update"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        if not shutil.which("pacman"):
            findings.append(ScanFinding(
                title="pacman غير موجود",
                detail="تعذر العثور على pacman.",
                severity=Severity.CRITICAL,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        if not shutil.which("fuser"):
            findings.append(ScanFinding(
                title="fuser غير موجود",
                detail="لا يمكن التحقق بأمان من استخدام db.lck؛ ثبّت حزمة psmisc قبل التطبيق.",
                severity=Severity.CRITICAL,
                actionable=False,
            ))

        if not shutil.which("pacman-mirrors"):
            findings.append(ScanFinding(
                title="pacman-mirrors غير موجود",
                detail="لن يمكن تحديث قائمة المرايا؛ ثبّت pacman-mirrors قبل التطبيق.",
                severity=Severity.CRITICAL,
                actionable=False,
            ))

        if _pacman_running():
            findings.append(ScanFinding(
                title="pacman يعمل حالياً",
                detail="لن يُحذف db.lck ولن يبدأ تحديث متوازٍ.",
                severity=Severity.WARNING,
                actionable=False,
            ))

        if LOCK.exists():
            findings.append(ScanFinding(
                title="يوجد db.lck",
                detail="سيُزال فقط إذا لم يكن هناك pacman أو عملية تستخدم القفل.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        if _empty_community_section():
            findings.append(ScanFinding(
                title="قسم [community] فارغ",
                detail="قسم مستودع بلا Server/Include يمكن أن يسبب: no servers configured for repository.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        if not MIRRORLIST.exists() or not any(
            line.lstrip().startswith("Server =") for line in MIRRORLIST.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        ):
            findings.append(ScanFinding(
                title="قائمة المرايا غير صالحة أو فارغة",
                detail="سيتم توليد mirrorlist جديدة عبر pacman-mirrors.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        if not findings:
            findings.append(ScanFinding(
                title="Pacman جاهز للصيانة",
                detail="لا يوجد قفل أو قسم [community] فارغ ظاهر في الفحص.",
                severity=Severity.OK,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(
                description="فحص pacman/db.lck وعدم حذف أي قفل نشط",
                command="pgrep -x pacman + fuser /var/lib/pacman/db.lck",
            ),
            PreviewStep(
                description="تعطيل [community] فقط إذا كان قسماً فارغاً، مع نسخة احتياطية",
                command="cp /etc/pacman.conf /etc/pacman.conf.bak.manjaro-care.* && comment empty [community]",
            ),
            PreviewStep(
                description="إعادة توليد قائمة المرايا واختيار 5 مرايا سريعة",
                command="pacman-mirrors --fasttrack 5",
            ),
            PreviewStep(
                description="مزامنة قواعد البيانات وترقية النظام",
                command="pacman -Syu",
            ),
        ]

    def apply(self) -> ApplyResult:
        if _pacman_running():
            return ApplyResult(False, "pacman يعمل حالياً؛ لم يتم تعديل القفل أو تشغيل التحديث.", "STOP: active pacman")

        logs: list[str] = []

        if LOCK.exists():
            check = run_privileged(["fuser", "-s", str(LOCK)])
            if check.returncode == 0 or _pacman_running():
                return ApplyResult(False, "قفل pacman مستخدم فعلياً؛ لن يتم حذفه.", "STOP: active lock user")
            rm = run_privileged(["rm", "-f", str(LOCK)])
            if not rm.ok:
                return ApplyResult(False, "فشل إزالة القفل العالق.", rm.stdout + rm.stderr)
            logs.append("تمت إزالة db.lck العالق بعد التحقق.")

        if _empty_community_section():
            backup = run_privileged([
                "bash", "-lc",
                'cp -a /etc/pacman.conf "/etc/pacman.conf.bak.manjaro-care.$(date +%Y%m%d-%H%M%S)"',
            ])
            if not backup.ok:
                return ApplyResult(False, "تعذر إنشاء نسخة احتياطية من pacman.conf.", backup.stdout + backup.stderr)

            fix = run_privileged([
                "sed", "-i",
                '/^\[community\][[:space:]]*$/s/^/# Manjaro Care disabled empty repository section: /',
                str(PACMAN_CONF),
            ])
            if not fix.ok:
                return ApplyResult(False, "تعذر تعطيل [community] الفارغ.", fix.stdout + fix.stderr)
            logs.append("تم تعطيل [community] الفارغ مع نسخة احتياطية.")

        if not shutil.which("pacman-mirrors"):
            return ApplyResult(False, "pacman-mirrors غير مثبت؛ أوقف التنفيذ قبل التحديث.", "\n".join(logs))

        mirrors = run_privileged(["pacman-mirrors", "--fasttrack", "5"], timeout=600)
        logs.append(mirrors.stdout + mirrors.stderr)
        if not mirrors.ok:
            return ApplyResult(False, "فشل تحديث قائمة المرايا؛ لم يُشغّل pacman -Syu.", "\n".join(logs))

        update = run_privileged(["pacman", "-Syu"], timeout=3600)
        logs.append(update.stdout + update.stderr)
        return ApplyResult(
            success=update.ok,
            message="تمت صيانة Pacman والمرايا والتحديث بنجاح." if update.ok else "فشل تحديث النظام؛ راجع السجل.",
            log_output="\n".join(logs),
        )
