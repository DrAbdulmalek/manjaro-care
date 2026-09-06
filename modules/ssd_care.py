#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/ssd_care.py — وحدة صيانة وتحسين أقراص SSD (المكافئ الوظيفي لـ SSD Fresh).
يعتمد على آليات لينكس الحقيقية (fstrim, sysctl, I/O scheduler, smartctl)
بدلاً من محاكاة واجهة برنامج ويندوز.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("ssd_care")


# ---------------------------------------------------------------------------
# Helper functions (adapted from the standalone ssd_care.py CLI)
# ---------------------------------------------------------------------------

def _list_block_devices() -> list[str]:
    """أسماء أجهزة الكتلة (sda, nvme0n1, ...)."""
    r = run_unprivileged(["lsblk", "-d", "-n", "-o", "NAME"])
    return [d for d in r.stdout.split() if d]


def _is_rotational(dev: str) -> bool | None:
    """True = HDD، False = SSD، None = غير معروف."""
    path = f"/sys/block/{dev}/queue/rotational"
    try:
        with open(path) as f:
            return f.read().strip() == "1"
    except (FileNotFoundError, PermissionError):
        return None


def _get_scheduler(dev: str) -> str | None:
    """الجدولة الحالية للجهاز (mq-deadline, none, bfq, ...)."""
    path = f"/sys/block/{dev}/queue/scheduler"
    try:
        with open(path) as f:
            content = f.read()
        for token in content.split():
            if token.startswith("[") and token.endswith("]"):
                return token.strip("[]")
    except (FileNotFoundError, PermissionError):
        pass
    return None


def _get_swappiness() -> int:
    r = run_unprivileged(["sysctl", "-n", "vm.swappiness"])
    try:
        return int(r.stdout.strip())
    except ValueError:
        return -1


def _get_trim_enabled() -> bool:
    r = run_unprivileged(["systemctl", "is-enabled", "fstrim.timer"])
    return r.ok and "enabled" in r.stdout


def _get_trim_last_run() -> str | None:
    r = run_unprivileged(["systemctl", "status", "fstrim.timer"])
    for line in r.stdout.splitlines():
        if "Trigger:" in line:
            return line.split("Trigger:")[-1].strip()
    return None


def _check_fstab_atime() -> dict:
    """يفحص /etc/fstab ويعرض خيارات atime لكل نقطة تحميل."""
    findings = {}
    try:
        with open("/etc/fstab") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                mountpoint, options = parts[1], parts[3]
                findings[mountpoint] = {
                    "options": options,
                    "has_noatime": "noatime" in options,
                    "has_relatime": "relatime" in options,
                }
    except (FileNotFoundError, PermissionError):
        pass
    return findings


def _get_journald_storage() -> str:
    try:
        with open("/etc/systemd/journald.conf") as f:
            for line in f:
                if line.strip().startswith("Storage="):
                    return line.split("=")[-1].strip()
    except (FileNotFoundError, PermissionError):
        pass
    return "auto (افتراضي)"


