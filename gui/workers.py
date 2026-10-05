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
from PyQt5.QtWidgets import QMessageBox

from core.logger import get_logger

log = get_logger("workers")


class BusyCloseGuardMixin:
    """يمنع إغلاق النافذة بينما خيط خلفي ما زال يعمل (زر X أو Esc).

    لماذا؟ النوافذ المخصصة تُفتح عبر dialog.exec_() من module_card،
    فإذا أغلق المستخدم النافذة أثناء تشغيل العامل خرج exec_() وتُجمَّع
    النافذة مع أبنائها — ومن بينهم QThread حيّ — ما يسبب خطأ
    «QThread: Destroyed while thread is still running» وانسحاباً محتملاً.
    النافذة معطّلة الأزرار أثناء العمل أصلًا (setEnabled(False))، فيبقى
    زر العنوان X هو المنفذ الوحيد — وهذا الحارس يسده.

    النوافذ التي تحمل أكثر من عامل تُصرّح بـ:
        _GUARD_ATTRS = ("_worker", "_gs_worker")
    """

    _GUARD_ATTRS: tuple[str, ...] = ("_worker",)
    _BUSY_MSG = (
        "هناك عملية ما تزال تعمل في الخلفية.\n"
        "انتظر انتهاءها قبل إغلاق النافذة."
    )

    def _any_worker_busy(self) -> bool:
        for attr in self._GUARD_ATTRS:
            worker = getattr(self, attr, None)
            if worker is not None and worker.isRunning():
                return True
        return False

    def reject(self):  # noqa: D102 — Esc وزر X يمرّان من هنا
        if self._any_worker_busy():
            log.debug("منع إغلاق %s: خيط خلفي يعمل", type(self).__name__)
            QMessageBox.information(self, "العملية جارية", self._BUSY_MSG)
            return
        super().reject()

    def closeEvent(self, event):  # noqa: N802 — واجهة Qt
        if self._any_worker_busy():
            event.ignore()
            log.debug("منع closeEvent لـ %s: خيط خلفي يعمل", type(self).__name__)
            QMessageBox.information(self, "العملية جارية", self._BUSY_MSG)
            return
        super().closeEvent(event)


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
