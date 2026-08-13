#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/scanner.py
===============
يكتشف كل الوحدات المسجّلة في modules/ تلقائياً (عبر REGISTRY)، ويشغّل
scan() الخاص بكل واحدة، ثم يرتّب النتائج حسب الخطورة لعرضها في قسم
"الاقتراحات الذكية" بالواجهة الرئيسية — هذا يحاكي وظيفة Advanced
SystemCare في إعطاء "لمحة صحة سريعة" عند فتح التطبيق.

إضافة وحدة جديدة لاحقاً لا تتطلب تعديل هذا الملف إطلاقاً — فقط سجّلها
في modules/registry.py.
"""

from __future__ import annotations
from dataclasses import dataclass

from core.module_base import MaintenanceModule, ScanResult, Severity
from core.logger import get_logger

log = get_logger("scanner")


@dataclass
class SystemHealthReport:
    results: list[ScanResult]

    @property
    def total_findings(self) -> int:
        return sum(len(r.findings) for r in self.results)

    @property
    def critical_count(self) -> int:
        return sum(
            1 for r in self.results for f in r.findings
            if f.severity == Severity.CRITICAL
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for r in self.results for f in r.findings
            if f.severity == Severity.WARNING
        )

    def sorted_by_severity(self) -> list[ScanResult]:
        order = {
            Severity.CRITICAL: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2,
            Severity.OK: 3,
        }
        return sorted(self.results, key=lambda r: order[r.worst_severity])


def run_full_scan(modules: list[MaintenanceModule]) -> SystemHealthReport:
    """يشغّل scan() لكل وحدة، ويتحمّل فشل وحدة واحدة دون إيقاف الباقي."""
    results: list[ScanResult] = []
    for module in modules:
        try:
            log.info("فحص الوحدة: %s", module.slug)
            result = module.scan()
        except Exception as exc:  # noqa: BLE001 — نريد عزل أي عطل بوحدة واحدة
            log.exception("فشل فحص الوحدة %s", module.slug)
            result = ScanResult(module_name=module.name, error=str(exc))
        results.append(result)
    return SystemHealthReport(results=results)
