#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/registry.py
====================
نقطة التسجيل المركزية لكل وحدات الصيانة. إضافة وحدة جديدة مستقبلاً
(mirror_rank, journal_vacuum, kernel_cleanup, startup_manager...)
تتطلب فقط:
  1) كتابة ملف modules/xxx.py يرث من MaintenanceModule
  2) إضافة سطر استيراد + إضافة الكلاس هنا

لا حاجة لتعديل أي كود في core/ أو gui/ عند إضافة وحدة جديدة.
"""

from __future__ import annotations

from core.module_base import MaintenanceModule

from modules.network_reset import NetworkResetModule
from modules.pkg_cleanup import PackageCleanupModule
from modules.failed_services import FailedServicesModule
from modules.journal_vacuum import JournalVacuumModule
from modules.mirror_rank import MirrorRankModule
from modules.kernel_cleanup import KernelCleanupModule
from modules.disk_analyzer import DiskAnalyzerModule
from modules.startup_manager import StartupManagerModule


def get_all_modules() -> list[MaintenanceModule]:
    """يُرجع نسخة جديدة من كل وحدة مسجّلة، بالترتيب المطلوب عرضه في الواجهة.

    الترتيب: الأكثر أماناً/فائدة يومية أولاً، الأكثر حساسية (kernel_cleanup)
    قرب النهاية، والوحدات الإخبارية البحتة (disk_analyzer, startup_manager)
    في الآخر لأنها لا تتطلب قراراً فورياً.
    """
    return [
        NetworkResetModule(),
        FailedServicesModule(),
        PackageCleanupModule(),
        JournalVacuumModule(),
        MirrorRankModule(),
        KernelCleanupModule(),
        DiskAnalyzerModule(),
        StartupManagerModule(),
    ]
