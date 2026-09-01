#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/large_file_finder.py — البحث عن الملفات الكبيرة."""
from __future__ import annotations
import os
from pathlib import Path
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("large_file_finder")

# الحد الأدنى: 100 ميجا
MIN_SIZE_MB = 100


def _find_large_files(paths: list[str], min_bytes: int) -> list[tuple[str, int]]:
    results = []
    for base in paths:
        base_path = Path(base).expanduser()
        if not base_path.exists():
            continue
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                fpath = Path(root) / fname
                try:
                    fsize = fpath.stat().st_size
                    if fsize >= min_bytes:
                        results.append((str(fpath), fsize))
                except (OSError, PermissionError):
                    continue
    return sorted(results, key=lambda x: x[1], reverse=True)


class LargeFileFinderModule(MaintenanceModule):
    name = "البحث عن الملفات الكبيرة 📦"
    slug = "large_file_finder"
    description = f"يجد الملفات الأكبر من {MIN_SIZE_MB}MB لتحرير مساحة القرص"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "folder-open"

    def scan(self):
        search_paths = ["~/Downloads", "~/Videos", "~/Documents", "~/.cache", "/var/log"]
        large = _find_large_files(search_paths, MIN_SIZE_MB * 1024 * 1024)

        findings = []
        if large:
            total_size = sum(s for _, s in large)
            top = large[:10]
            detail = "\n".join(f"  • {p} ({self._hs(s)})" for p, s in top)
            findings.append(ScanFinding(
                title=f"{len(large)} ملف كبير ({self._hs(total_size)})",
                detail=detail + (f"\n  ... و {len(large)-10} آخرون" if len(large) > 10 else ""),
                severity=Severity.INFO,
                actionable=True,
                raw_value=large,
            ))
        else:
            findings.append(ScanFinding(
                title="لا ملفات كبيرة",
                detail=f"لا يوجد ملفات أكبر من {MIN_SIZE_MB}MB.",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [PreviewStep(description="عرض الملفات الكبيرة — يتطلب حذف يدوي لضمان الأمان.")]

    def apply(self):
        # هذه الوحدة إخبارية فقط — الحذف يدوي لضمان الأمان
        return ApplyResult(
            success=True,
            message="استخدم نتائج الفحص لحذف الملفات يدوياً.",
        )

    @staticmethod
    def _hs(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
