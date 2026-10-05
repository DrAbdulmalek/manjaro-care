#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/registry.py — نقطة التسجيل المركزية."""
from __future__ import annotations

from modules.app_uninstaller import AppUninstallerModule
from modules.archive_extract import ArchiveExtractModule
from modules.boot_guard import BootGuardModule
from modules.boot_manager import BootManagerModule
from modules.boot_sanity import BootSanityModule
from modules.btrfs_health import BtrfsHealthModule
from modules.btrfs_snapper import BtrfsSnapperModule
from modules.dashboard import DashboardModule
from modules.disk_analyzer import DiskAnalyzerModule
from modules.disk_optimizer import DiskOptimizerModule
from modules.driver_manager import DriverManagerModule

# 🆕 وحدات جديدة مستوحاة من أفضل برامج الويندوز 2026
from modules.duplicate_finder import DuplicateFinderModule
from modules.failed_services import FailedServicesModule
from modules.file_shredder import FileShredderModule

# وحدات Garuda-style
from modules.firewall_manager import FirewallManagerModule
from modules.flatpak_cleanup import FlatpakCleanupModule
from modules.font_toolkit import FontToolkitModule
from modules.gamescope_hdr import GamescopeHdrModule
from modules.journal_vacuum import JournalVacuumModule
from modules.kernel_cleanup import KernelCleanupModule
from modules.large_file_finder import LargeFileFinderModule
from modules.locale_manager import LocaleManagerModule
from modules.mirror_rank import MirrorRankModule

# الوحدات الأصلية
from modules.network_reset import NetworkResetModule
from modules.one_click_maintenance import OneClickMaintenanceModule
from modules.pacman_maintenance import PacmanMaintenanceModule
from modules.pdf_toolkit import PdfToolkitModule
from modules.performance_optimizer import PerformanceOptimizerModule
from modules.pkg_cleanup import PackageCleanupModule
from modules.printer_manager import PrinterManagerModule
from modules.ram_booster import RamBoosterModule
from modules.repo_manager import RepoManagerModule
from modules.report_export import ReportExportModule
from modules.snapper_cleanup import SnapperCleanupModule
from modules.snapshot_before_update import SnapshotBeforeUpdateModule
from modules.software_updater import SoftwareUpdaterModule
from modules.startup_impact import StartupImpactModule
from modules.startup_manager import StartupManagerModule

# 🆕 وحدات CCleaner / TuneUp / ASC / IObit
from modules.system_cleaner import SystemCleanerModule
from modules.system_info import SystemInfoModule
from modules.tcp_optimizer import TcpOptimizerModule
from modules.time_manager import TimeManagerModule
from modules.update_check import UpdateCheckModule
from modules.user_manager import UserManagerModule


def get_all_modules():
    return [
        # معلومات وصيانة سريعة
        DashboardModule(),
        SystemInfoModule(),
        PacmanMaintenanceModule(),
        OneClickMaintenanceModule(),
        StartupImpactModule(),
        ReportExportModule(),  # تقرير منقّى (نافذة معاينة مخصصة)

        # التنظيف والصيانة
        SystemCleanerModule(),
        PackageCleanupModule(),
        FlatpakCleanupModule(),
        JournalVacuumModule(),
        SnapperCleanupModule(),
        SnapshotBeforeUpdateModule(),  # لقطة pre-update + رجوع (نافذة مخصصة)
        UpdateCheckModule(),  # إخبارية: pacnew + مزامنة + خدمات فاشلة + أخبار
        BtrfsHealthModule(),  # صحة btrfs + scrub/fstrim (نافذة مخصصة)

        # إدارة البرامج
        AppUninstallerModule(),
        SoftwareUpdaterModule(),
        DuplicateFinderModule(),
        LargeFileFinderModule(),

        # أدوات ملفات ووسائط (مستوردة من طقم المستخدم الشخصي)
        ArchiveExtractModule(),   # الاستخراج الآمن للأرشيفات (safe_extract.sh)
        PdfToolkitModule(),       # صور→PDF / OCR / استخراج نص
        FontToolkitModule(),      # ttx / subset / merge

        # الأداء والتحسين
        PerformanceOptimizerModule(),
        RamBoosterModule(),
        DiskOptimizerModule(),
        TcpOptimizerModule(),
        KernelCleanupModule(),

        # الألعاب
        # game_mode لا يوجد له وحدة — نافذة مخصصة فقط
        GamescopeHdrModule(),  # توفر gamescope + ملف HDR الافتراضي (الإطلاق من نافذة الألعاب)

        # الحماية والخصوصية
        # ملاحظة: PrivacyGuardModule كانت تُنشأ مرتين (هنا وفي قسم التنظيف
        # أعلاه) فتظهر بطاقتها مرتين وتُفحص مرتين في "الفحص الشامل" —
        # أُبقي الوجود في قسم الحماية والخصوصية فقط.
        FirewallManagerModule(),
        FileShredderModule(),

        # الإعدادات
        BootManagerModule(),
        BootGuardModule(),  # الأعلى أولوية: حارس انزلاق الإقلاع على btrfs (حساس)
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
