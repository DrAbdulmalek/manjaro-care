#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اختبار انحدار لسجل الوحدات: كل وحدة تُستورد يجب أن تُسجَّل فعلياً.

الانتكاسة التي يمنعها هذا الملف: استيراد وحدات جديدة في modules/registry.py
دون إضافة نسخ منها إلى get_all_modules() — فلا تظهر في الواجهة ولا تُفحص
(حدث فعلياً مع thermal_power وservice_audit قبل إصلاحه).
"""
from modules.registry import get_all_modules


def test_new_diagnostic_modules_are_registered():
    slugs = {module.slug for module in get_all_modules()}
    assert "thermal_power" in slugs
    assert "service_audit" in slugs


def test_registry_slugs_are_unique():
    slugs = [module.slug for module in get_all_modules()]
    assert len(slugs) == len(set(slugs))


def test_every_module_has_required_metadata():
    for module in get_all_modules():
        assert module.slug and module.slug != "unnamed", f"slug مفقود: {module}"
        assert module.name and module.name != "وحدة بلا اسم", f"اسم مفقود: {module}"
        assert module.description, f"وصف مفقود: {module.slug}"