def _get_smart_health(dev: str) -> dict:
    """قراءة S.M.A.R.T والحرارة — يتطلب smartmontools + root."""
    if not shutil.which("smartctl"):
        return {"error": "smartmontools غير مثبّت"}
    r_health = run_privileged(["smartctl", "-H", f"/dev/{dev}"])
    r_attrs = run_privileged(["smartctl", "-A", f"/dev/{dev}"])
    if not r_health.ok and not r_attrs.ok:
        return {"error": "تعذّر قراءة S.M.A.R.T"}
    passed = "PASSED" in r_health.stdout or "OK" in r_health.stdout
    temp = None
    wear = None
    for line in r_attrs.stdout.splitlines():
        low = line.lower()
        if "temperature" in low:
            digits = [t for t in line.split() if t.isdigit()]
            if digits:
                temp = int(digits[0])
        if "wear_leveling" in low or "media_wearout" in low or "percent_lifetime" in low:
            digits = [t for t in line.split() if t.isdigit()]
            if digits:
                wear = digits[-1]
    return {
        "health_passed": passed,
        "temperature_c": temp,
        "wear_indicator": wear,
    }


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class SSDCareModule(MaintenanceModule):
    name = "صحة SSD ⚡"
    slug = "ssd_care"
    description = "صيانة وتحسين أقراص SSD: TRIM، جدولة I/O، S.M.A.R.T، swappiness"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "drive-harddisk-solidstate"
    has_custom_ui = True
    doc_url = None

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        # ── TRIM ──────────────────────────────────────────────────────
        trim_enabled = _get_trim_enabled()
        trim_last = _get_trim_last_run()
        if trim_enabled:
            findings.append(ScanFinding(
                title="TRIM الدوري مفعّل ✅",
                detail=f"fstrim.timer نشط. آخر/قادم تشغيل: {trim_last or 'غير محدد'}",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="TRIM الدوري معطّل ❌",
                detail="الـ SSD يحتاج TRIM دوري لإطالة العمر وتحسين الأداء. "
                       "يفضّل تفعيل fstrim.timer (أسبوعي) بدل التشغيل المستمر (discard).",
                severity=Severity.WARNING,
                actionable=True,
            ))

        # ── Swappiness ────────────────────────────────────────────────
        sw = _get_swappiness()
        if 0 <= sw <= 30:
            findings.append(ScanFinding(
                title=f"vm.swappiness = {sw} ✅",
                detail="قيمة مثالية لأقراص SSD — تقلّل الكتابة على القرص.",
                severity=Severity.OK,
                actionable=False,
                raw_value=sw,
            ))
        else:
            findings.append(ScanFinding(
                title=f"vm.swappiness = {sw} ⚠️",
                detail=f"القيمة الافتراضية ({sw}) مرتفعة لأقراص SSD. "
                       f"يُنصح بخفضها إلى 10-20 لتقليل الكتابة على القرص.",
                severity=Severity.WARNING,
                actionable=True,
                raw_value=sw,
            ))

        # ── I/O Scheduler ────────────────────────────────────────────
        for dev in _list_block_devices():
            rotational = _is_rotational(dev)
            if rotational is True:
                continue  # skip HDDs
            if rotational is None:
                continue  # skip unknowns (loop, ram, etc.)
            sched = _get_scheduler(dev)
            if sched is None:
                continue
            good_schedulers = {"none", "mq-deadline"}
            if sched in good_schedulers:
                findings.append(ScanFinding(
                    title=f"{dev}: جدولة I/O = {sched} ✅",
                    detail=f"الجدولة '{sched}' مناسبة لأقراص SSD.",
                    severity=Severity.OK,
                    actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title=f"{dev}: جدولة I/O = {sched} ⚠️",
                    detail=f"الجدولة '{sched}' ليست المثلى للـ SSD. "
                           f"يُنصح بـ 'none' أو 'mq-deadline'.",
                    severity=Severity.INFO,
                    actionable=True,
                ))

        # ── fstab atime ──────────────────────────────────────────────
        fstab = _check_fstab_atime()
        for mp, info in fstab.items():
            if info["has_noatime"]:
                findings.append(ScanFinding(
                    title=f"{mp}: noatime ✅",
                    detail="خيار noatime يقلّل الكتابة غير الضرورية على الـ SSD.",
                    severity=Severity.OK,
                    actionable=False,
                ))
            elif info["has_relatime"]:
                findings.append(ScanFinding(
                    title=f"{mp}: relatime (مقبول)",
                    detail="relatime مقبول لكن noatime أفضل للـ SSD.",
                    severity=Severity.INFO,
                    actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title=f"{mp}: بدون تحسين atime ⚠️",
                    detail="إضافة noatime إلى fstab تقلّل الكتابة. "
                           "(يُفضّل التعديل اليدوي لتجنّب أخطاء الإقلاع)",
                    severity=Severity.INFO,
                    actionable=False,
                ))

        # ── Journald ─────────────────────────────────────────────────
        js = _get_journald_storage()
        findings.append(ScanFinding(
            title=f"Journald storage: {js}",
            detail="تحديد حجم أقصى للسجلات (مثلاً 200M) يقلّل الكتابة على الـ SSD.",
            severity=Severity.INFO,
            actionable=True,
        ))

        # ── S.M.A.R.T ────────────────────────────────────────────────
        if not shutil.which("smartctl"):
            findings.append(ScanFinding(
                title="S.M.A.R.T غير متاح",
                detail="smartmontools غير مثبّت. ثبّته بـ: sudo pacman -S smartmontools",
                severity=Severity.INFO,
                actionable=False,
            ))
        else:
            for dev in _list_block_devices():
                if _is_rotational(dev) is False:
                    smart = _get_smart_health(dev)
                    if "error" in smart:
                        findings.append(ScanFinding(
                            title=f"{dev}: تعذّر قراءة S.M.A.R.T",
                            detail=smart["error"],
                            severity=Severity.INFO,
                            actionable=False,
                        ))
                    else:
                        health = "سليم ✅" if smart["health_passed"] else "تحذير ❌"
                        temp = f"{smart['temperature_c']}°C" if smart["temperature_c"] else "غير متاح"
                        wear = smart["wear_indicator"] or "غير متاح"
                        sev = Severity.OK if smart["health_passed"] else Severity.WARNING
                        findings.append(ScanFinding(
                            title=f"{dev}: S.M.A.R.T {health}",
                            detail=f"الحرارة: {temp} | مؤشر التآكل: {wear}",
                            severity=sev,
                            actionable=False,
                        ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        steps = []
        if not _get_trim_enabled():
            steps.append(PreviewStep(
                description="تفعيل TRIM الدوري (fstrim.timer)",
                command="systemctl enable --now fstrim.timer",
            ))
        steps.append(PreviewStep(
            description="تشغيل TRIM فوري على كل أقسام SSD",
            command="fstrim -av",
        ))
        sw = _get_swappiness()
        if sw > 30:
            steps.append(PreviewStep(
                description=f"خفض vm.swappiness من {sw} إلى 15",
                command="sysctl vm.swappiness=15 && "
                       "echo 'vm.swappiness=15' > /etc/sysctl.d/99-ssd-care.conf",
            ))
        steps.append(PreviewStep(
            description="تحديد حجم سجلات journald إلى 200M",
            command="mkdir -p /etc/systemd/journald.conf.d && "
                    "echo '[Journal]\\nSystemMaxUse=200M' > "
                    "/etc/systemd/journald.conf.d/99-ssd-care.conf && "
                    "systemctl restart systemd-journald",
        ))
        return steps

    def apply(self) -> ApplyResult:
        logs: list[str] = []

        # TRIM timer
        if not _get_trim_enabled():
            r = run_privileged(["systemctl", "enable", "--now", "fstrim.timer"])
            logs.append(f"fstrim.timer: {'OK' if r.ok else 'FAIL'}")
            logs.append(r.stdout + r.stderr)

        # TRIM now
        r = run_privileged(["fstrim", "-av"])
        logs.append(f"fstrim -av: {'OK' if r.ok else 'FAIL'}")
        logs.append(r.stdout + r.stderr)

        # Swappiness
        sw = _get_swappiness()
        if sw > 30:
            r = run_privileged(["sysctl", "vm.swappiness=15"])
            logs.append(f"sysctl swappiness: {'OK' if r.ok else 'FAIL'}")
            # Persist
            r2 = run_privileged(["bash", "-c",
                "echo 'vm.swappiness=15' > /etc/sysctl.d/99-ssd-care.conf"])
            logs.append(f"persist swappiness: {'OK' if r2.ok else 'FAIL'}")

        # Journald
        r = run_privileged(["bash", "-c",
            "mkdir -p /etc/systemd/journald.conf.d && "
            "printf '[Journal]\\nSystemMaxUse=200M\\n' > "
            "/etc/systemd/journald.conf.d/99-ssd-care.conf"])
        logs.append(f"journald limit: {'OK' if r.ok else 'FAIL'}")
        r2 = run_privileged(["systemctl", "restart", "systemd-journald"])
        logs.append(f"journald restart: {'OK' if r2.ok else 'FAIL'}")

        all_ok = all("OK" in l for l in logs if ":" in l)
        return ApplyResult(
            success=all_ok,
            message="تم تطبيق تحسينات SSD" if all_ok else "بعض العمليات فشلت — راجع السجل",
            log_output="\n".join(logs),
        )
