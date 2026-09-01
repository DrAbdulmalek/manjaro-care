#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/custom_dialogs.py
========================
سجل مركزي يربط slug الوحدة بنافذتها المخصصة.

4 نوافذ مخصصة:
  1. StartupManagerDialog — برامج بدء التشغيل
  2. RepoManagerDialog — مستودعات pacman
  3. FirewallManagerDialog — الجدار الناري
  4. BootManagerDialog — إدارة GRUB
"""

from __future__ import annotations
from typing import Callable

from PyQt5.QtWidgets import QDialog

from gui.startup_dialog import StartupManagerDialog
from gui.boot_sanity_dialog import BootSanityDialog
from gui.repo_dialog import RepoManagerDialog
from gui.firewall_dialog import FirewallManagerDialog
from gui.boot_dialog import BootManagerDialog

_REGISTRY: dict[str, Callable[..., QDialog]] = {
    "startup_manager": StartupManagerDialog,
    "boot_sanity": BootSanityDialog,
    "repo_manager": RepoManagerDialog,
    "firewall_manager": FirewallManagerDialog,
    "boot_manager": BootManagerDialog,
}


def get_custom_dialog(slug: str) -> Callable[..., QDialog] | None:
    return _REGISTRY.get(slug)
