#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/registry.py
====================
نقطة التسجيل المركزية لكل وحدات الصيانة. إضافة وحدة جديدة مستقبلاً
تتطلب فقط:
  1) كتابة ملف modules/xxx.py يرث من MaintenanceModule
  2) إضافة سطر استيراد + إضافة الكلاس هنا

لا حاجة لتعديل أي كود في core/ أو gui/ عند إضافة وحدة جديدة.

v1.3: أضيفت وحدات مستوحاة من Garuda Assistant/Toolbox.
"""

from __future__ import annotations

from core.module_base import MaintenanceModule

# ── الوحدات الأصلية ──
from modules.network_reset import NetworkResetModule
from modules.pkg_cleanup import PackageCleanupModule
from modules.failed_services import FailedServicesModule
from modules.journal_vacuum import JournalVacuumModule
from modules.mirror_rank import MirrorRankModule
from modules.kernel_cleanup import KernelCleanupModule
from modules.disk_analyzer import DiskAnalyzerModule
from modules.startup_manager import StartupManagerModule
from modules.boot_sanity import BootSanityModule

# ── وحدات جديدة مستوحاة من Garuda Assistant ──
from modules.system_info import SystemInfoModule
from modules.firewall_manager import FirewallManagerModule
from modules.repo_manager import RepoManagerModule
from modules.locale_manager import LocaleManagerModule
from modules.time_manager import TimeManagerModule
from modules.boot_manager import BootManagerModule
from modules.driver_manager import DriverManagerModule
from modules.btrfs_snapper import BtrfsSnapperModule
from modules.printer_manager import PrinterManagerModule
from modules.user_manager import UserManagerModule
from modules.flatpak_cleanup import FlatpakCleanupModule
from modules.snapper_cleanup import SnapperCleanupModule


def get_all_modules() -> list[MaintenanceModule]:
    """يُرجع نسخة جديدة من كل وحدة مسجّلة، بالترتيب المطلوب عرضه في الواجهة.

    الترتيب مقسّم لأقسام منطقية:
      1. صحة النظام العامة (معلومات، شبكة، خدمات، جدار ناري)
      2. صيانة الحزم والتخزين (تنظيف، سجلات، مرايا، مستودعات، قرص)
      3. النواة والإقلاع (نوى، تعريفات، إقلاع، لقطات)
      4. إعدادات النظام (لغة، وقت، مستخدمون، طابعات)
      5. بدء التشغيل
    """
    return [
        # ── صحة النظام العامة ──
        SystemInfoModule(),
        NetworkResetModule(),
        FailedServicesModule(),
        FirewallManagerModule(),

        # ── صيانة الحزم والتخزين ──
        PackageCleanupModule(),
        JournalVacuumModule(),
        MirrorRankModule(),
        RepoManagerModule(),
        DiskAnalyzerModule(),

        # ── النواة والتعريفات والإقلاع ──
        KernelCleanupModule(),
        DriverManagerModule(),
        BootManagerModule(),
        BtrfsSnapperModule(),

        # ── إعدادات النظام ──
        LocaleManagerModule(),
        TimeManagerModule(),
        UserManagerModule(),
        PrinterManagerModule(),

        # ── بدء التشغيل ──
        StartupManagerModule(),
    ]
