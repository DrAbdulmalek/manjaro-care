#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/custom_dialogs.py
========================
سجل مركزي يربط slug الوحدة بنافذتها المخصصة.
"""
from __future__ import annotations
from typing import Callable

from PyQt5.QtWidgets import QDialog

from gui.startup_dialog import StartupManagerDialog
from gui.repo_dialog import RepoManagerDialog

_REGISTRY: dict[str, Callable[..., QDialog]] = {
    "startup_manager": StartupManagerDialog,
    "repo_manager": RepoManagerDialog,
}


def get_custom_dialog(slug: str) -> Callable[..., QDialog] | None:
    return _REGISTRY.get(slug)
