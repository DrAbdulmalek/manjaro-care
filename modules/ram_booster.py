#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/ram_booster.py — تنظيف الذاكرة وتقليل الـ cache."""
from __future__ import annotations
import psutil
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("ram_booster")


def _get_ram_info():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return mem, swap


class RamBoosterModule(MaintenanceModule):
    name = "معزز الذاكرة 🧠"
    slug = "ram_booster"
    description = "تنظيف cache النظام وتحرير الذاكرة المستخدمة"
    needs_root = True
    risk_level = RiskLevel.SAFE
    icon = "memory"

    def scan(self):
        mem, swap = _get_ram_info()
        findings = []

        findings.append(ScanFinding(
            title=f"الذاكرة: {mem.percent}% مستخدمة ({self._hs(mem.used)} / {self._hs(mem.total)})",
            detail=f"متاح: {self._hs(mem.available)} | SWAP: {swap.percent}%",
            severity=Severity.WARNING if mem.percent > 85 else Severity.INFO,
            actionable=True,
        ))

        if mem.percent > 90:
            findings.append(ScanFinding(
                title="⚠️ ذاكرة ممتلئة تقريباً",
                detail="يُنصح بتنظيف cache النظام.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [
            PreviewStep(description="تنظيف pagecache, dentries and inodes", command="sync && echo 3 > /proc/sys/vm/drop_caches"),
            PreviewStep(description="تقليل swappiness مؤقتاً", command="sysctl vm.swappiness=10"),
        ]

    def apply(self):
        logs = []
        # تنظيف cache (آمن — يعيد قراءة من القرص فقط)
        r1 = run_privileged(["bash", "-c", "sync && echo 3 > /proc/sys/vm/drop_caches"])
        logs.append("تم تنظيف cache النظام.")

        # تقليل swappiness مؤقتاً
        r2 = run_privileged(["sysctl", "vm.swappiness=10"])
        logs.append(r2.stdout + r2.stderr)

        return ApplyResult(
            success=True,
            message="تم تحرير الذاكرة",
            log_output="\n".join(logs),
        )

    @staticmethod
    def _hs(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
