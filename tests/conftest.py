#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/conftest.py — يضيف جذر المشروع إلى sys.path ويعيد ضبط الحالة
العامة بين الاختبارات (خاصة علم dry-run في core/runtime.py)."""
from __future__ import annotations

import sys
from pathlib import Path

# يسمح باستيراد core.* وmodules.* سواء استُدعي pytest من جذر المشروع
# أو من داخل tests/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from core.runtime import set_dry_run


@pytest.fixture(autouse=True)
def _reset_global_state():
    """كل اختبار يبدأ وينتهي بحالة نظيفة — لا تسرب لعلم dry-run
    أو غيره بين الاختبارات."""
    set_dry_run(False)
    yield
    set_dry_run(False)
