#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/registry.py — نقطة التسجيل المركزية."""
from __future__ import annotations

from core.module_base import MaintenanceModule

# الوحدات الأصلية
from modules.network_reset import NetworkResetModule
from modules.pkg_cleanup import PackageCleanupModule
from modules.failed_services import FailedServicesModule
from modules.journal_vacuum import JournalVacuumModule
from modules.mirror_rank import MirrorRankModule
from modules.kernel_cleanup import KernelCleanupModule
from modules.disk_analyzer import DiskAnalyzerModule
from modules.startup_manager import StartupManagerModule

# وحدات Garuda-style
from modules.firewall_manager import FirewallManagerModule
from modules.repo_manager import RepoManagerModule
from modules.locale_manager import LocaleManagerModule
from modules.time_manager import TimeManagerModule
from modules.boot_sanity import BootSanityModule
from modules.boot_manager import BootManagerModule
from modules.system_info import SystemInfoModule
from modules.driver_manager import DriverManagerModule
from modules.btrfs_snapper import BtrfsSnapperModule
from modules.printer_manager import PrinterManagerModule
from modules.user_manager import UserManagerModule
from modules.flatpak_cleanup import FlatpakCleanupModule
from modules.snapper_cleanup import SnapperCleanupModule

# 🆕 وحدات CCleaner / TuneUp / ASC / IObit
from modules.system_cleaner import SystemCleanerModule
from modules.privacy_guard import PrivacyGuardModule
from modules.performance_optimizer import PerformanceOptimizerModule
from modules.app_uninstaller import AppUninstallerModule

# 🆕 وحدات جديدة مستوحاة من أفضل برامج الويندوز 2026
from modules.duplicate_finder import DuplicateFinderModule
from modules.large_file_finder import LargeFileFinderModule
from modules.startup_impact import StartupImpactModule
from modules.software_updater import SoftwareUpdaterModule
from modules.disk_optimizer import DiskOptimizerModule
from modules.ram_booster import RamBoosterModule
from modules.file_shredder import FileShredderModule
from modules.one_click_maintenance import OneClickMaintenanceModule
from modules.tcp_optimizer import TcpOptimizerModule


def get_all_modules():
    return [
        # معلومات وصيانة سريعة
        SystemInfoModule(),
        OneClickMaintenanceModule(),
        StartupImpactModule(),
        
        # التنظيف والصيانة
        SystemCleanerModule(),
        PrivacyGuardModule(),
        PackageCleanupModule(),
        FlatpakCleanupModule(),
        JournalVacuumModule(),
        SnapperCleanupModule(),
        
        # إدارة البرامج
        AppUninstallerModule(),
        SoftwareUpdaterModule(),
        DuplicateFinderModule(),
        LargeFileFinderModule(),
        
        # الأداء والتحسين
        PerformanceOptimizerModule(),
        RamBoosterModule(),
        DiskOptimizerModule(),
        TcpOptimizerModule(),
        KernelCleanupModule(),
        
        # الألعاب
        # game_mode لا يوجد له وحدة — نافذة مخصصة فقط
        
        # الحماية والخصوصية
        FirewallManagerModule(),
        PrivacyGuardModule(),
        FileShredderModule(),
        
        # الإعدادات
        BootManagerModule(),
        StartupManagerModule(),
        RepoManagerModule(),
        MirrorRankModule(),
        LocaleManagerModule(),
        TimeManagerModule(),
        NetworkResetModule(),
        
        # العتاد والمعلومات
        DriverManagerModule(),
        DiskAnalyzerModule(),
        BtrfsSnapperModule(),
        BootSanityModule(),
        
        # الخدمات والمستخدمين
        FailedServicesModule(),
        UserManagerModule(),
        PrinterManagerModule(),
    ]
