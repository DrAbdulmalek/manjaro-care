#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/driver_manager.py
==========================
فحص تعريفات GPU واقتراح التعريف المناسب عبر mhwd.
مستوحى من Garuda Settings Manager → Hardware Configuration.
"""
from __future__ import annotations
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("driver_manager")


def _gpu_info() -> str:
    if shutil.which("mhwd"):
        r = run_unprivileged(["mhwd", "-li"])
        return r.stdout or "mhwd لا يُرجع معلومات."
    if shutil.which("lspci"):
        r = run_unprivileged(["lspci", "-k"])
        for line in r.stdout.splitlines():
            if "VGA" in line or "3D" in line:
                return line.strip()
    return "تعذّر الكشف عن GPU."


def _recommended_driver() -> str:
    if not shutil.which("mhwd"):
        return "mhwd غير مثبت"
    r = run_unprivileged(["mhwd", "-a", "pci", "nonfree", "0300"])
    return r.stdout or r.stderr


class DriverManagerModule(MaintenanceModule):
    name = "إدارة التعريفات (GPU)"
    slug = "driver_manager"
    description = "فحص تعريفات GPU المثبتة واقتراح التعريف الأمثل عبر mhwd"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "video-display"

    def scan(self) -> ScanResult:
        gpu = _gpu_info()
        findings: list[ScanFinding] = []

        if "NVIDIA" in gpu.upper():
            findings.append(ScanFinding(
                title="GPU: NVIDIA",
                detail=f"{gpu}\n\nmhwd يمكنه تثبيت nvidia أو nvidia-390xx حسب الجيل.",
                severity=Severity.INFO,
                actionable=shutil.which("mhwd") is not None,
            ))
        elif "AMD" in gpu.upper() or "ATI" in gpu.upper():
            findings.append(ScanFinding(
                title="GPU: AMD/ATI",
                detail=f"{gpu}\n\nالتعريف المفتوح amdgpu/mesa مثبت عادةً افتراضياً.",
                severity=Severity.OK,
                actionable=False,
            ))
        elif "INTEL" in gpu.upper():
            findings.append(ScanFinding(
                title="GPU: Intel",
                detail=f"{gpu}\n\nالتعريف المفتوح intel/mesa مثبت افتراضياً.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="GPU غير معروف",
                detail=gpu,
                severity=Severity.INFO,
                actionable=False,
            ))

        if not shutil.which("mhwd"):
            findings.append(ScanFinding(
                title="mhwd غير مثبت",
                detail="هذه الأداة خاصة بـ Manjaro — إن لم تكن موجودة، ثبّتها: sudo pacman -S mhwd",
                severity=Severity.WARNING,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        if not shutil.which("mhwd"):
            return [PreviewStep(description="mhwd غير مثبت — لا يمكن اقتراح تعريف.")]
        return [PreviewStep(
            description="تثبيت التعريف الموصى به عبر mhwd",
            command="mhwd -a pci nonfree 0300",
        )]

    def apply(self) -> ApplyResult:
        if not shutil.which("mhwd"):
            return ApplyResult(success=False, message="mhwd غير مثبت.")
        result = run_privileged(["mhwd", "-a", "pci", "nonfree", "0300"])
        return ApplyResult(
            success=result.ok,
            message="تم تثبيت التعريف" if result.ok else f"فشل (كود {result.returncode})",
            log_output=result.stdout + result.stderr,
        )
