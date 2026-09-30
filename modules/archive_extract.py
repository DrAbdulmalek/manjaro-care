#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/archive_extract.py
===========================
الاستخراج الآمن للأرشيفات — منقول ومنظّم من سكربت safe_extract.sh الشخصي.

السلوك الموروث من السكربت الأصلي:
  1) كل أرشيف يُستخرج إلى مجلد بنفس اسمه (بلا امتداد) في نفس المكان.
  2) إذا كان المجلد الهدف موجوداً مسبقاً → تخطٍّ آمن بلا أي لمس.
  3) نجاح الاستخراج → حذف الأرشيف الأصلي (توفير مساحة).
  4) فشل الاستخراج → تنظيف المجلد الهدف الجزئي فوراً والإبقاء على الأرشيف.
  5) أنواع مدعومة: zip عبر unzip، rar عبر unrar، والبقية عبر 7z.

التحسينات على السكربت الأصلي:
  - أوامر argv صريحة (لا shell interpolation) — أسماء ملفات بمسافات آمنة.
  - احترام وضع dry-run العالمي (core/runtime.py): لا تنفيذ ولا حذف.
  - نتيجة منظمة لكل أرشيف تُعرض في النافذة المخصصة.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
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
from core.runtime import is_dry_run

log = get_logger("archive_extract")

# امتدادات شائعة نبحث عنها في مجلد التنزيلات أثناء الفحص (قراءة فقط)
COMMON_ARCHIVE_EXTS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst",
    ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst",
}


@dataclass
class ExtractionPlan:
    """خطة استخراج واحدة — تُبنى قبل التنفيذ وتُعرض للمستخدم."""
    archive: Path
    target_dir: Path
    tool: str          # unzip / unrar / 7z
    cmd: list[str]
    skip_existing: bool  # المجلد الهدف موجود مسبقاً → سيُتخطى


@dataclass
class ExtractionOutcome:
    """نتيجة تنفيذ استخراج واحد (أو معاينة جافة له)."""
    archive: Path
    success: bool
    skipped: bool = False            # تخطٍّ لأن الهدف موجود
    dry_run: bool = False
    deleted_archive: bool = False    # حُذف الأرشيف بعد نجاح؟
    cleaned_partial_dir: bool = False # نُظّف مجلد جزئي بعد فشل؟
    message: str = ""
    log_output: str = ""


def archive_kind(archive: Path) -> str:
    """نوع الأداة المناسبة: zip / rar / other (7z)."""
    name = archive.name.lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith(".rar"):
        return "rar"
    return "other"


def build_extract_cmd(archive: Path, target_dir: Path) -> tuple[str, list[str]]:
    """يبني (اسم الأداة، أمر argv صريح) حسب نوع الأرشيف."""
    kind = archive_kind(archive)
    if kind == "zip":
        return "unzip", ["unzip", "-o", str(archive), "-d", str(target_dir)]
    if kind == "rar":
        return "unrar", ["unrar", "x", "-o+", str(archive), str(target_dir) + "/"]
    return "7z", ["7z", "x", str(archive), "-o" + str(target_dir)]


def plan_extraction(archive: Path) -> ExtractionPlan:
    """يبني خطة استخراج كاملة لأرشيف واحد (بلا أي تنفيذ)."""
    archive = Path(archive)
    target_dir = archive.parent / archive.stem
    tool, cmd = build_extract_cmd(archive, target_dir)
    return ExtractionPlan(
        archive=archive,
        target_dir=target_dir,
        tool=tool,
        cmd=cmd,
        skip_existing=target_dir.is_dir(),
    )


def _cleanup_partial_dir(target_dir: Path) -> bool:
    """تنظيف مجلد استخراج فاشل: rmdir إن كان فارغاً وإلا حذف كامل."""
    if not target_dir.is_dir():
        return False
    try:
        if not any(target_dir.iterdir()):
            target_dir.rmdir()
        else:
            shutil.rmtree(target_dir)
        return True
    except OSError as exc:
        log.error("فشل تنظيف المجلد الجزئي %s: %s", target_dir, exc)
        return False


