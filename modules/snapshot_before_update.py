#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/snapshot_before_update.py
=================================
إنشاء لقطة نظام موسومة "manjaro-care pre-update" قبل تحديث النظام —
حتى يصبح أي تحديث فاشل قابلاً للرجوع بدلاً من كارثة.

اكتشاف الأداة المتاحة (أحدهما يكفي):
  - timeshift  → إنشاء: timeshift --create --comments "..."
  - snapper    → إنشاء: snapper -c root create --description "..."
  - لا شيء     → حالة "غير قابل للتطبيق" برسالة تثبيت واضحة (ليست خطأ).

الرجوع (restore) متاح عبر النافذة المخصصة (has_custom_ui) بتأكيد
مزدوج وتحذير صريح — راجع gui/snapshot_dialog.py. ملاحظة صادقة:
رجوع timeshift تفاعلي بطبيعته (يطالب بالتأكيد في الطرفية) لذلك
تعرضه النافذة كأمر حرفي للنسخ لا كزر تنفيذ آلي — أتمتته كانت سترسل
"y" نيابة عن المستخدم في عملية تدمر حالة النظام، وهذا يخالف فلسفة
المشروع. رجوع snapper (rollback) يُنفَّذ آلياً عبر pkexec.

التحديث الفعلي بعد اللقطة اختياري بتأكيد منفصل تماماً في النافذة
المخصصة (pacman -Syu --noconfirm عبر pkexec) — لا يحدث في apply().
"""

from __future__ import annotations

import os
import re
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
from core.privilege import run_privileged
from core.runtime import is_dry_run

log = get_logger("snapshot_before_update")

SNAPSHOT_TAG = "manjaro-care pre-update"
_MIN_FREE_BYTES = 2 * 1024 ** 3  # أقل من 2GB = تحذير مساحة قبل لقطة

# تنسيق أسطر snapper -c root list:
#   # | Type | Pre # | Date | User | Cleanup | Description | Userdata
_SNAPPER_RE = re.compile(
    r"^\s*(\d+)\s*\|[^|]*\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)"
)

# تنسيق أسطر timeshift --list (تقريبي — الأداة تغيّر التنسيق بين
# الإصدارات؛ التحليل هنا ببيت رحمة ويتجاهل ما لا يطابق):
#   0  >  2026-01-02 12:00:00  4567 MB  O  /dev/sda2  -- وصف
_TIMESHIFT_RE = re.compile(
    r"^\s*(\d+)\s*[> ]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+.*?(?:--\s*(.*))?$"
)


# ---------------------------------------------------------------------------
# محللات نقيّة (بلا I/O)
# ---------------------------------------------------------------------------

def parse_snapper_list(output: str) -> list[dict]:
    """يحلل مخرجات snapper -c root list إلى قائمة {num, date, desc}."""
    snaps = []
    for line in output.splitlines():
        m = _SNAPPER_RE.match(line)
        if m:
            snaps.append({
                "num": m.group(1),
                "date": m.group(2).strip(),
                "desc": m.group(5).strip(),
            })
    return snaps


def parse_timeshift_list(output: str) -> list[dict]:
    """يحلل مخرجات timeshift --list إلى قائمة {num, date, desc}."""
    snaps = []
    for line in output.splitlines():
        m = _TIMESHIFT_RE.match(line)
        if m:
            snaps.append({
                "num": m.group(1),
                "date": m.group(2),
                "desc": (m.group(3) or "").strip(),
            })
    return snaps


def free_bytes_on_root() -> int | None:
    """المساحة المتاحة على الجذر (os.statvfs — قراءة خالصة بلا أوامر)."""
    try:
        st = os.statvfs("/")
        return st.f_bavail * st.f_frsize
    except OSError:
        return None


def _fmt_gb(n: int | None) -> str:
    if n is None:
        return "تعذر القياس"
    return f"{n / 1024 ** 3:.1f} GB"


# ---------------------------------------------------------------------------
# قائمة اللقطات الموحّدة (تستخدمها الوحدة والنافذة المخصصة)
# ---------------------------------------------------------------------------

def detect_tool() -> str | None:
    """أول أداة لقطات متاحة: timeshift ثم snapper. None = لا أداة."""
    if shutil.which("timeshift"):
        return "timeshift"
    if shutil.which("snapper"):
        return "snapper"
    return None


def list_snapshots(tool: str) -> tuple[list[dict], str | None]:
    """قائمة اللقطات موحّدة الشكل عبر الأداة المكتشفة.
    يُرجع (قائمة, رسالة خطأ أو None). قراءة فقط.

    ملاحظة صادقة: parsing مخرجات timeshift غير موثّق رسمياً وقد يختلف
    بين الإصدارات — غير مُجرَّب على نظام حقيقي بعد.
    """
    from core.privilege import run_unprivileged

    if tool == "timeshift":
        r = run_unprivileged(["timeshift", "--list"])
        if not r.ok:
            return [], f"فشل timeshift --list (كود {r.returncode})"
        return parse_timeshift_list(r.stdout), None
    if tool == "snapper":
        r = run_unprivileged(["snapper", "-c", "root", "list"])
        if not r.ok:
            return [], f"فشل snapper -c root list (كود {r.returncode}) — تحقق من إعداد الحزمة الجذرية"
        return parse_snapper_list(r.stdout), None
    return [], "لا أداة لقطات مثبتة"


# ---------------------------------------------------------------------------
# الوحدة
# ---------------------------------------------------------------------------

class SnapshotBeforeUpdateModule(MaintenanceModule):
    name = "لقطة قبل التحديث"
    slug = "snapshot_before_update"
    description = (
        "ينشئ لقطة نظام موسومة 'manjaro-care pre-update' (timeshift أو "
        "snapper) قبل التحديث، مع رجوع بتأكيد مزدوج عبر «إدارة فردية»"
    )
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "document-save"
    has_custom_ui = True  # قائمة لقطات + رجوع بتأكيد مزدوج + تحديث اختياري

    # ------------------------------------------------------------------
    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        tool = detect_tool()

        if tool is None:
            findings.append(ScanFinding(
                title="لا أداة لقطات مثبتة",
                detail="ثبّت إحدى الأداتين لحماية نظامك قبل التحديثات:\n"
                       "  sudo pacman -S timeshift\n"
                       "  sudo pacman -S snapper  (يتطلب إعداد حزمة snapper root)",
                severity=Severity.WARNING, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        free = free_bytes_on_root()
        if free is not None and free < _MIN_FREE_BYTES:
            findings.append(ScanFinding(
                title=f"المساحة المتاحة منخفضة ({_fmt_gb(free)})",
                detail="إنشاء لقطة btrfs/rsync قد يفشل أو يملأ القرص — "
                       "حرّر مساحة أولاً.",
                severity=Severity.WARNING, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title=f"المساحة المتاحة: {_fmt_gb(free)}",
                detail=f"الأداة المكتشفة: {tool}",
                severity=Severity.OK, actionable=False,
            ))

        snaps, error = list_snapshots(tool)
        if error:
            findings.append(ScanFinding(
                title="تعذّرت قراءة قائمة اللقطات",
                detail=error, severity=Severity.WARNING, actionable=False,
            ))
        elif snaps:
            findings.append(ScanFinding(
                title=f"{len(snaps)} لقطة موجودة (آخر 5)",
                detail="\n".join(
                    f"  #{s['num']} | {s['date']} | {s['desc'] or 'بدون وصف'}"
                    for s in snaps[-5:]
                ),
                severity=Severity.INFO, actionable=False,
                raw_value=snaps,
            ))
        else:
            findings.append(ScanFinding(
                title="لا لقطات موجودة بعد",
                detail="إنشئ أول لقطة قبل التحديث القادم.",
                severity=Severity.INFO, actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    # ------------------------------------------------------------------
    def preview(self) -> list[PreviewStep]:
        tool = detect_tool()
        if tool == "timeshift":
            return [PreviewStep(
                description=f"إنشاء لقطة موسومة '{SNAPSHOT_TAG}' عبر timeshift",
                command=f'timeshift --create --comments "{SNAPSHOT_TAG}"',
            )]
        if tool == "snapper":
            return [PreviewStep(
                description=f"إنشاء لقطة موسومة '{SNAPSHOT_TAG}' عبر snapper (الحزمة الجذرية)",
                command=f'snapper -c root create --description "{SNAPSHOT_TAG}"',
            )]
        return [PreviewStep(
            description="لا إجراء — لا أداة لقطات مثبتة. ثبّت timeshift أو snapper أولاً."
        )]

    # ------------------------------------------------------------------
    def apply(self) -> ApplyResult:
        # طبقة الحماية 1: وضع dry-run العام — خطة صادقة بلا أي تنفيذ
        if is_dry_run():
            plan = "\n".join(
                f"• {s.description}" + (f"\n  $ {s.command}" if s.command else "")
                for s in self.preview()
            )
            return ApplyResult(success=True,
                               message="[DRY-RUN] لم تُنشأ أي لقطة — أدناه ما كان سيُنفَّذ.",
                               log_output=plan)

        tool = detect_tool()
        if tool == "timeshift":
            result = run_privileged(
                ["timeshift", "--create", "--comments", SNAPSHOT_TAG], timeout=600
            )
        elif tool == "snapper":
            result = run_privileged(
                ["snapper", "-c", "root", "create", "--description", SNAPSHOT_TAG],
                timeout=600,
            )
        else:
            return ApplyResult(success=False,
                               message="لا أداة لقطات مثبتة — ثبّت timeshift أو snapper أولاً.")

        if result.ok:
            return ApplyResult(
                success=True,
                message=f"تم إنشاء لقطة '{SNAPSHOT_TAG}' عبر {tool}. "
                        "يمكنك الآن التحديث بأمان، والرجوع متاح من «إدارة فردية».",
                log_output=result.stdout + result.stderr,
            )
        return ApplyResult(
            success=False,
            message=f"فشل إنشاء اللقطة عبر {tool} (كود {result.returncode}) — "
                    "لم يُنفَّذ أي تحديث. راجع المخرجات.",
            log_output=result.stdout + result.stderr,
        )
