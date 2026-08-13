#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/disk_analyzer.py
===========================
وحدة "إخبارية" (informational) — تعرض أكبر 10 ملفات في مجلد المستخدم
وحجم /tmp، دون تنفيذ أي حذف تلقائي. حذف الملفات الشخصية قرار لا يجوز
لأداة صيانة عامة اتخاذه نيابة عن المستخدم — الفحص هنا يعطي معلومة
لاتخاذ قرار يدوي (نفس نهج "Disk Analyzer" في WinDirStat، لا "حذف تلقائي").

لذلك: findings.actionable = False دائماً، ولا preview()/apply() فعلي.
هذا نمط متعمَّد ضمن core/module_base.py: وحدة قد تكون "إخبارية بحتة".
"""

from __future__ import annotations
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("disk_analyzer")

_TOP_N = 10


def _largest_files_in_home() -> list[tuple[str, int]]:
    home = str(Path.home())
    # -xdev: لا يعبر نقاط التحميل
    # استثناء المجلدات الثقيلة عديمة الفائدة (.cache, .mozilla, .steam...)
    # لتقليل وقت البحث من ~30s إلى ~3-5s
    result = run_unprivileged(
        ["/usr/bin/find", home, "-xdev", "-type", "f", "-size", "+100M",
         "-not", "-path", "*/.cache/*",
         "-not", "-path", "*/.local/share/Trash/*",
         "-not", "-path", "*/.mozilla/*",
         "-not", "-path", "*/.config/google-chrome/*",
         "-not", "-path", "*/.config/chromium/*",
         "-not", "-path", "*/node_modules/*",
         "-not", "-path", "*/.local/share/containers/*",
         "-not", "-path", "*/.steam/*",
         "-not", "-path", "*/.var/*",
         "-printf", "%s %p\n"],
        timeout=30,
    )
    if not result.ok and not result.stdout:
        return []
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            entries.append((parts[1], int(parts[0])))
    entries.sort(key=lambda e: e[1], reverse=True)
    return entries[:_TOP_N]


def _tmp_size_mb() -> float:
    result = run_unprivileged(["du", "-sm", "/tmp"])
    if not result.ok or not result.stdout.strip():
        return 0.0
    try:
        return float(result.stdout.split()[0])
    except (ValueError, IndexError):
        return 0.0


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class DiskAnalyzerModule(MaintenanceModule):
    name = "تحليل مساحة القرص"
    slug = "disk_analyzer"
    description = "يعرض أكبر الملفات في مجلد المستخدم وحجم /tmp — للاطلاع فقط، بلا حذف تلقائي"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "drive-harddisk"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        large_files = _largest_files_in_home()

        if large_files:
            detail_lines = [f"{_human_size(size)} — {path}" for path, size in large_files]
            findings.append(ScanFinding(
                title=f"أكبر {len(large_files)} ملفات في مجلد المستخدم (أكبر من 100MB)",
                detail="\n".join(detail_lines),
                severity=Severity.INFO,
                actionable=False,  # معلومة فقط — الحذف قرار يدوي بحت
            ))
        else:
            findings.append(ScanFinding(
                title="لا ملفات كبيرة بشكل ملحوظ",
                detail="لا يوجد ملف أكبر من 100MB في مجلد المستخدم.",
                severity=Severity.OK,
                actionable=False,
            ))

        tmp_mb = _tmp_size_mb()
        if tmp_mb > 1024:
            findings.append(ScanFinding(
                title=f"مجلد /tmp كبير: {tmp_mb:.0f} MB",
                detail="يُنظَّف عادة تلقائياً عند إعادة الإقلاع — لا حاجة لتدخّل يدوي عادة.",
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="هذه وحدة إخبارية فقط — لا يوجد إجراء تلقائي. راجع نتائج الفحص واحذف يدوياً ما تراه مناسباً.",
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="لا إجراء تلقائي لهذه الوحدة — هي للاطلاع فقط.",
        )
