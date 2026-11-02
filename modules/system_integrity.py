#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تدقيق اتساق الإقلاع وBtrfs وinitramfs — قراءة فقط."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from core.module_base import (
    ApplyResult,
    MaintenanceModule,
    PreviewStep,
    RiskLevel,
    ScanFinding,
    ScanResult,
    Severity,
)
from core.privilege import run_unprivileged


def parse_root_mount(text: str) -> dict[str, str]:
    """تحليل سطر findmnt: SOURCE FSTYPE UUID OPTIONS."""
    parts = text.strip().split(None, 3)
    if len(parts) < 2:
        return {}
    return {
        "source": parts[0],
        "fstype": parts[1],
        "uuid": parts[2] if len(parts) > 2 else "",
        "options": parts[3] if len(parts) > 3 else "",
    }


def parse_mkinitcpio_preset(text: str) -> list[tuple[str, str]]:
    """استخراج مسارات الصور والنواة دون تنفيذ أو source لملف preset."""
    rows = []
    pattern = re.compile(r"""^\s*(default_image|fallback_image|ALL_kver)\s*=\s*["']?([^"'\s]+)""")
    for line in text.splitlines():
        match = pattern.match(line)
        if match and not match.group(2).startswith("$"):
            rows.append((match.group(1), match.group(2)))
    return rows


class SystemIntegrityModule(MaintenanceModule):
    name = "سلامة الإقلاع والنظام"
    slug = "system_integrity"
    description = (
        "فحص مصدر الجذر وfstab وصياغة grub.cfg ومسارات mkinitcpio "
        "وتفاصيل مساحة Btrfs — قراءة فقط دون تعديل الإقلاع"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "shield-check"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        root = run_unprivileged([
            "findmnt", "--noheadings", "--raw",
            "--output", "SOURCE,FSTYPE,UUID,OPTIONS", "/",
        ])
        mount = parse_root_mount(root.stdout) if root.ok else {}
        if mount:
            findings.append(ScanFinding(
                title=f"مصدر الجذر: {mount['source']} ({mount['fstype']})",
                detail=f"UUID: {mount['uuid'] or 'غير متاح'}\nOptions: {mount['options']}",
                severity=Severity.INFO, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="تعذر تحديد مصدر نظام الملفات الجذر",
                detail=root.stderr.strip() or "لم تُرجع findmnt بيانات قابلة للتحليل.",
                severity=Severity.INFO, actionable=False,
            ))

        fstab = run_unprivileged([
            "findmnt", "--verify", "--verbose", "--tab-file", "/etc/fstab",
        ])
        if fstab.ok:
            findings.append(ScanFinding(
                title="تحقق fstab: لم يُبلغ findmnt عن أخطاء",
                detail=fstab.stdout.strip()[-1800:],
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="findmnt اكتشف مشكلة أو تحذيراً في fstab",
                detail=(fstab.stdout + "\n" + fstab.stderr).strip()[-3000:],
                severity=Severity.WARNING, actionable=False,
            ))

        grub_cfg = Path("/boot/grub/grub.cfg")
        if grub_cfg.is_file() and shutil.which("grub-script-check"):
            check = run_unprivileged(["grub-script-check", str(grub_cfg)])
            findings.append(ScanFinding(
                title="فحص صياغة grub.cfg: " + ("سليم" if check.ok else "يحتاج مراجعة"),
                detail=(check.stdout + "\n" + check.stderr).strip()[:1800],
                severity=Severity.OK if check.ok else Severity.WARNING,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="فحص grub.cfg غير متاح",
                detail="ملف grub.cfg أو أداة grub-script-check غير متاحة؛ لم يُنشأ أو يُعدّل أي ملف.",
                severity=Severity.INFO, actionable=False,
            ))

        presets = sorted(Path("/etc/mkinitcpio.d").glob("*.preset"))
        missing = []
        checked = 0
        for preset in presets:
            try:
                content = preset.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for key, value in parse_mkinitcpio_preset(content):
                checked += 1
                target = Path(value)
                if target.is_absolute() and not target.exists():
                    missing.append(f"{preset.name}: {key} -> {value}")
        if missing:
            findings.append(ScanFinding(
                title=f"مسارات نواة/initramfs مفقودة في {len(missing)} إعداد",
                detail="\n".join(missing[:20]) + "\nلم يُشغّل mkinitcpio ولم تُعدّل ملفات الإقلاع.",
                severity=Severity.WARNING, actionable=False, raw_value=missing,
            ))
        elif presets:
            findings.append(ScanFinding(
                title=f"مسارات mkinitcpio: لا توجد ملفات مفقودة ضمن {checked} مرجعاً",
                detail=f"عدد ملفات preset: {len(presets)}",
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="لا توجد ملفات mkinitcpio preset",
                detail="قد يستخدم النظام أداة توليد initramfs مختلفة؛ لا يُعد ذلك خطأ بحد ذاته.",
                severity=Severity.INFO, actionable=False,
            ))

        if mount.get("fstype") == "btrfs":
            usage = run_unprivileged(["btrfs", "filesystem", "usage", "--raw", "/"])
            if usage.ok:
                findings.append(ScanFinding(
                    title="تفاصيل توزيع مساحة Btrfs",
                    detail=usage.stdout.strip()[:3500],
                    severity=Severity.INFO, actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title="تفاصيل Btrfs تحتاج صلاحيات إضافية أو الأداة غير متاحة",
                    detail="لم تُطلب صلاحيات جذر أثناء الفحص. يمكن قراءة btrfs filesystem usage / يدوياً عند الحاجة.",
                    severity=Severity.INFO, actionable=False,
                ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="فحوص قراءة فقط لمصدر الجذر وfstab وGRUB وmkinitcpio وBtrfs؛ لا توجد أوامر إصلاح."
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="هذه الوحدة تشخيصية فقط؛ لم تُعدّل fstab أو GRUB أو initramfs أو Btrfs.",
        )
