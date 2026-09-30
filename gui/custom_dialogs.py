#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/custom_dialogs.py — سجل مركزي للنوافذ المخصصة."""
from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import QDialog

from gui.archive_extract_dialog import ArchiveExtractDialog
from gui.boot_dialog import BootManagerDialog
from gui.boot_sanity_dialog import BootSanityDialog
from gui.btrfs_health_dialog import BtrfsHealthDialog
from gui.dashboard_widget import DashboardDialog
from gui.file_shredder_dialog import FileShredderDialog
from gui.firewall_dialog import FirewallManagerDialog
from gui.font_toolkit_dialog import FontToolkitDialog
from gui.game_mode_dialog import GameModeDialog
from gui.oneclick_dialog import OneClickMaintenanceDialog
from gui.pdf_toolkit_dialog import PdfToolkitDialog
from gui.repo_dialog import RepoManagerDialog
from gui.report_export_dialog import ReportExportDialog
from gui.snapshot_dialog import SnapshotDialog
from gui.startup_dialog import StartupManagerDialog
from gui.uninstaller_dialog import UninstallerDialog
from gui.update_check_dialog import UpdateCheckDialog

_REGISTRY: dict[str, Callable[..., QDialog]] = {
    "startup_manager": StartupManagerDialog,
    "boot_sanity": BootSanityDialog,
    "repo_manager": RepoManagerDialog,
    "firewall_manager": FirewallManagerDialog,
    "boot_manager": BootManagerDialog,
    "app_uninstaller": UninstallerDialog,
    "game_mode": GameModeDialog,
    "file_shredder": FileShredderDialog,
    "archive_extract": ArchiveExtractDialog,
    "pdf_toolkit": PdfToolkitDialog,
    "font_toolkit": FontToolkitDialog,
    "one_click_maintenance": OneClickMaintenanceDialog,
    "dashboard": DashboardDialog,
    "snapshot_before_update": SnapshotDialog,
    "update_check": UpdateCheckDialog,
    "btrfs_health": BtrfsHealthDialog,
    "report_export": ReportExportDialog,
}

def get_custom_dialog(slug: str) -> Callable[..., QDialog] | None:
    return _REGISTRY.get(slug)
