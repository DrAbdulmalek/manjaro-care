#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/snapper_cleanup.py
==========================
إدارة اللقطات القديمة عبر snapper: يحذف **القديمة فقط** ويحتفظ بآخر
N لقطات (N قابل للضبط من نافذة «لقطة قبل التحديث» المخصصة، ويُخزَّن
في ~/.config/manjaro-care/snapper_keep_n — الافتراضي 10).

الضمانات:
  - اللقطة رقم 0 ("current" — الحالة الحية) لا تُحذف أبداً.
  - preview() يعرض **أرقام اللقطات المحددة للحذف بالاسم** حرفياً —
    لا أوامر عامة مثل cleanup (القديمة: كانت تنفّذ snapper cleanup
    number/timeline وتترك قرار الأعمار لأداة snapper بلا معاينة
    صريحة بالمعرّفات).
  - apply() يحذف المعرّفات المعروضة واحداً واحداً عبر argv، ويفشل
    جزئياً بصدق إن فشل رقم منها.
  - dry-run العام يمنع كل الحذف (رسالة خطة صادقة).
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
from core.privilege import run_privileged
from core.runtime import is_dry_run

log = get_logger("snapper_cleanup")

CONFIG_DIR = Path.home() / ".config" / "manjaro-care"
KEEP_FILE = CONFIG_DIR / "snapper_keep_n"
DEFAULT_KEEP = 10
# لقطة 0 = "current" (الحالة الحية للنظام) — مقدسة، لا تُحذف أبداً
PROTECTED_NUMS = {"0"}


def read_keep_count() -> int:
    """قراءة N من ملف الإعداد (سطر واحد رقمي)، أو DEFAULT_KEEP."""
    try:
        value = int(KEEP_FILE.read_text().strip())
        if value >= 1:
            return value
    except (OSError, ValueError):
        pass
    return DEFAULT_KEEP


def write_keep_count(n: int) -> bool:
    """حفظ N (تستدعيه النافذة المخصصة). يُرجع نجاح الكتابة."""
    if n < 1:
        return False
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        KEEP_FILE.write_text(f"{int(n)}\n")
        return True
    except OSError:
        log.exception("فشل حفظ إعداد keep-N")
        return False


def compute_deletions(nums: list[str], keep: int) -> list[str]:
    """دالة نقيّة: من المُحتفظ به آخر `keep` لقطة (ترتيب رقمي تصاعدي)،
    يُرجع كل ما عداه — مع حماية اللقطة 0 وحماية القيم غير الرقمية."""
    numeric = sorted({n for n in nums if n.isdigit() and n not in PROTECTED_NUMS},
                     key=int)
    if keep <= 0:
        keep = 1
    return numeric[:-keep] if len(numeric) > keep else []


