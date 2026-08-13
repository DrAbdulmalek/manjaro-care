#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/mirror_rank.py
========================
إعادة ترتيب مرايا مانجارو (pacman-mirrors) حسب السرعة الفعلية، بدل
البقاء على مرايا بطيئة أو معطّلة تُبطئ كل عملية pacman -Syu.

الفحص: يتحقق من عمر ملف /etc/pacman.d/mirrorlist — إن كان قديماً
(أكثر من 30 يوماً) يُقترح إعادة الترتيب، لأن سرعة المرايا تتغيّر
بمرور الوقت وهذا لا يُكتشف إلا بإعادة القياس الفعلي (لا توجد طريقة
"فحص قراءة فقط" لسرعة المرايا دون اختبارها فعلياً، لذلك المعيار هنا
هو عمر آخر تحديث بدل فحص السرعة الحالية).
"""

from __future__ import annotations
import os
import time
from pathlib import Path

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged
from core.logger import get_logger

log = get_logger("mirror_rank")

_MIRRORLIST_PATH = Path("/etc/pacman.d/mirrorlist")
_STALE_DAYS = 30


def _mirrorlist_age_days() -> float | None:
    if not _MIRRORLIST_PATH.exists():
        return None
    age_seconds = time.time() - os.path.getmtime(_MIRRORLIST_PATH)
    return age_seconds / 86400


class MirrorRankModule(MaintenanceModule):
    name = "ترتيب مرايا التحديث"
    slug = "mirror_rank"
    description = "يعيد اختبار وترتيب مرايا مانجارو حسب السرعة الفعلية لتسريع pacman -Syu"
    needs_root = True
    risk_level = RiskLevel.SAFE  # لا يحذف شيئاً، فقط يعيد كتابة ملف المرايا
    icon = "network-server"

    def scan(self) -> ScanResult:
        age = _mirrorlist_age_days()
        findings: list[ScanFinding] = []

        if age is None:
            findings.append(ScanFinding(
                title="ملف المرايا غير موجود",
                detail=f"{_MIRRORLIST_PATH} غير موجود — قد تحتاج تثبيت pacman-mirrors.",
                severity=Severity.WARNING,
                actionable=False,
            ))
        elif age > _STALE_DAYS:
            findings.append(ScanFinding(
                title=f"لم تُحدَّث المرايا منذ {age:.0f} يوماً",
                detail="يُنصح بإعادة الترتيب — سرعة المرايا تتغيّر بمرور الوقت.",
                severity=Severity.WARNING,
                raw_value=age,
            ))
        else:
            findings.append(ScanFinding(
                title=f"المرايا محدَّثة منذ {age:.0f} يوماً",
                detail="لا حاجة ملحّة لإعادة الترتيب الآن، لكن يمكنك تشغيله يدوياً في أي وقت.",
                severity=Severity.OK,
                actionable=True,  # نسمح بالتشغيل اليدوي رغم عدم وجود مشكلة
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="اختبار سرعة المرايا وإعادة كتابة قائمة المرايا مرتبة تصاعدياً حسب زمن الاستجابة",
            command="pacman-mirrors --fasttrack 5",
        )]

    def apply(self) -> ApplyResult:
        result = run_privileged(["pacman-mirrors", "--fasttrack", "5"])
        if result.ok:
            return ApplyResult(
                success=True,
                message="تم اختبار المرايا وإعادة ترتيبها حسب السرعة",
                log_output=result.stdout + result.stderr,
            )
        return ApplyResult(
            success=False,
            message=f"فشل إعادة الترتيب (كود {result.returncode}) — تأكد من تثبيت pacman-mirrors",
            log_output=result.stdout + result.stderr,
        )
