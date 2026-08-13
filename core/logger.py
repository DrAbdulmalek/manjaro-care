#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/logger.py
==============
لوغ مركزي لكل التطبيق والوحدات. الملف الافتراضي:
  ~/.local/share/manjaro-care/manjaro-care.log   (وضع مستخدم عادي)
مع محاولة الكتابة أيضاً إلى /var/log/manjaro-care.log إن توفرت الصلاحية
(يُترك فارغاً بصمت إن لم تتوفر، لأن هذا الملف اختياري وليس ضرورياً للعمل).
"""

from __future__ import annotations
import logging
import os
from pathlib import Path

_LOG_DIR = Path.home() / ".local" / "share" / "manjaro-care"
_LOG_FILE = _LOG_DIR / "manjaro-care.log"

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger("manjaro_care")
    root.setLevel(logging.DEBUG if os.environ.get("MC_DEBUG") else logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True


def get_logger(component: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(f"manjaro_care.{component}")


def log_file_path() -> Path:
    return _LOG_FILE
