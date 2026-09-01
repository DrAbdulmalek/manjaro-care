#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/registry.py — نقطة التسجيل المركزية."""
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

# وحدات جديدة مستوحاة من Garuda Assistant
from modules.firewall_manager import FirewallManagerModule
from modules.repo_manager import RepoManagerModule
from modules.locale_manager import LocaleManagerModule
from modules.time_manager import TimeManagerModule
from modules.boot_sanity import BootSanityModule
from modules.boot_sanity import BootSanityModule
from modules.boot_manager import BootManagerModule
from modules.system_info import SystemInfoModule
from modules.driver_manager import DriverManagerModule
from modules.btrfs_snapper import BtrfsSnapperModule
from modules.printer_manager import PrinterManagerModule
from modules.user_manager import UserManagerModule
from modules.flatpak_cleanup import FlatpakCleanupModule
from modules.snapper_cleanup import SnapperCleanupModule


def get_all_modules():
    return [
        SystemInfoModule(),
        NetworkResetModule(),
        FailedServicesModule(),
        FirewallManagerModule(),
        PackageCleanupModule(),
        JournalVacuumModule(),
        MirrorRankModule(),
        RepoManagerModule(),
        DiskAnalyzerModule(),
        FlatpakCleanupModule(),
        KernelCleanupModule(),
        DriverManagerModule(),
        BootManagerModule(),
        BtrfsSnapperModule(),
        BootSanityModule(),
        BootSanityModule(),
        SnapperCleanupModule(),
        LocaleManagerModule(),
        TimeManagerModule(),
        UserManagerModule(),
        PrinterManagerModule(),
        StartupManagerModule(),
    ]
