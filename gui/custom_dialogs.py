#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/custom_dialogs.py — سجل مركزي للنوافذ المخصصة."""
from __future__ import annotations
from typing import Callable

from PyQt5.QtWidgets import QDialog

from gui.startup_dialog import StartupManagerDialog
from gui.repo_dialog import RepoManagerDialog
from gui.firewall_dialog import FirewallManagerDialog

_REGISTRY = {
    "startup_manager": StartupManagerDialog,
    "repo_manager": RepoManagerDialog,
    "firewall_manager": FirewallManagerDialog,
}


def get_custom_dialog(slug: str):
    return _REGISTRY.get(slug)
