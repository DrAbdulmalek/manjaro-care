#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/custom_dialogs.py — سجل مركزي للنوافذ المخصصة.

6 نوافذ مخصصة:
  1. StartupManagerDialog — برامج بدء التشغيل
  2. BootSanityDialog — فحص الإقلاع
  3. RepoManagerDialog — مستودعات pacman
  4. FirewallManagerDialog — الجدار الناري
  5. BootManagerDialog — إدارة GRUB
  6. UninstallerDialog — إلغاء تثبيت البرامج (IObit-style)
"""
from __future__ import annotations
from typing import Callable

from PyQt5.QtWidgets import QDialog

from gui.startup_dialog import StartupManagerDialog
from gui.boot_sanity_dialog import BootSanityDialog
from gui.repo_dialog import RepoManagerDialog
from gui.firewall_dialog import FirewallManagerDialog
from gui.boot_dialog import BootManagerDialog
from gui.uninstaller_dialog import UninstallerDialog

_REGISTRY = {
    "startup_manager": StartupManagerDialog,
    "boot_sanity": BootSanityDialog,
    "repo_manager": RepoManagerDialog,
    "firewall_manager": FirewallManagerDialog,
    "boot_manager": BootManagerDialog,
    "app_uninstaller": UninstallerDialog,
}


def get_custom_dialog(slug: str) -> Callable[..., QDialog] | None:
    return _REGISTRY.get(slug)
