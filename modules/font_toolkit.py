#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/font_toolkit.py
========================
حقيبة أدوات الخطوط — منقولة من طقم المستخدم (fonttools: ttx،
pyftsubset، pyftmerge).

ثلاث عمليات:
  1) ttx dump/compile — تفكيك خط TTF/OTF إلى XML قابل للقراءة والتعديل،
     أو إعادة تجميع XML إلى خط (للمسح والتدقيق اليدوي).
  2) pyftsubset — تقليص خط إلى مجموعة رموز محددة (نطاقات Unicode أو
     ملف نصي) مع إخراج TTF/WOFF/WOFF2 — يصغّر الخطوط للأجهزة والويب.
  3) pyftmerge — دمج خطين أو أكثر في ملف واحد.

الوحدة طبقة منطق بلا GUI — النافذة في gui/font_toolkit_dialog.py.
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

log = get_logger("font_toolkit")

FONT_TOOLS: dict[str, str] = {
    "ttx": "تفكيك/تجميع الخط إلى XML",
    "pyftsubset": "تقليص خط إلى مجموعة رموز",
    "pyftmerge": "دمج خطوط في ملف واحد",
}

# نطاقات يونيكود جاهزة للاستخدام السريع في النافذة
QUICK_RANGES: dict[str, str] = {
    "عربي أساسي": "U+0600-06FF",
    "عربي + لاتيني": "U+0000-00FF,U+0600-06FF",
    "عربي + لاتيني + أرقام عربية-هندية": "U+0000-00FF,U+0600-06FF,U+0660-0669",
}


# ---------------- بنّائات الأوامر (نقية وقابلة للاختبار) ----------------

def build_ttx_dump_cmd(font: str, output_xml: str | None = None) -> list[str]:
    """تفكيك خط إلى XML (ttx). إن لم يُحدد خرج يُكتب بجانب المصدر."""
    cmd = ["ttx"]
    if output_xml:
        cmd += ["-o", output_xml]
    cmd.append(font)
    return cmd


def build_ttx_compile_cmd(xml_path: str) -> list[str]:
    """إعادة تجميع XML معدّل إلى خط ثنائي (ttx)."""
    if not xml_path.lower().endswith((".ttx", ".xml")):
        raise ValueError("إعادة التجميع تتطلب ملف .ttx/.xml — وليس خطاً ثنائياً.")
    return ["ttx", xml_path]


def build_subset_cmd(
    font: str, output: str,
    unicodes: str | None = None, text_file: str | None = None,
    flavor: str | None = None,
) -> list[str]:
    """تقليص خط إلى مجموعة رموز (pyftsubset). مطلوب مصدر رموز واحد على الأقل."""
    if not unicodes and not text_file:
        raise ValueError("حدد نطاق Unicode أو ملف نصي — لا يمكن التقليص بلا مصدر رموز.")
    if flavor not in (None, "woff", "woff2"):
        raise ValueError(f"صيغة غير مدعومة: {flavor} (المسموح: woff/woff2).")
    cmd = ["pyftsubset", font, f"--output-file={output}"]
    if unicodes:
        cmd.append(f"--unicodes={unicodes}")
    if text_file:
        cmd.append(f"--text-file={text_file}")
    if flavor:
        cmd.append(f"--flavor={flavor}")
    return cmd


def build_merge_cmd(fonts: list[str], output: str) -> list[str]:
    """دمج خطين أو أكثر (pyftmerge)."""
    if len(fonts) < 2:
        raise ValueError("الدمج يتطلب خطين على الأقل.")
    return ["pyftmerge", "-o", output, *fonts]


def font_tools_availability() -> dict[str, bool]:
    """توفر أدوات fonttools الثلاث (قراءة فقط)."""
    return {tool: shutil.which(tool) is not None for tool in FONT_TOOLS}


# ---------------- الوحدة (بطاقة في اللوحة) ----------------

class FontToolkitModule(MaintenanceModule):
    name = "حقيبة أدوات الخطوط 🔤"
    slug = "font_toolkit"
    description = (
        "تفكيك/تجميع الخطوط (ttx)، تقليصها لنطاقات عربية/لاتينية (subset)، "
        "ودمجها (merge) — عبر النافذة المخصصة"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE  # ينتج ملفات جديدة ولا يعدل الأصل
    icon = "font-x-generic"
    has_custom_ui = True

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        avail = font_tools_availability()
        missing = [t for t, ok in avail.items() if not ok]

        if not missing:
            findings.append(ScanFinding(
                title="أدوات fonttools الثلاث متوفرة (ttx + subset + merge)",
                detail="كل عمليات الحقيبة جاهزة من النافذة المخصصة.",
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title=f"أدوات غير مثبتة: {', '.join(missing)}",
                detail="ثبّت الحزمة مرة واحدة: pip install fonttools"
                       " (تتضمن ttx و pyftsubset و pyftmerge).",
                severity=Severity.WARNING,
            ))

        findings.append(ScanFinding(
            title="نطاقات يونيكود جاهزة للتقليص",
            detail="عربي أساسي / عربي+لاتيني / عربي+لاتيني+أرقام هندية — اختيار بنقرة في النافذة.",
            severity=Severity.INFO, actionable=False,
        ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(
                description="تفكيك خط إلى XML للفحص اليدوي",
                command="ttx -o <out>.ttx <font>.ttf",
            ),
            PreviewStep(
                description="تقليص خط إلى نطاق عربي+لاتيني (مثال)",
                command="pyftsubset <font>.ttf --output-file=<out>.ttf "
                        "--unicodes=U+0000-00FF,U+0600-06FF",
            ),
            PreviewStep(
                description="دمج خطين في ملف واحد",
                command="pyftmerge -o <merged>.ttf <font1>.ttf <font2>.ttf",
            ),
        ]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="العمليات تُنفَّذ من النافذة المخصصة (اختيار الخطوط قرار فردي).",
        )
