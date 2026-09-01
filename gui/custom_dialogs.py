#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/custom_dialogs.py
========================
سجل مركزي يربط slug الوحدة بنافذتها المخصصة، لوحدات وضعت
has_custom_ui = True في core/module_base.py.

إضافة نافذة مخصصة لوحدة جديدة مستقبلاً تتطلب فقط تسجيلها هنا —
module_card.py لا يحتاج أي تعديل.

v1.3: أضيف RepoManagerDialog لإدارة مستودعات pacman.
"""

from __future__ import annotations
from typing import Callable

from PyQt5.QtWidgets import QDialog

from gui.startup_dialog import StartupManagerDialog
from gui.boot_sanity_dialog import BootSanityDialog
from gui.repo_dialog import RepoManagerDialog

_REGISTRY: dict[str, Callable[..., QDialog]] = {
    "startup_manager": StartupManagerDialog,
    "boot_sanity": BootSanityDialog,
    "repo_manager": RepoManagerDialog,
}


def get_custom_dialog(slug: str) -> Callable[..., QDialog] | None:
    return _REGISTRY.get(slug)
