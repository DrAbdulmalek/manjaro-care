#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/custom_dialogs.py — سجل مركزي للنوافذ المخصصة."""
from __future__ import annotations

from PyQt5.QtWidgets import QDialog

from gui.startup_dialog import StartupManagerDialog
from gui.boot_sanity_dialog import BootSanityDialog
from gui.repo_dialog import RepoManagerDialog
from gui.firewall_dialog import FirewallManagerDialog
from gui.boot_dialog import BootManagerDialog
from gui.uninstaller_dialog import UninstallerDialog
from gui.game_mode_dialog import GameModeDialog

_REGISTRY = {
    "startup_manager": StartupManagerDialog,
    "boot_sanity": BootSanityDialog,
    "repo_manager": RepoManagerDialog,
    "firewall_manager": FirewallManagerDialog,
    "boot_manager": BootManagerDialog,
    "app_uninstaller": UninstallerDialog,
    "game_mode": GameModeDialog,
}


def get_custom_dialog(slug: str):
    return _REGISTRY.get(slug)