class SnapperCleanupModule(MaintenanceModule):
    name = "تنظيف Snapshots القديمة"
    slug = "snapper_cleanup"
    description = (
        "يحذف لقطات snapper القديمة فقط ويحتفظ بآخر N (قابل للضبط) — "
        "المعاينة تعرض المعرّفات المحددة للحذف بالتحديد"
    )
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "edit-clear-history"

    # ------------------------------------------------------------------
    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        if not shutil.which("snapper"):
            findings.append(ScanFinding(
                title="snapper غير مثبت",
                detail="هذه الوحدة خاصة بـ snapper. لمستخدمي timeshift: "
                       "استخدم أداة timeshift نفسها لإدارة اللقطات القديمة.",
                severity=Severity.INFO, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        from modules.snapshot_before_update import detect_tool, list_snapshots

        snaps, error = ([], None)
        if detect_tool() is None:
            error = "لا أداة لقطات"
        else:
            snaps, error = list_snapshots("snapper")
        if error:
            findings.append(ScanFinding(
                title="تعذّرت قراءة قائمة اللقطات",
                detail=str(error), severity=Severity.WARNING, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        keep = read_keep_count()
        deletions = compute_deletions([s["num"] for s in snaps], keep)
        if deletions:
            findings.append(ScanFinding(
                title=f"{len(deletions)} لقطة قديمة قابلة للحذف (الاحتفاظ بآخر {keep})",
                detail="المعرّفات: " + ", ".join(f"#{n}" for n in deletions),
                severity=Severity.INFO, actionable=True,
                raw_value=deletions,
            ))
        else:
            findings.append(ScanFinding(
                title=f"لا لقطات زائدة — العدد ضمن آخر {keep}",
                detail=f"عدد اللقطات الحالي: {len([s for s in snaps if s['num'] != '0'])}",
                severity=Severity.OK, actionable=False,
            ))
        return ScanResult(module_name=self.name, findings=findings)

    # ------------------------------------------------------------------
    def preview(self) -> list[PreviewStep]:
        if not shutil.which("snapper"):
            return [PreviewStep(description="لا إجراء — snapper غير مثبت.")]

        snaps, error = ([], None)
        try:
            from modules.snapshot_before_update import list_snapshots
            snaps, error = list_snapshots("snapper")
        except Exception as exc:  # نريد ألا تنهار المعاينة أبداً
            error = str(exc)
        if error:
            return [PreviewStep(description=f"لا إجراء — {error}")]

        keep = read_keep_count()
        deletions = compute_deletions([s["num"] for s in snaps], keep)
        if not deletions:
            return [PreviewStep(description=f"لا حذف — العدد ضمن آخر {keep} لقطات.")]

        steps = [PreviewStep(
            description=f"سيُحذف بالتحديد {len(deletions)} لقطة: "
                        + ", ".join(f"#{n}" for n in deletions)
                        + f" — سيُحتفظ بآخر {keep}.",
        )]
        for num in deletions:
            steps.append(PreviewStep(
                description=f"حذف اللقطة #{num}",
                command=f"snapper -c root delete {num}",
            ))
        return steps

    # ------------------------------------------------------------------
    def apply(self) -> ApplyResult:
        # طبقة الحماية 1: dry-run — لا حذف إطلاقاً، خطة صادقة
        if is_dry_run():
            plan = "\n".join(
                f"• {s.description}" + (f"\n  $ {s.command}" if s.command else "")
                for s in self.preview()
            )
            return ApplyResult(success=True,
                               message="[DRY-RUN] لم يُحذف شيء — أدناه ما كان سيُنفَّذ.",
                               log_output=plan)

        if not shutil.which("snapper"):
            return ApplyResult(success=False, message="snapper غير مثبت على هذا النظام.")

        from modules.snapshot_before_update import list_snapshots
        snaps, error = list_snapshots("snapper")
        if error:
            return ApplyResult(success=False, message=f"تعذّرت قراءة قائمة اللقطات: {error}")

        keep = read_keep_count()
        deletions = compute_deletions([s["num"] for s in snaps], keep)
        if not deletions:
            return ApplyResult(success=True, message=f"لا لقطات زائدة — العدد ضمن آخر {keep}.")

        logs = []
        failed = []
        for num in deletions:
            r = run_privileged(["snapper", "-c", "root", "delete", num])
            logs.append(f"snapper -c root delete {num}\n{r.stdout}{r.stderr}")
            if not r.ok:
                failed.append(num)
                log.warning("فشل حذف اللقطة #%s (كود %s)", num, r.returncode)

        if failed:
            return ApplyResult(
                success=False,
                message=f"فشل حذف: {', '.join('#' + n for n in failed)} — "
                        "الباقي نُفِّذ. راجع المخرجات.",
                log_output="\n".join(logs),
            )
        return ApplyResult(
            success=True,
            message=f"تم حذف {len(deletions)} لقطة قديمة (احتفاظ بآخر {keep}).",
            log_output="\n".join(logs),
        )
