#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/boot_sanity.py
======================
وحدة فحص سلامة الإقلاع — تدمج منطق manjaro-doctor داخل واجهة manjaro-care.

تكشف ثلاث حالات تسبب فشل الإقلاع بعد تحديث Manjaro على btrfs:
  1) النظام يعمل فعلياً من داخل لقطة timeshift بدل subvolume @ الحقيقي.
  2) الإدخال الرئيسي في grub.cfg يشير لمسار لقطة قديمة.
  3) الحل الوقائي الدائم (rootflags=subvol=@) غير مُفعّل بعد.

المرجع التوثيقي الكامل: https://github.com/DrAbdulmalek/manjaro-doctor

ترث من MaintenanceModule وتحترم نمط فحص → معاينة → تطبيق:
  - scan(): يقرأ حالة النظام فقط (findmnt, grub.cfg, /etc/default/grub)
  - preview(): يعرض ماذا سيحدث إن نُفّذ الإصلاح
  - apply(): يُنفّذ grub-mkconfig فقط (الإصلاح الآمن من داخل @ الحقيقي)

للتشخيص التفصيلي الكامل (خارج نطاق scan/preview/apply)، توفر
has_custom_ui = True نافذة مخصصة (BootSanityDialog) تعرض التشخيص
الكامل خطوة بخطوة مع الاقتراحات — كما هو موثّق في manjaro-doctor.
"""

from __future__ import annotations
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


# ---------------------------------------------------------------------------
# دوال مساعدة للفحص
# ---------------------------------------------------------------------------

def _get_root_source() -> str:
    """يُرجع مصدر الجذر المُركَّب فعلياً (مثل /dev/sda6[/@] أو مسار لقطة)."""
    result = run_unprivileged(["findmnt", "-no", "SOURCE", "/"])
    return result.stdout.strip() if result.ok else ""


def _is_booted_from_snapshot(root_source: str) -> bool:
    """هل الجذر الحالي مركّب من داخل لقطة timeshift؟"""
    return "timeshift-btrfs/snapshots" in root_source


def _is_rootflags_protection_enabled() -> bool:
    """هل rootflags=subvol=@ موجود في GRUB_CMDLINE_LINUX_DEFAULT؟"""
    try:
        with open("/etc/default/grub", "r") as f:
            content = f.read()
        return bool(re.search(r"GRUB_CMDLINE_LINUX_DEFAULT=.*rootflags=subvol=@", content))
    except FileNotFoundError:
        return False


def _get_main_grub_entry_linux_line() -> str:
    """يستخرج سطر linux من الإدخال الرئيسي في grub.cfg (وليس submenu اللقطات)."""
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

    # ابحث عن الإدخال الرئيسي (Manjaro Linux) واستخرج سطر linux
    in_main_entry = False
    for line in content.splitlines():
        if line.startswith("menuentry") and "Manjaro Linux" in line and "submenu" not in line.lower():
            in_main_entry = True
            continue
        if in_main_entry and line.strip().startswith("linux"):
            return line.strip()
        if in_main_entry and line.startswith("menuentry"):
            break  # دخلنا إدخالاً آخر
    return ""


def _grub_entry_points_to_snapshot(linux_line: str) -> bool:
    """هل سطر linux يشير إلى لقطة timeshift؟"""
    return "timeshift-btrfs/snapshots" in linux_line


def _is_btrfs_system() -> bool:
    """هل نظام الملفات الجذر btrfs؟"""
    result = run_unprivileged(["findmnt", "-no", "FSTYPE", "/"])
    return result.ok and result.stdout.strip() == "btrfs"


def _get_kernel_from_grub_entry(linux_line: str) -> str:
    """يستخرج اسم ملف النواة من سطر linux في grub.cfg."""
    parts = linux_line.split()
    if len(parts) >= 2:
        return os.path.basename(parts[1])
    return ""


def _kernel_file_exists(kernel_name: str) -> bool:
    """هل ملف النواة موجود فعلياً في /boot؟"""
    return os.path.isfile(f"/boot/{kernel_name}") if kernel_name else True


# ---------------------------------------------------------------------------
# وحدة فحص سلامة الإقلاع
# ---------------------------------------------------------------------------

class BootSanityModule(MaintenanceModule):
    name = "فحص سلامة الإقلاع (btrfs + GRUB)"
    slug = "boot_sanity"
    description = "يكشف مشاكل الإقلاع بعد تحديث النواة على btrfs: انزلاق إلى لقطة timeshift، إعدادات grub خاطئة، ويتحقق من الحل الوقائي الدائم"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "system-software-install"
    has_custom_ui = True  # نافذة تشخيص تفصيلية مخصصة

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        # هل النظام btrfs أصلاً؟ إن لم يكن، لا داعي للفحص
        if not _is_btrfs_system():
            findings.append(ScanFinding(
                title="نظام الملفات ليس btrfs — لا ينطبق هذا الفحص",
                detail="هذا الفحص مخصّص لأنظمة btrfs مع timeshift و grub-btrfs فقط.",
                severity=Severity.OK,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        # 1) فحص الجذر: هل نعمل من لقطة؟
        root_source = _get_root_source()
        booted_from_snapshot = _is_booted_from_snapshot(root_source)

        if booted_from_snapshot:
            findings.append(ScanFinding(
                title="النظام يعمل من لقطة timeshift وليس من subvolume @ الحقيقي!",
                detail=(
                    f"مصدر الجذر: {root_source}\n"
                    "هذا يعني أن التحديثات (بما فيها النواة) تُكتب داخل اللقطة وليس في @.\n"
                    "يجب الإصلاح عبر chroot إلى @ الحقيقي."
                ),
                severity=Severity.CRITICAL,
                actionable=False,  # لا يمكن إصلاح هذا من داخل اللقطة نفسها
                raw_value="booted_from_snapshot",
            ))
        else:
            findings.append(ScanFinding(
                title="الجذر يعمل من subvolume حقيقي (ليس لقطة)",
                detail=f"مصدر الجذر: {root_source}",
                severity=Severity.OK,
                actionable=False,
            ))

        # 2) فحص إدخال grub الرئيسي
        linux_line = _get_main_grub_entry_linux_line()
        if linux_line:
            if _grub_entry_points_to_snapshot(linux_line):
                findings.append(ScanFinding(
                    title="الإدخال الرئيسي في grub.cfg يشير إلى لقطة قديمة",
                    detail=f"السطر: {linux_line[:120]}...",
                    severity=Severity.CRITICAL,
                    actionable=not booted_from_snapshot,  # يمكن إصلاح فقط إن كنا على @ حقيقي
                    raw_value="grub_points_to_snapshot",
                ))
            else:
                findings.append(ScanFinding(
                    title="إدخال grub الرئيسي يشير لمسار طبيعي",
                    detail="لا إشارة للقطات timeshift في الإدخال الرئيسي.",
                    severity=Severity.OK,
                    actionable=False,
                ))

            # 2b) هل ملف النواة موجود فعلياً؟
            kernel_name = _get_kernel_from_grub_entry(linux_line)
            if kernel_name and not _kernel_file_exists(kernel_name):
                findings.append(ScanFinding(
                    title=f"ملف النواة {kernel_name} غير موجود في /boot!",
                    detail="النواة المُشار إليها في grub.cfg غير موجودة فعلياً — سيفشل الإقلاع.",
                    severity=Severity.CRITICAL,
                    actionable=False,
                    raw_value="kernel_missing",
                ))
        else:
            findings.append(ScanFinding(
                title="تعذر قراءة إدخال grub الرئيسي",
                detail="قد يكون النظام لا يستخدم GRUB أو الملف غير قابل للقراءة.",
                severity=Severity.INFO,
                actionable=False,
            ))

        # 3) فحص الحل الوقائي الدائم
        if _is_rootflags_protection_enabled():
            findings.append(ScanFinding(
                title="الحل الوقائي الدائم (rootflags=subvol=@) مُفعّل",
                detail="GRUB_CMDLINE_LINUX_DEFAULT يحتوي rootflags=subvol=@ — هذا يمنع تكرار المشكلة.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="الحل الوقائي الدائم غير مُفعّل بعد",
                detail=(
                    "أضف rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT في /etc/default/grub\n"
                    "ثم شغّل grub-mkconfig. هذا يمنع تكرار مشكلة 'kernel not found' حتى لو\n"
                    "انزلق اكتشاف subvolume الحي في grub-mkconfig مستقبلاً."
                ),
                severity=Severity.WARNING,
                actionable=not booted_from_snapshot,
                raw_value="rootflags_not_set",
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        root_source = _get_root_source()
        booted_from_snapshot = _is_booted_from_snapshot(root_source)
        steps: list[PreviewStep] = []

        if booted_from_snapshot:
            steps.append(PreviewStep(
                description="لا يمكن الإصلاح تلقائياً من داخل لقطة — يجب إصلاح عبر chroot إلى @ الحقيقي.",
                command=None,
            ))
            steps.append(PreviewStep(
                description="الخطوات اليدوية:",
                command="sudo mount -o subvol=@ /dev/sdXN /mnt/realroot && sudo arch-chroot /mnt/realroot",
            ))
            return steps

        needs_fix = False

        # هل grub.cfg يشير للقطة؟
        linux_line = _get_main_grub_entry_linux_line()
        if linux_line and _grub_entry_points_to_snapshot(linux_line):
            needs_fix = True

        # هل rootflags غير مُفعّل؟
        if not _is_rootflags_protection_enabled():
            needs_fix = True
            steps.append(PreviewStep(
                description="إضافة rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT",
                command="sudo nano /etc/default/grub",
            ))

        if needs_fix:
            steps.append(PreviewStep(
                description="إعادة توليد grub.cfg",
                command="sudo grub-mkconfig -o /boot/grub/grub.cfg",
            ))
        else:
            steps.append(PreviewStep(
                description="لا توجد إجراءات ضرورية — النظام سليم.",
                command=None,
            ))

        return steps

    def apply(self) -> ApplyResult:
        root_source = _get_root_source()
        if _is_booted_from_snapshot(root_source):
            return ApplyResult(
                success=False,
                message="لا يمكن الإصلاح تلقائياً من داخل لقطة. استخدم 'تشخيص تفصيلي' للخطوات اليدوية.",
            )

        # 1) تفعيل الحل الوقائي إن لم يكن مُفعّلاً
        grub_default = "/etc/default/grub"
        if not _is_rootflags_protection_enabled() and os.path.isfile(grub_default):
            # قراءة الملف
            with open(grub_default, "r") as f:
                content = f.read()

            # إضافة rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT
            # نبحث عن السطر ونُلحق القيمة قبل علامة الإقفال الأخيرة
            modified = []
            for line in content.splitlines():
                if line.strip().startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    # أضف rootflags=subvol=@ إن لم يكن موجوداً
                    if "rootflags=subvol=@" not in line:
                        # أضف قبل علامة الإقفال الأخيرة
                        if line.rstrip().endswith("'"):
                            line = line.rstrip()[:-1] + " rootflags=subvol=@'"
                        elif line.rstrip().endswith('"'):
                            line = line.rstrip()[:-1] + ' rootflags=subvol=@"'
                modified.append(line)

            # كتابة الملف عبر pkexec (يحتاج صلاحيات جذر)
            new_content = "\n".join(modified)
            # نكتب عبر ملف مؤقت + pkexec cp
            tmp_path = "/tmp/grub_default_modified"
            with open(tmp_path, "w") as f:
                f.write(new_content)
            cp_result = run_privileged(["cp", tmp_path, grub_default])
            os.unlink(tmp_path)
            if not cp_result.ok:
                return ApplyResult(
                    success=False,
                    message=f"فشل تحديث /etc/default/grub: {cp_result.stderr}",
                )

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
