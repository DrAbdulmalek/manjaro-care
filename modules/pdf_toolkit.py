#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/pdf_toolkit.py
=======================
حقيبة أدوات PDF — مستوحاة من طقم أدوات المستخدم (img2pdf، ocrmypdf،
pdfminer: pdf2txt.py/dumppdf.py، pypdfium2).

ثلاث عمليات عملية تغطي 90% من الاستخدام اليومي:
  1) صور → PDF  (img2pdf — دمج صور ماسح ضوئي في ملف واحد بلا إعادة ترميز)
  2) OCR لملف PDF ممسوح ضوئياً  (ocrmypdf — إضافة طبقة نص قابلة للبحث)
  3) استخراج نص من PDF  (pdftotext إن وجد وإلا pdf2txt.py من pdfminer)

الوحدة طبقة منطق نظيفة (بلا GUI) — النافذة المخصصة في gui/pdf_toolkit_dialog.py
تستدعي البنّائات هنا وتنفذها عبر QThread. كل أوامر argv صريحة، وتحترم dry-run
عبر طبقة التنفيذ نفسها (نمط archive_extract).
"""

from __future__ import annotations

import shutil
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

log = get_logger("pdf_toolkit")

# الأدوات التي نفحص توفرها + وصف عربي لما تفعله
KNOWN_TOOLS: dict[str, str] = {
    "img2pdf": "دمج الصور في PDF (بلا فقدان جودة)",
    "ocrmypdf": "إضافة طبقة نص OCR لملف ممسوح ضوئياً",
    "pdftotext": "استخراج النص (من poppler)",
    "pdf2txt.py": "استخراج النص (بديل pdfminer)",
    "pypdfium2": "عرض/معالجة PDF (محرّك pdfium)",
}


# ---------------- بنّائات الأوامر (نقية وقابلة للاختبار) ----------------

def build_img2pdf_cmd(images: list[Path], output: Path) -> list[str]:
    """دمج قائمة صور في ملف PDF واحد عبر img2pdf."""
    if not images:
        raise ValueError("قائمة الصور فارغة — اختر صورة واحدة على الأقل.")
    return ["img2pdf", *[str(p) for p in images], "-o", str(output)]


def build_ocrmypdf_cmd(
    src: Path, output: Path, lang: str = "ara+eng",
    skip_text: bool = True, jobs: int = 2,
) -> list[str]:
    """OCR ملف PDF ممسوح ضوئياً — الناتج نسخة قابلة للبحث والنسخ."""
    if lang not in {"ara", "eng", "ara+eng"}:
        raise ValueError(f"لغة OCR غير مدعومة: {lang}")
    cmd = ["ocrmypdf", "-l", lang]
    if skip_text:
        # لا يعيد OCR الصفحات التي تحمل نصاً أصلاً (أسرع وأقل خطأ)
        cmd += ["--skip-text"]
    cmd += ["-j", str(jobs), str(src), str(output)]
    return cmd


def text_extract_tool() -> str | None:
    """الأداة المفضلة لاستخراج النص: pdftotext ثم pdf2txt.py."""
    if shutil.which("pdftotext"):
        return "pdftotext"
    if shutil.which("pdf2txt.py"):
        return "pdf2txt.py"
    return None


def build_text_extract_cmd(src: Path, output: Path, tool: str | None = None) -> list[str]:
    """استخراج نص من PDF إلى ملف .txt (pdftotext أولاً ثم pdf2txt.py)."""
    chosen = tool or text_extract_tool()
    if chosen == "pdftotext":
        return ["pdftotext", "-layout", str(src), str(output)]
    if chosen == "pdf2txt.py":
        return ["pdf2txt.py", "-o", str(output), str(src)]
    raise ValueError("لا توجد أداة استخراج نص — ثبّت poppler (pdftotext) أو pdfminer.")


def tools_availability() -> dict[str, bool]:
    """خريطة توفر الأدوات المعروفة (قراءة فقط، بلا تنفيذ)."""
    return {tool: shutil.which(tool) is not None for tool in KNOWN_TOOLS}


# ---------------- الوحدة (بطاقة في اللوحة) ----------------

class PdfToolkitModule(MaintenanceModule):
    name = "حقيبة أدوات PDF 📄"
    slug = "pdf_toolkit"
    description = (
        "صور→PDF، OCR لملفات ممسوحة ضوئياً (عربي+إنجليزي)، واستخراج نص — "
        "عبر النافذة المخصصة"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE  # ينشئ ملفات جديدة فقط، لا يعدل الأصل
    icon = "application-pdf"
    has_custom_ui = True

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        avail = tools_availability()

        if avail.get("img2pdf"):
            findings.append(ScanFinding(
                title="img2pdf متوفر — دمج الصور في PDF جاهز",
                detail="اختر الصور من النافذة المخصصة وسيُبنى ملف واحد بلا إعادة ترميز.",
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="img2pdf غير مثبت",
                detail="لفعاليتها: pamac install img2pdf (دمج صور الماسح في PDF واحد).",
                severity=Severity.WARNING,
            ))

        if avail.get("ocrmypdf"):
            findings.append(ScanFinding(
                title="ocrmypdf متوفر — OCR عربي/إنجليزي جاهز",
                detail="يتطلب حزم tesseract-ocr-ara و tesseract-ocr-eng لغتي التعرّف.",
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="ocrmypdf غير مثبت",
                detail="لفعاليتها: pamac install ocrmypdf tesseract-data-ara tesseract-data-eng.",
                severity=Severity.WARNING,
            ))

        if text_extract_tool() is None:
            findings.append(ScanFinding(
                title="لا توجد أداة استخراج نص",
                detail="ثبّت poppler (pdftotext) أو pdfminer (pdf2txt.py).",
                severity=Severity.WARNING,
            ))
        else:
            findings.append(ScanFinding(
                title=f"استخراج النص متوفر عبر {text_extract_tool()}",
                detail="جاهز من النافذة المخصصة.",
                severity=Severity.OK, actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(
                description="صور → PDF عبر img2pdf (بلا إعادة ترميز)",
                command="img2pdf <img1> <img2> ... -o <output>.pdf",
            ),
            PreviewStep(
                description="OCR عربي+إنجليزي مع تخطي الصفحات ذات النص الأصلي",
                command="ocrmypdf -l ara+eng --skip-text -j 2 <src>.pdf <out>.pdf",
            ),
            PreviewStep(
                description="استخراج نص مع الحفاظ على التنسيق",
                command="pdftotext -layout <src>.pdf <out>.txt",
            ),
        ]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="العمليات تُنفَّذ من النافذة المخصصة (اختيار الملفات قرار فردي).",
        )
