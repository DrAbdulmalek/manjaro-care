#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تجميع نتائج الوحدات في أقسام صحة موحدة دون إعادة تشغيل أي فحص."""
from __future__ import annotations

from collections import defaultdict

from core.module_base import ScanFinding, Severity
from core.scanner import SystemHealthReport

_CATEGORIES = [
    ("boot_storage", "الإقلاع والتخزين", ("الإقلاع", "btrfs", "القرص", "snapshot", "snapper")),
    ("packages", "الحزم والمكتبات", ("الحزم", "pacman", "البرامج", "المستودعات")),
    ("thermal_power", "الحرارة والطاقة", ("الحرارة", "الطاقة", "العتاد")),
    ("services", "الخدمات", ("الخدمات", "service", "update_shutdown")),
    ("security", "الأمان والشبكة", ("الجدار", "الشبكة", "الخصوصية", "الحماية")),
    ("performance", "الأداء والموارد", ("الذاكرة", "المعالج", "العمليات", "الأداء")),
]
_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2, Severity.OK: 3}


def _category_for(module_name: str) -> tuple[str, str]:
    name = module_name.casefold()
    for key, label, markers in _CATEGORIES:
        if any(marker.casefold() in name for marker in markers):
            return key, label
    return "general", "فحوص عامة"


def build_health_sections(report: SystemHealthReport) -> list[dict]:
    """تحويل التقرير الموجود إلى أقسام؛ لا يستدعي scan ولا ينفذ أوامر."""
    grouped = defaultdict(lambda: {"key": "", "title": "", "findings": []})
    for result in report.results:
        key, title = _category_for(result.module_name)
        section = grouped[key]
        section["key"], section["title"] = key, title
        if result.error:
            section["findings"].append(ScanFinding(
                title=f"الفحص غير مكتمل: {result.module_name}",
                detail=result.error,
                severity=Severity.INFO,
                actionable=False,
            ))
        section["findings"].extend(result.findings)

    sections = [section for section in grouped.values() if section["findings"]]
    for section in sections:
        section["findings"].sort(key=lambda item: _SEVERITY_ORDER[item.severity])
        section["critical"] = sum(f.severity == Severity.CRITICAL for f in section["findings"])
        section["warning"] = sum(f.severity == Severity.WARNING for f in section["findings"])
    sections.sort(key=lambda section: (
        min(_SEVERITY_ORDER[f.severity] for f in section["findings"]),
        section["title"],
    ))
    return sections
