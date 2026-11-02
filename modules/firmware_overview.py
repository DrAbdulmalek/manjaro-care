#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only firmware and UEFI inventory; no firmware variables are modified."""
from __future__ import annotations

import shutil
from pathlib import Path

from core.module_base import (
    ApplyResult, MaintenanceModule, PreviewStep, RiskLevel, ScanFinding,
    ScanResult, Severity,
)
from core.privilege import run_unprivileged


_DMI_FIELDS = {
    "الشركة المصنعة": "sys_vendor",
    "طراز الجهاز": "product_name",
    "اللوحة الأم": "board_name",
    "مصنّع BIOS/UEFI": "bios_vendor",
    "إصدار BIOS/UEFI": "bios_version",
    "تاريخ BIOS/UEFI": "bios_date",
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "غير متاح أو محجوب الصلاحيات"


def _command_output(command: list[str]) -> str:
    result = run_unprivileged(command, timeout=15)
    if result.ok:
        return result.stdout.strip() or "لم تُرجع الأداة معلومات."
    return (result.stderr or result.stdout).strip() or f"تعذر التنفيذ (رمز {result.returncode})"


def collect_firmware_report() -> dict[str, object]:
    """Collect firmware details using read-only commands and sysfs files."""
    efi_dir = Path("/sys/firmware/efi")
    is_uefi = efi_dir.is_dir()
    lines = [
        "تقرير البرامج الثابتة والإقلاع",
        "================================",
        f"وضع الإقلاع الحالي: {'UEFI' if is_uefi else 'Legacy BIOS أو UEFI غير مكشوف للنظام'}",
        "",
        "معلومات الجهاز واللوحة:",
    ]
    for label, filename in _DMI_FIELDS.items():
        lines.append(f"{label}: {_read_text(Path('/sys/class/dmi/id') / filename)}")

    lines.extend(["", "النواة الحالية:", _command_output(["uname", "-r"])])

    if is_uefi:
        lines.extend(["", "حالة محمّل الإقلاع (bootctl):"])
        lines.append(
            _command_output(["bootctl", "status", "--no-pager"])
            if shutil.which("bootctl") else "أداة bootctl غير مثبتة."
        )
        lines.extend(["", "مدخلات UEFI (efibootmgr):"])
        lines.append(
            _command_output(["efibootmgr", "-v"])
            if shutil.which("efibootmgr") else "أداة efibootmgr غير مثبتة."
        )
        lines.extend(["", "حالة Secure Boot:"])
        lines.append(
            _command_output(["mokutil", "--sb-state"])
            if shutil.which("mokutil") else
            "أداة mokutil غير مثبتة؛ راجع حالة Secure Boot من تقرير bootctl أو إعدادات UEFI."
        )
    else:
        lines.extend([
            "",
            "معلومات UEFI غير متاحة في هذه الجلسة. لم تُجرَ محاولة لتعديل نمط الإقلاع.",
        ])

    lines.extend([
        "",
        "حدود التقرير:",
        "- قراءة فقط؛ لا يغيّر NVRAM أو Secure Boot أو إعدادات firmware.",
        "- قد لا تتوفر بعض الحقول إذا كانت الأدوات غير مثبتة أو كانت صلاحيات القراءة محدودة.",
        "- لا يتضمن التقرير الرقم التسلسلي أو مفاتيح Secure Boot أو محتويات متغيرات EFI.",
    ])
    return {"is_uefi": is_uefi, "report": "\\n".join(lines)}


class FirmwareOverviewModule(MaintenanceModule):
    name = "معلومات Firmware وUEFI"
    slug = "firmware_overview"
    description = "معلومات BIOS/UEFI واللوحة ومدخلات الإقلاع وSecure Boot مع تقرير قابل للتصدير"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "computer"
    has_custom_ui = True

    def scan(self) -> ScanResult:
        try:
            data = collect_firmware_report()
        except Exception as exc:
            return ScanResult(module_name=self.name, error=f"تعذر جمع معلومات Firmware: {exc}")
        mode = "UEFI" if data["is_uefi"] else "Legacy/غير معروف"
        return ScanResult(module_name=self.name, findings=[ScanFinding(
            title=f"وضع الإقلاع: {mode}",
            detail=str(data["report"])[:5000],
            severity=Severity.INFO, actionable=False, raw_value=data,
        )])

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="قراءة معلومات firmware وEFI وتصدير تقرير اختياري. لا توجد تغييرات على إعدادات الإقلاع."
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="هذه الوحدة معلوماتية؛ لم تُعدّل متغيرات EFI أو إعدادات firmware.",
        )
