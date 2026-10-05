#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/gamescope_hdr.py
=========================
إطلاق ألعاب عبر Gamescope مع HDR — منقول ومنظّم من gamescope-hdr.sh الشخصي.

السكربت الأصلي:
    gamescope -W 1920 -H 1080 -r 144 --hdr-enabled --hdr-itm-enable \
        -- env ENABLE_GAMESCOPE_WSI=1 DXVK_HDR=1 DISPLAY= :1 "$@"

المنطق هنا نفسه لكن:
  - أوامر argv صريحة (لا shell interpolation — عناوين ألعاب بمسافات آمنة).
  - كل المعاملات قابلة للضبط من النافذة (الدقة، التردد، HDR، ITM).
  - بنّاء الأمر نقّي وقابل للاختبار بلا تنفيذ.

لا تحتاج root — gamescope يعمل بصلاحيات المستخدم (يطلب setcap مرة واحدة
إن لزم؛ هذه الوحدة تكتشف غيابه وتُرشد للمستخدم دون تلمس النظام).
"""

from __future__ import annotations

import shutil

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

log = get_logger("gamescope_hdr")


def gamescope_available() -> bool:
    """هل gamescope مثبت؟ (قراءة فقط)"""
    return shutil.which("gamescope") is not None


def build_gamescope_cmd(
    game_cmd: list[str],
    width: int = 1920,
    height: int = 1080,
    rate: int = 144,
    hdr: bool = True,
    itm: bool = True,
    display: str = ":1",
    enable_wsi: bool = True,
    dxvk_hdr: bool = True,
) -> list[str]:
    """
    بناء أمر الإطلاق الكامل بنفس دلالات السكربت الأصلي:
    gamescope <خيارات> -- env <متغيرات البيئة> <أمر اللعبة ووسائطها>

    - hdr: --hdr-enabled (يتطلب شاشة HDR + gamescope يدعمها)
    - itm: --hdr-itm-enable (Inverse Tone Mapping لرفع سطوع SDR→HDR)
    - display: شاشة الخرج المخصصة داخل جلسة gamescope (الافتراضي :1 كما في السكربت)
    """
    if not game_cmd:
        raise ValueError("أمر اللعبة فارغ — اكتب أمر الإطلاق أو اختر الملف التنفيذي.")
    cmd = ["gamescope", "-W", str(width), "-H", str(height), "-r", str(rate)]
    if hdr:
        cmd.append("--hdr-enabled")
    if itm:
        cmd.append("--hdr-itm-enable")
    cmd.append("--")
    cmd.append("env")
    if enable_wsi:
        cmd.append("ENABLE_GAMESCOPE_WSI=1")
    if dxvk_hdr:
        cmd.append("DXVK_HDR=1")
    cmd.append(f"DISPLAY={display}")
    cmd.extend(game_cmd)
    return cmd


class GamescopeHdrModule(MaintenanceModule):
    name = "ألعاب HDR عبر Gamescope 🖥️"
    slug = "gamescope_hdr"
    description = (
        "إطلاق الألعاب داخل gamescope بدقة 1080p@144 مع HDR وITM — "
        "من النافذة المخصصة لوضع الألعاب"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE  # إطلاق عملية للمستخدم فقط
    icon = "applications-games"
    # لا نافذة مستقلة — مدمج داخل وضع الألعاب (game_mode) كقسم إضافي

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        if gamescope_available():
            findings.append(ScanFinding(
                title="gamescope متوفر — إطلاق HDR جاهز",
                detail="من نافذة وضع الألعاب: اكتب أمر اللعبة واضغط إطلاق HDR.",
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="gamescope غير مثبت",
                detail="لفعاليتها: pamac install gamescope (وتأكد من شاشة HDR "
                       "وصلاحيات setcap إن طلبها gamescope عند أول تشغيل).",
                severity=Severity.WARNING,
            ))

        findings.append(ScanFinding(
            title="الملف الافتراضي: 1920×1080 @ 144Hz — HDR + ITM مفعّلان",
            detail="نفس إعدادات gamescope-hdr.sh الشخصية؛ كلها قابلة للضبط من النافذة.",
            severity=Severity.INFO, actionable=False,
        ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        sample = build_gamescope_cmd(["steam", "-applaunch", "0"])
        return [
            PreviewStep(
                description="إطلاق لعبة داخل gamescope مع تفعيل HDR",
                command=" ".join(sample),
            ),
            PreviewStep(
                description="لا يحتاج صلاحيات جذر — العملية تُطلق باسم المستخدم",
            ),
        ]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="الإطلاق يتم من نافذة وضع الألعاب (قسم Gamescope HDR).",
        )
