#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/boot_manager.py
========================
فحص إعدادات الإقلاع (GRUB) — هل grub-mkconfig محدّث؟ هل يوجد نواة بديلة؟
مستوحى من Garuda Assistant → Boot Options.
"""
from __future__ import annotations
import re
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("boot_manager")

_GRUB_CFG = Path("/boot/grub/grub.cfg")
_GRUB_DEFAULT = Path("/etc/default/grub")


def _grub_entries() -> list[str]:
    """يستخرج أسماء إدخالات GRUB من grub.cfg."""
    if not _GRUB_CFG.exists():
        return []
    try:
        text = _GRUB_CFG.read_text(encoding="utf-8", errors="ignore")
    except PermissionError:
        log.warning("لا توجد صلاحيات كافية لقراءة /boot/grub/grub.cfg")
        return []
    entries = []
    for line in text.splitlines():
        if line.strip().startswith("menuentry '"):
            name = line.split("'", 2)[1] if "'" in line else ""
            if name:
                entries.append(name)
    return entries


def _grub_timeout() -> int:
    """يقرأ timeout من /etc/default/grub."""
    if not _GRUB_DEFAULT.exists():
        return -1
    try:
        text = _GRUB_DEFAULT.read_text()
    except PermissionError:
        log.warning("لا توجد صلاحيات كافية لقراءة /etc/default/grub")
        return -1
    for line in text.splitlines():
        if line.strip().startswith("GRUB_TIMEOUT="):
            try:
                return int(line.split("=", 1)[1].strip().strip('"'))
            except ValueError:
                return -1
    return -1


class BootManagerModule(MaintenanceModule):
    name = "إدارة الإقلاع (GRUB)"
    slug = "boot_manager"
    description = "فحص إعدادات GRUB وعدد إدخالات الإقلاع المتاحة"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "drive-harddisk-system"

    def scan(self) -> ScanResult:
        entries = _grub_entries()
        timeout = _grub_timeout()
        findings: list[ScanFinding] = []

        if not entries:
            findings.append(ScanFinding(
                title="لم يُعثر على grub.cfg",
                detail="قد يكون النظام يستخدم systemd-boot بدل GRUB.",
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        findings.append(ScanFinding(
            title=f"{len(entries)} إدخال/إدخالات إقلاع",
            detail="\n".join(f"  • {e}" for e in entries[:10]),
            severity=Severity.INFO,
            actionable=False,
            raw_value=entries,
        ))

        if timeout == 0:
            findings.append(ScanFinding(
                title="GRUB timeout = 0",
                detail="لا يمكنك اختيار نواة بديلة عند الإقلاع — يُنصح بـ 5 ثوانٍ على الأقل.",
                severity=Severity.WARNING,
                actionable=True,
            ))
        elif timeout > 30:
            findings.append(ScanFinding(
                title=f"GRUB timeout طويل ({timeout} ثانية)",
                detail="يمكن تقليصه لتسريع الإقلاع.",
                severity=Severity.INFO,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        timeout = _grub_timeout()
        steps = []
        if timeout == 0 or timeout > 30:
            # التنفيذ الفعلي يتم من Python (نسخة احتياطية + كتابة آمنة عبر
            # core/file_ops.py) ثم grub-mkconfig — نعرض الخطوات كما ستحدث.
            steps.append(PreviewStep(
                description=f"تعيين GRUB_TIMEOUT إلى 5 ثوانٍ في {_GRUB_DEFAULT} (مع نسخة احتياطية)",
                command="GRUB_TIMEOUT=5  # تعديل سطر واحد فقط ثم:",
            ))
        steps.append(PreviewStep(
            description="إعادة توليد إعدادات GRUB",
            command="grub-mkconfig -o /boot/grub/grub.cfg",
        ))
        return steps or [PreviewStep(description="لا إجراء مطلوب.")]

    def apply(self) -> ApplyResult:
        timeout = _grub_timeout()
        logs = []

        if timeout == 0 or timeout > 30:
            # تعديل GRUB_TIMEOUT من Python مباشرة (argv فقط — بلا shell):
            # نقرأ الملف، نستبدل سطر GRUB_TIMEOUT وحده، نحفظ عبر
            # core/file_ops.py (نسخة احتياطية + كتابة آمنة) ثم grub-mkconfig.
            try:
                content = _GRUB_DEFAULT.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                return ApplyResult(success=False, message=f"تعذّرت قراءة {_GRUB_DEFAULT}: {exc}")

            new_content, n_subs = re.subn(
                r"^GRUB_TIMEOUT=.*$", "GRUB_TIMEOUT=5", content,
                count=1, flags=re.MULTILINE,
            )
            if n_subs == 0:
                # لا يوجد سطر GRUB_TIMEOUT أصلاً — نضيفه بعد آخر سطر إعداد
                new_content = content.rstrip("\n") + "\nGRUB_TIMEOUT=5\n"

            from core.file_ops import backup_root_file, write_root_file

            backup = backup_root_file(str(_GRUB_DEFAULT))
            if backup is None:
                return ApplyResult(
                    success=False,
                    message=f"فشل إنشاء نسخة احتياطية من {_GRUB_DEFAULT} — لن نُعدّل دون نسخة احتياطية.",
                )
            ok, err = write_root_file(str(_GRUB_DEFAULT), new_content)
            if not ok:
                return ApplyResult(success=False, message=f"فشل تعديل GRUB_TIMEOUT: {err}")
            logs.append(f"GRUB_TIMEOUT -> 5 (نسخة احتياطية: {backup})")

        r2 = run_privileged(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
        logs.append(r2.stdout + r2.stderr)

        return ApplyResult(
            success=r2.ok,
            message="تم تحديث إعدادات GRUB" if r2.ok else "فشل تحديث GRUB",
            log_output="\n".join(logs),
        )
