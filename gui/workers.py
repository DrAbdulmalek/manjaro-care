#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/workers.py
================
عامل خيط خلفي عام (QThread) لتنفيذ أي دالة قد تستغرق وقتاً — أهمها
scan() و apply() في كل وحدة، وrun_full_scan() في لوحة الصحة العامة.

هذا يعالج السبب الجذري لمشكلة "تجمّد الواجهة" (GUI freeze/Not
Responding): استدعاء subprocess.run() مباشرة داخل خيط Qt الرئيسي
يُجمّد كل النافذة حتى ينتهي الأمر — قد يكون هذا ثوانٍ معدودة (فحص
عادي) أو عشرات الثواني (بحث find على مجلد شخصي ضخم مليء بملفات
كبيرة)، وأثناءها لا تستجيب النافذة إطلاقاً حتى لو أراد المستخدم
إلغاء العملية.

الاستخدام:
    worker = FunctionWorker(some_module.scan)
    worker.finished.connect(on_result)
    worker.failed.connect(on_error)
    worker.start()

يجب الاحتفاظ بمرجع للـ worker (self._worker = worker) طالما هو
يعمل، وإلا قد تُجمَّع (garbage collected) قبل انتهائه.
"""

from __future__ import annotations
from typing import Any, Callable

from PyQt5.QtCore import QThread, pyqtSignal

from core.logger import get_logger

log = get_logger("workers")


class FunctionWorker(QThread):
    """يُنفّذ دالة واحدة بلا معطيات في خيط خلفي، ويبعث النتيجة أو الخطأ."""

    finished_ok = pyqtSignal(object)   # النتيجة الناجحة
    failed = pyqtSignal(str)           # نص الاستثناء عند الفشل

    def __init__(self, func: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._func = func

    def run(self) -> None:  # يُنفَّذ في الخيط الخلفي — لا تلمس عناصر Qt هنا
        try:
            result = self._func()
        except Exception as exc:  # noqa: BLE001 — نريد عرض أي خطأ للمستخدم بدل انهيار صامت
            log.exception("فشل تنفيذ عملية في الخيط الخلفي")
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)