def run_extraction(
    plan: ExtractionPlan,
    delete_on_success: bool = True,
    timeout: int = 1800,
) -> ExtractionOutcome:
    """
    تنفيذ خطة استخراج واحدة وفق سلوك safe_extract.sh:
    تخطي الموجود، حذف الأرشيف عند النجاح، تنظيف الجزئي عند الفشل.
    في وضع dry-run: تُعاد نتيجة توثيقية بلا أي تنفيذ أو حذف.
    """
    if plan.skip_existing:
        return ExtractionOutcome(
            archive=plan.archive, success=True, skipped=True,
            message=f"تخطٍّ: المجلد '{plan.target_dir.name}' موجود مسبقاً.",
        )

    if is_dry_run():
        return ExtractionOutcome(
            archive=plan.archive, success=True, dry_run=True,
            message="[DRY-RUN] لم يُنفَّذ: " + " ".join(plan.cmd),
        )

    try:
        proc = subprocess.run(
            plan.cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return ExtractionOutcome(
            archive=plan.archive, success=False,
            message=f"الأداة '{plan.tool}' غير مثبتة.",
        )
    except subprocess.TimeoutExpired:
        _cleanup_partial_dir(plan.target_dir)
        return ExtractionOutcome(
            archive=plan.archive, success=False, cleaned_partial_dir=True,
            message=f"انتهت مهلة استخراج '{plan.archive.name}' — نُظّف الجزئي.",
        )

    if proc.returncode == 0:
        deleted = False
        if delete_on_success:
            try:
                plan.archive.unlink()
                deleted = True
            except OSError as exc:
                log.error("تعذر حذف الأرشيف %s: %s", plan.archive, exc)
        return ExtractionOutcome(
            archive=plan.archive, success=True, deleted_archive=deleted,
            message=f"تم استخراج '{plan.archive.name}' بنجاح"
                    + (" وحُذف الأرشيف الأصلي." if deleted else "."),
            log_output=(proc.stdout + proc.stderr)[-2000:],
        )

    # فشل: تنظيف الجزئي والإبقاء على الأرشيف (سلوك السكربت الأصلي)
    cleaned = _cleanup_partial_dir(plan.target_dir)
    return ExtractionOutcome(
        archive=plan.archive, success=False, cleaned_partial_dir=cleaned,
        message=f"فشل استخراج '{plan.archive.name}' (رمز {proc.returncode})"
                + " — نُظّف المجلد الجزئي وحُفِظ الأرشيف.",
        log_output=(proc.stdout + proc.stderr)[-2000:],
    )


class ArchiveExtractModule(MaintenanceModule):
    name = "الاستخراج الآمن للأرشيفات 📦"
    slug = "archive_extract"
    description = (
        "استخراج zip/rar/7z إلى مجلد بنفس الاسم، حذف الأرشيف عند النجاح، "
        "وتنظيف تلقائي عند الفشل — عبر نافذة مخصصة"
    )
    needs_root = False
    risk_level = RiskLevel.MODERATE  # يحذف الأرشيف الأصلي بعد نجاح الاستخراج
    icon = "application-zip"
    has_custom_ui = True

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        tools = {"unzip": shutil.which("unzip"), "unrar": shutil.which("unrar"),
                 "7z": shutil.which("7z") or shutil.which("7za")}
        missing = [t for t, path in tools.items() if path is None]
        if missing:
            findings.append(ScanFinding(
                title=f"أدوات استخراج غير مثبتة: {', '.join(missing)}",
                detail="ثبّتها لتغطية كامل الأنواع (pamac install unzip unrar p7zip).",
                severity=Severity.WARNING,
            ))
        else:
            findings.append(ScanFinding(
                title="أدوات الاستخراج متوفرة (unzip + unrar + 7z)",
                detail="كل أنواع الأرشيفات الشائعة مدعومة.",
                severity=Severity.OK, actionable=False,
            ))

        downloads = Path.home() / "Downloads"
        if downloads.is_dir():
            archives = [p for p in downloads.iterdir()
                        if p.is_file() and p.suffix.lower() in COMMON_ARCHIVE_EXTS][:50]
            if archives:
                findings.append(ScanFinding(
                    title=f"{len(archives)} أرشيفاً في مجلد التنزيلات",
                    detail="افتح النافذة المخصصة لاستخراجها بأمان (وحذف الأرشيفات بعد النجاح).",
                    severity=Severity.INFO, raw_value=len(archives),
                ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(
                description="اختيار أرشيفات من النافذة المخصصة ثم استخراج كلٍّ إلى مجلد بنفس اسمه",
                command="unzip -o <archive>.zip -d <archive>/   # مثال zip",
            ),
            PreviewStep(
                description="عند النجاح يُحذف الأرشيف الأصلي، وعند الفشل يُنظّف المجلد الجزئي ويبقى الأرشيف",
            ),
        ]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="الاستخراج يتم عبر النافذة المخصصة (اختيار الأرشيفات قرار فردي لكل ملف).",
        )
