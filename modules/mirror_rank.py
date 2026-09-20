#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/mirror_rank.py
========================
إعادة ترتيب مرايا pacman حسب السرعة الفعلية، بدل البقاء على مرايا
بطيئة أو معطّلة تُبطئ كل عملية pacman -Syu.

اكتشاف التوزيعة وقت التشغيل (إصلاح تناقض سابق: الوصف كان يقول
"مانجارو/آرتش" بينما الأداة pacman-mirrors خاصة بمانجارو فقط):
  - Manjaro → pacman-mirrors --fasttrack 5
  - Arch    → reflector --latest 20 --sort rate --save /etc/pacman.d/mirrorlist
  - غيره    → حالة "غير قابل للتطبيق" (ليست خطأ) برسالة واضحة

الفحص: يتحقق من عمر ملف /etc/pacman.d/mirrorlist — إن كان قديماً
(أكثر من 30 يوماً) يُقترح إعادة الترتيب، لأن سرعة المرايا تتغيّر
بمرور الوقت وهذا لا يُكتشف إلا بإعادة القياس الفعلي (لا توجد طريقة
"فحص قراءة فقط" لسرعة المرايا دون اختبارها فعلياً، لذلك المعيار هنا
هو عمر آخر تحديث بدل فحص السرعة الحالية).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from core.logger import get_logger
from core.module_base import (
    ApplyResult,
    MaintenanceModule,
    PreviewStep,
    RiskLevel,
    ScanFinding,
    ScanResult,
    Severity,
)
from core.privilege import run_privileged

log = get_logger("mirror_rank")

_MIRRORLIST_PATH = Path("/etc/pacman.d/mirrorlist")
_STALE_DAYS = 30
_OS_RELEASE = Path("/etc/os-release")


def _detect_distro_id() -> str:
    """يقرأ ID من /etc/os-release (مانجارو=manjaro، آرتش=arch، غير ذلك
    يُرجع المعرّف كما هو أو سلسلة فارغة). قراءة ملف فقط، بلا أوامر."""
    try:
        for line in _OS_RELEASE.read_text(encoding="utf-8").splitlines():
            if line.startswith("ID="):
                return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return ""


def _mirror_tool() -> str | None:
    """يُرجع أداة ترتيب المرايا المناسبة للتوزيعة الحالية، أو None."""
    distro = _detect_distro_id()
    if distro == "manjaro" and shutil.which("pacman-mirrors"):
        return "pacman-mirrors"
    if distro == "arch" and shutil.which("reflector"):
        return "reflector"
    return None


def _not_applicable_detail() -> str:
    distro = _detect_distro_id() or "غير معروفة"
    return (
        f"التوزيعة المكتشفة: {distro}. هذه الوحدة تعمل على مانجارو "
        f"(pacman-mirrors) أو آرتش (reflector) فقط."
    )


def _mirrorlist_age_days() -> float | None:
    if not _MIRRORLIST_PATH.exists():
        return None
    age_seconds = time.time() - os.path.getmtime(_MIRRORLIST_PATH)
    return age_seconds / 86400


class MirrorRankModule(MaintenanceModule):
    name = "ترتيب مرايا التحديث"
    slug = "mirror_rank"
    description = "يعيد اختبار وترتيب مرايا pacman حسب السرعة الفعلية (مانجارو: pacman-mirrors / آرتش: reflector)"
    needs_root = True
    risk_level = RiskLevel.SAFE  # لا يحذف شيئاً، فقط يعيد كتابة ملف المرايا
    icon = "network-server"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        if _mirror_tool() is None:
            findings.append(ScanFinding(
                title="غير قابل للتطبيق على هذه التوزيعة",
                detail=_not_applicable_detail(),
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        age = _mirrorlist_age_days()
        if age is None:
            findings.append(ScanFinding(
                title="ملف المرايا غير موجود",
                detail=f"{_MIRRORLIST_PATH} غير موجود — قد تحتاج تثبيت أداة المرايا.",
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
        tool = _mirror_tool()
        if tool == "pacman-mirrors":
            return [PreviewStep(
                description="اختبار سرعة المرايا (أسرع 5) وإعادة كتابة قائمة المرايا",
                command="pacman-mirrors --fasttrack 5",
            )]
        if tool == "reflector":
            return [PreviewStep(
                description="اختبار أحدث 20 مرآة وترتيبها حسب السرعة وكتابة mirrorlist",
                command="reflector --latest 20 --sort rate --save /etc/pacman.d/mirrorlist",
            )]
        return [PreviewStep(
            description="لا يوجد إجراء — " + _not_applicable_detail(),
        )]

    def apply(self) -> ApplyResult:
        tool = _mirror_tool()
        if tool == "pacman-mirrors":
            result = run_privileged(["pacman-mirrors", "--fasttrack", "5"])
            msg_ok = "تم اختبار المرايا وإعادة ترتيبها حسب السرعة"
            msg_fail = f"فشل إعادة الترتيب (كود {result.returncode}) — تأكد من تثبيت pacman-mirrors"
        elif tool == "reflector":
            result = run_privileged(
                ["reflector", "--latest", "20", "--sort", "rate",
                 "--save", str(_MIRRORLIST_PATH)]
            )
            msg_ok = "تم اختبار المرايا عبر reflector وإعادة ترتيبها حسب السرعة"
            msg_fail = f"فشل إعادة الترتيب (كود {result.returncode}) — تأكد من تثبيت reflector"
        else:
            return ApplyResult(success=False, message="غير قابل للتطبيق — " + _not_applicable_detail())

        if result.ok:
            return ApplyResult(success=True, message=msg_ok,
                               log_output=result.stdout + result.stderr)
        return ApplyResult(success=False, message=msg_fail,
                           log_output=result.stdout + result.stderr)
