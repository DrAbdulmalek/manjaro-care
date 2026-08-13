#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/boot_sanity.py
======================
وحدة فحص سلامة الإقلاع — تكامل اختياري بين manjaro-care و manjaro-doctor.

آلية العمل:
  1) إن وُجد السكربت الخارجي boot-sanity-check.sh (من manjaro-doctor)،
     يستدعيه مع --json ويُحلّل الناتج — هذا يضمن عدم تكرار المنطق
     والمزامنة التلقائية مع أي تحديث للسكربت.
  2) إن لم يكن السكربت مُثبّتاً، يستخدم منطق Python أصلي كـ fallback —
     هذا يضمن أن manjaro-care يعمل مستقلاً بدون تبعية إجبارية.

المرجع التوثيقي: https://github.com/DrAbdulmalek/manjaro-doctor
ملف المشكلة:     issues/grub-btrfs-snapshot-boot.md

ترث من MaintenanceModule وتحترم نمط فحص → معاينة → تطبيق.
has_custom_ui = True لتوفير نافذة تشخيص تفصيلية.
"""

from __future__ import annotations
import json
import os
import re
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("boot_sanity")

# مسار السكربت الخارجي (من manjaro-doctor)
SCRIPT_PATH = "/usr/local/bin/boot-sanity-check.sh"

# رابط التوثيق الكامل على GitHub
DOC_URL = "https://github.com/DrAbdulmalek/manjaro-doctor/blob/main/issues/grub-btrfs-snapshot-boot.md"


# ---------------------------------------------------------------------------
# الطريقة 1: استدعاء السكربت الخارجي مع --json (الأفضل — لا تكرار منطق)
# ---------------------------------------------------------------------------

def _script_exists() -> bool:
    return shutil.which(SCRIPT_PATH) is not None


def _run_script_json(fix: bool = False) -> tuple[dict | None, str | None]:
    """يستدعي boot-sanity-check.sh --json وُيرجع البيانات المحلّلة."""
    args = [SCRIPT_PATH, "--json"]
    if fix:
        args.append("--fix")

    result = run_privileged(args, timeout=60)
    if not result.ok:
        return None, result.stderr.strip() or f"فشل السكربت (كود {result.returncode})"

    try:
        data = json.loads(result.stdout)
        return data, None
    except json.JSONDecodeError:
        return None, f"نتيجة غير متوقعة من السكربت:\n{result.stdout[:200]}"


# ---------------------------------------------------------------------------
# الطريقة 2: منطق Python أصلي (fallback — إن لم يكن السكربت مُثبّتاً)
# ---------------------------------------------------------------------------

def _get_root_source() -> str:
    result = run_unprivileged(["findmnt", "-no", "SOURCE", "/"])
    return result.stdout.strip() if result.ok else ""


def _is_btrfs_system() -> bool:
    result = run_unprivileged(["findmnt", "-no", "FSTYPE", "/"])
    return result.ok and result.stdout.strip() == "btrfs"


def _is_booted_from_snapshot(root_source: str) -> bool:
    return "timeshift-btrfs/snapshots" in root_source


def _is_rootflags_enabled() -> bool:
    try:
        with open("/etc/default/grub", "r") as f:
            return bool(re.search(r"GRUB_CMDLINE_LINUX_DEFAULT=.*rootflags=subvol=@", f.read()))
    except FileNotFoundError:
        return False


def _get_grub_linux_line() -> str:
    if not os.path.isfile("/boot/grub/grub.cfg"):
        return ""
    try:
        with open("/boot/grub/grub.cfg", "r") as f:
            content = f.read()
    except PermissionError:
        result = run_unprivileged(["cat", "/boot/grub/grub.cfg"])
        if not result.ok:
            return ""
        content = result.stdout

    in_main = False
    for line in content.splitlines():
        if line.startswith("menuentry") and "Manjaro Linux" in line and "submenu" not in line.lower():
            in_main = True
            continue
        if in_main and line.strip().startswith("linux"):
            return line.strip()
        if in_main and line.startswith("menuentry"):
            break
    return ""


def _grub_points_to_snapshot(line: str) -> bool:
    return "timeshift-btrfs/snapshots" in line


def _kernel_from_grub(line: str) -> str:
    parts = line.split()
    return os.path.basename(parts[1]) if len(parts) >= 2 else ""


def _kernel_exists(name: str) -> bool:
    return os.path.isfile(f"/boot/{name}") if name else True


def _scan_fallback() -> ScanResult:
    """فحص باستخدام المنطق Python الأصلي (إن لم يكن السكربت مُثبّتاً)."""
    findings: list[ScanFinding] = []

    if not _is_btrfs_system():
        findings.append(ScanFinding(
            title="نظام الملفات ليس btrfs — لا ينطبق هذا الفحص",
            detail="هذا الفحص مخصّص لأنظمة btrfs مع timeshift و grub-btrfs.",
            severity=Severity.OK, actionable=False,
        ))
        return ScanResult(module_name="فحص سلامة الإقلاع (btrfs + GRUB)", findings=findings)

    root_source = _get_root_source()
    booted_snapshot = _is_booted_from_snapshot(root_source)

    if booted_snapshot:
        findings.append(ScanFinding(
            title="النظام يعمل من لقطة timeshift وليس من @ الحقيقي!",
            detail=f"مصدر الجذر: {root_source}\nالتحديثات تُكتب داخل اللقطة وليس في @.",
            severity=Severity.CRITICAL, actionable=False,
        ))
    else:
        findings.append(ScanFinding(
            title="الجذر يعمل من subvolume حقيقي",
            detail=f"مصدر الجذر: {root_source}",
            severity=Severity.OK, actionable=False,
        ))

    linux_line = _get_grub_linux_line()
    if linux_line:
        if _grub_points_to_snapshot(linux_line):
            findings.append(ScanFinding(
                title="إدخال grub الرئيسي يشير إلى لقطة قديمة",
                detail=f"السطر: {linux_line[:120]}...",
                severity=Severity.CRITICAL, actionable=not booted_snapshot,
            ))
        else:
            findings.append(ScanFinding(
                title="إدخال grub الرئيسي يشير لمسار طبيعي",
                severity=Severity.OK, actionable=False,
            ))

        kernel = _kernel_from_grub(linux_line)
        if kernel and not _kernel_exists(kernel):
            findings.append(ScanFinding(
                title=f"ملف النواة {kernel} غير موجود في /boot!",
                severity=Severity.CRITICAL, actionable=False,
            ))

    if _is_rootflags_enabled():
        findings.append(ScanFinding(
            title="rootflags=subvol=@ مُفعّل (الحل الوقائي)",
            severity=Severity.OK, actionable=False,
        ))
    else:
        findings.append(ScanFinding(
            title="rootflags=subvol=@ غير مُفعّل بعد",
            detail="أضف rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT في /etc/default/grub",
            severity=Severity.WARNING, actionable=not booted_snapshot,
        ))

    return ScanResult(module_name="فحص سلامة الإقلاع (btrfs + GRUB)", findings=findings)


# ---------------------------------------------------------------------------
# وحدة فحص سلامة الإقلاع
# ---------------------------------------------------------------------------

class BootSanityModule(MaintenanceModule):
    name = "فحص سلامة الإقلاع (btrfs + GRUB)"
    slug = "boot_sanity"
    description = "يكتشف مشاكل الإقلاع بعد تحديث النواة على btrfs: انزلاق إلى لقطة timeshift، إعدادات grub خاطئة، ويتحقق من الحل الوقائي الدائم"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "drive-harddisk"
    has_custom_ui = True
    doc_url = DOC_URL  # يفتح صفحة التوثيق الكامل على GitHub

    def scan(self) -> ScanResult:
        # الطريقة 1: استدعاء السكربت الخارجي (الأفضل)
        if _script_exists():
            data, error = _run_script_json(fix=False)
            if error:
                # فشل السكربت — نستخدم fallback
                log.warning("فشل استدعاء السكربت الخارجي (%s)، نستخدم fallback", error)
                return _scan_fallback()

            findings: list[ScanFinding] = []
            for p in data.get("problems", []):
                sev = Severity.CRITICAL if p.get("severity") == "critical" else Severity.WARNING
                findings.append(ScanFinding(
                    title=p.get("message", ""),
                    detail=p.get("detail", p.get("message", "")),
                    severity=sev,
                    actionable=data.get("can_auto_fix", False),
                ))

            if not findings:
                findings.append(ScanFinding(
                    title="نظام الإقلاع سليم",
                    detail="لا توجد مشاكل في grub أو النواة أو لقطات timeshift.",
                    severity=Severity.OK, actionable=False,
                ))

            return ScanResult(module_name=self.name, findings=findings)

        # الطريقة 2: fallback Python أصلي
        log.info("السكربت الخارجي غير مُثبّت، نستخدم منطق Python أصلي")
        return _scan_fallback()

    def preview(self) -> list[PreviewStep]:
        # إن وُجد السكربت الخارجي، نستخدم fix_commands منه
        if _script_exists():
            data, _ = _run_script_json(fix=False)
            if data:
                steps: list[PreviewStep] = []
                for cmd in data.get("fix_commands", []):
                    steps.append(PreviewStep(description=f"تنفيذ: {cmd}", command=cmd))
                if not data.get("can_auto_fix"):
                    steps.append(PreviewStep(
                        description="⚠ الإصلاح التلقائي غير ممكن من هذه الجلسة. راجع التوثيق.",
                        command=None,
                    ))
                if not steps:
                    steps.append(PreviewStep(description="لا توجد إجراءات ضرورية."))
                return steps

        # Fallback: نعرض المعاينة يدوياً
        steps = []
        root_source = _get_root_source()
        if _is_booted_from_snapshot(root_source):
            steps.append(PreviewStep(
                description="لا يمكن الإصلاح تلقائياً من داخل لقطة — استخدم 'تشخيص تفصيلي' للخطوات اليدوية.",
            ))
            return steps

        if not _is_rootflags_enabled():
            steps.append(PreviewStep(
                description="إضافة rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT",
                command="sudo nano /etc/default/grub",
            ))

        linux_line = _get_grub_linux_line()
        if linux_line and _grub_points_to_snapshot(linux_line):
            steps.append(PreviewStep(
                description="إعادة توليد grub.cfg",
                command="sudo grub-mkconfig -o /boot/grub/grub.cfg",
            ))

        if not steps:
            steps.append(PreviewStep(description="لا توجد إجراءات ضرورية — النظام سليم."))

        return steps

    def apply(self) -> ApplyResult:
        # إن وُجد السكربت الخارجي مع --fix
        if _script_exists():
            data, error = _run_script_json(fix=True)
            if error:
                return ApplyResult(success=False, message=error)
            if not data.get("can_auto_fix"):
                return ApplyResult(
                    success=False,
                    message="لا يمكن الإصلاح تلقائياً. النظام يعمل من داخل لقطة timeshift.",
                    log_output=json.dumps(data, indent=2, ensure_ascii=False),
                )
            return ApplyResult(
                success=True,
                message="تم تنفيذ الإصلاحات. أعد التشغيل للتحقق بـ: findmnt /",
                log_output=json.dumps(data, indent=2, ensure_ascii=False),
            )

        # Fallback: إصلاح يدوي عبر Python
        root_source = _get_root_source()
        if _is_booted_from_snapshot(root_source):
            return ApplyResult(
                success=False,
                message="لا يمكن الإصلاح تلقائياً من داخل لقطة. استخدم 'تشخيص تفصيلي'.",
            )

        # 1) تفعيل rootflags إن لم يكن مُفعّلاً
        grub_default = "/etc/default/grub"
        if not _is_rootflags_enabled() and os.path.isfile(grub_default):
            with open(grub_default, "r") as f:
                content = f.read()
            modified = []
            for line in content.splitlines():
                if line.strip().startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    if "rootflags=subvol=@" not in line:
                        if line.rstrip().endswith("'"):
                            line = line.rstrip()[:-1] + " rootflags=subvol=@'"
                        elif line.rstrip().endswith('"'):
                            line = line.rstrip()[:-1] + ' rootflags=subvol=@"'
                modified.append(line)
            new_content = "\n".join(modified)
            tmp_path = "/tmp/grub_default_modified"
            with open(tmp_path, "w") as f:
                f.write(new_content)
            cp_result = run_privileged(["cp", tmp_path, grub_default])
            os.unlink(tmp_path)
            if not cp_result.ok:
                return ApplyResult(success=False, message=f"فشل تحديث /etc/default/grub: {cp_result.stderr}")

        # 2) إعادة توليد grub.cfg
        result = run_privileged(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
        if result.ok:
            return ApplyResult(
                success=True,
                message="تم إعادة توليد grub.cfg مع rootflags=subvol=@ — أعد التشغيل وتحقق بـ findmnt /",
                log_output=result.stdout + result.stderr,
            )
        return ApplyResult(
            success=False,
            message=f"فشل grub-mkconfig (كود {result.returncode}): {result.stderr}",
            log_output=result.stdout + result.stderr,
        )
