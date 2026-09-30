#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/btrfs_health.py
=======================
فحص صحة نظام ملفات btrfs والإقلاع المرتبط به — قراءة فقط في scan()،
مع إجراءين اختياريين (كلٌّ بمعاينة وتأكيد منفصلين عبر النافذة
المخصصة): بدء scrub وتفعيل fstrim.timer.

الصدق أولاً: بعض فحوص btrfs/SMART تتطلب صلاحيات جذر للقراءة نفسها.
scan() لا يفتح نوافذ pkexec عمداً (مصادقة منبثقة أثناء كل فحص شامل
تجربة سيئة) — إن فشل أمر قراءة بسبب الصلاحيات يظهر ذلك صراحة في
النتيجة ("يتطلب صلاحيات — متاح من الإجراء") ولا يُختلق نجاح.

فحوص scan():
  1) حالة آخر scrub (btrfs scrub status /)
  2) الاستخدام الحقيقي للمساحة (os.statvfs) — تفصيل metadata
     (btrfs filesystem usage) يتطلب جذر فيُشار لذلك
  3) إحصاءات أخطاء الأجهزة (btrfs device stats /)
  4) SMART (smartctl إن وُجد على الجهاز الحامل للجذر)
  5) حالة fstrim.timer (is-enabled/is-active)
  6) أبطأ خدمات الإقلاع (systemd-analyze blame — أعلى 8)
"""

from __future__ import annotations

import os
import re

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
from core.privilege import run_privileged, run_unprivileged
from core.runtime import is_dry_run

log = get_logger("btrfs_health")

_MIN_FREE_BYTES = 2 * 1024 ** 3
_BLAME_TOP = 8


# ---------------------------------------------------------------------------
# محللات نقيّة
# ---------------------------------------------------------------------------

def parse_scrub_status(text: str) -> dict:
    """يستخرج حالة آخر scrub من مخرجات btrfs scrub status."""
    status = {"state": None, "errors": None, "duration": None}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "status":
            status["state"] = value
        elif key == "error summary":
            status["errors"] = value
        elif key == "duration":
            status["duration"] = value
    return status


def parse_device_stats(text: str) -> list[tuple[str, float]]:
    """يحلل مخرجات btrfs device stats: أسطر '<الجهاز> <العدد>'."""
    stats = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                stats.append((parts[0], float(parts[1])))
            except ValueError:
                continue
    return stats


def parse_blame(text: str, top: int = _BLAME_TOP) -> list[tuple[str, str]]:
    """أبطأ خدمات الإقلاع من systemd-analyze blame: (الزمن, الوحدة).
    الزمن قد يكون '2.500s' أو '900ms' أو '1min 2.500s' (كلمتان)."""
    rows = []
    unit_re = re.compile(r"^[\w@.-]+\.(service|timer|mount|target|scope|socket|path)$")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and unit_re.match(parts[-1]):
            rows.append((" ".join(parts[:-1]), parts[-1]))
    return rows[:top]


def parent_device(source: str) -> str | None:
    """الجهاز الفيزيائي الحامل للجذر من مصدر findmnt:
    '/dev/sda2[/@]' → '/dev/sda' ، '/dev/nvme0n1p2[/@]' → '/dev/nvme0n1'."""
    src = source.split("[", 1)[0].strip()
    if src.startswith("/dev/"):
        name = src[len("/dev/"):]
        name = re.sub(r"p?\d+$", "", name)  # sda2→sda ، nvme0n1p2→nvme0n1 ، mmcblk0p1→mmcblk0
        return f"/dev/{name}" if name else None
    return None  # UUID/LABEL — لا يمكن تحديد الجهاز بثقة هنا


def _fmt_gb(n: int) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


def _statvfs_root() -> tuple[int, int]:
    """(المتاح، الإجمالي) لنظام الملفات الجذر — مغلّف هنا ليُسخّر في
    اختبارات _healthy_env بدل قراءة القرص الحقيقي لآلة التشغيل."""
    st = os.statvfs("/")
    return st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize


# ---------------------------------------------------------------------------
# الوحدة
# ---------------------------------------------------------------------------

class BtrfsHealthModule(MaintenanceModule):
    name = "صحة btrfs"
    slug = "btrfs_health"
    description = (
        "فحص صحة btrfs: حالة scrub، الاستخدام والأخطاء، SMART، fstrim، "
        "وأبطأ خدمات الإقلاع — مع scrub وتفعيل fstrim كإجراءين اختياريين"
    )
    needs_root = True
    risk_level = RiskLevel.SAFE  # الإجراءان لا يحذفان بيانات
    icon = "drive-multidisk"
    has_custom_ui = True  # إجراءان منفصلان بمعاينة وتأكيد لكل منهما

    # ------------------------------------------------------------------
    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        fstype = run_unprivileged(["findmnt", "-no", "FSTYPE", "/"]).stdout.strip()
        if fstype != "btrfs":
            findings.append(ScanFinding(
                title=f"غير قابل للتطبيق: الجذر {fstype or 'غير معروف'} وليس btrfs",
                detail="وحدة صحة btrfs مخصصة لأنظمة btrfs فقط.",
                severity=Severity.OK, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        # 1) حالة آخر scrub — قد تتطلب جذر للقراءة
        scrub = run_unprivileged(["btrfs", "scrub", "status", "/"])
        if scrub.ok:
            info = parse_scrub_status(scrub.stdout)
            if info["state"] == "finished" and "no errors" in (info["errors"] or ""):
                findings.append(ScanFinding(
                    title=f"آخر scrub سليم (انتهى بدون أخطاء، {info['duration'] or '؟'})",
                    severity=Severity.OK, actionable=False, detail="",
                ))
            elif info["state"] == "running":
                findings.append(ScanFinding(
                    title="scrub قيد التشغيل الآن",
                    detail="اتركه يكتمل — لا تشغّل scrub آخر بالتوازي.",
                    severity=Severity.INFO, actionable=False,
                ))
            elif info["state"] is None:
                findings.append(ScanFinding(
                    title="تعذّر تحليل حالة scrub",
                    detail=f"مخرجات غير متوقعة:\n{scrub.stdout[:300]}",
                    severity=Severity.INFO, actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title=f"scrub بحالة '{info['state']}' مع أخطاء؟",
                    detail=(info["errors"] or "") + "\nراجع btrfs scrub status / يدوياً.",
                    severity=Severity.CRITICAL, actionable=False,
                ))
        else:
            findings.append(ScanFinding(
                title="حالة scrub تتطلب صلاحيات جذر للقراءة",
                detail="متاح من الإجراء (بدء scrub) أو يدوياً: btrfs scrub status /",
                severity=Severity.INFO, actionable=False,
            ))

        # 2) الاستخدام الحقيقي — statvfs بلا أوامر؛ تفصيل metadata يتطلب جذر
        try:
            free, total = _statvfs_root()
            findings.append(ScanFinding(
                title=f"المساحة: {_fmt_gb(free)} متاحة من {_fmt_gb(total)}",
                detail=(
                    "أرقام df على مستوى الكتل. توزيع data/metadata الدقيق "
                    "يتطلب جذر: btrfs filesystem usage / (متاح من الإجراء؟ لا — "
                    "اقرأه يدوياً؛ لا نفتح pkexec أثناء الفحص)."
                ),
                severity=Severity.WARNING if free < _MIN_FREE_BYTES else Severity.OK,
                actionable=False,
                raw_value={"free": free, "total": total},
            ))
        except OSError:
            findings.append(ScanFinding(
                title="تعذر قياس المساحة (statvfs)",
                severity=Severity.INFO, actionable=False, detail="",
            ))

        # 3) إحصاءات أخطاء الأجهزة
        stats = run_unprivileged(["btrfs", "device", "stats", "/"])
        if stats.ok:
            parsed = parse_device_stats(stats.stdout)
            bad = [(d, v) for d, v in parsed if v > 0]
            if bad:
                findings.append(ScanFinding(
                    title=f"أخطاء جهاز مسجلة في {len(bad)} جهاز!",
                    detail="\n".join(f"  {d}: {v}" for d, v in bad)
                           + "\nشغّل scrub للفحص الشامل وخدم أنظف الأخطاء المؤقتة.",
                    severity=Severity.CRITICAL, actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title="device stats نظيفة — لا أخطاء قراءة/كتابة/تصحيح مسجلة",
                    severity=Severity.OK, actionable=False, detail="",
                ))
        else:
            findings.append(ScanFinding(
                title="إحصاءات الأجهزة تتطلب صلاحيات جذر",
                detail="يدوياً: btrfs device stats /",
                severity=Severity.INFO, actionable=False,
            ))

        # 4) SMART — إن وُجدت الأداة وتحدد الجهاز
        source = run_unprivileged(["findmnt", "-no", "SOURCE", "/"]).stdout.strip()
        device = parent_device(source)
        if device:
            smart = run_unprivileged(["smartctl", "--health", device])
            if smart.ok:
                healthy = "PASSED" in smart.stdout
                findings.append(ScanFinding(
                    title=f"SMART لـ {device}: {'سليم (PASSED)' if healthy else 'تحذير!'}",
                    detail=smart.stdout.strip()[:400] if not healthy else "",
                    severity=Severity.OK if healthy else Severity.CRITICAL,
                    actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title=f"SMART غير متاح بدون صلاحيات (أو smartctl غير مثبت) لـ {device}",
                    detail="يدوياً: sudo smartctl --health " + device,
                    severity=Severity.INFO, actionable=False,
                ))
        else:
            findings.append(ScanFinding(
                title="تعذّر تحديد الجهاز الفيزيائي للجذر (مصدر غير قياسي)",
                detail=f"مصدر الجذر: {source or 'غير معروف'}",
                severity=Severity.INFO, actionable=False,
            ))

        # 5) fstrim.timer
        enabled = run_unprivileged(["systemctl", "is-enabled", "fstrim.timer"])
        if enabled.stdout.strip() == "enabled":
            findings.append(ScanFinding(
                title="fstrim.timer مفعّل (صيانة SSD التلقائية تعمل)",
                severity=Severity.OK, actionable=False, detail="",
            ))
        else:
            findings.append(ScanFinding(
                title=f"fstrim.timer غير مفعّل ({enabled.stdout.strip() or 'غير معروف'})",
                detail="على SSD يُنصح بتفعيله — متاح من الإجراء.",
                severity=Severity.WARNING, actionable=False,
            ))

        # 6) أبطأ خدمات الإقلاع
        blame = run_unprivileged(["systemd-analyze", "blame"])
        if blame.ok and blame.stdout.strip():
            rows = parse_blame(blame.stdout)
            findings.append(ScanFinding(
                title=f"أبطأ {len(rows)} خدمة إقلاع",
                detail="\n".join(f"  {t:>8}  {u}" for t, u in rows),
                severity=Severity.INFO, actionable=False,
                raw_value=rows,
            ))
        else:
            findings.append(ScanFinding(
                title="systemd-analyze blame غير متاح الآن",
                detail="قد لا تكون بيانات الإقلاع الحالية جاهزة بعد.",
                severity=Severity.INFO, actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    # ------------------------------------------------------------------
    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(
                description="بدء فحص scrub كامل لنظام btrfs (قراءة كل البيانات والتحقق من checksums — لا يحذف شيئاً)",
                command="btrfs scrub start -B /",
            ),
            PreviewStep(
                description="تفعيل fstrim.timer (صيانة SSD الأسبوعية التلقائية)",
                command="systemctl enable --now fstrim.timer",
            ),
        ]

    # ------------------------------------------------------------------
    def apply(self) -> ApplyResult:
        # الإجراءات تنفَّذ من النافذة المخصصة (تأكيد منفصل لكل إجراء).
        # المسار القياسي هنا يعمل أيضاً إن استُدعي — ينفذ ما "يلزم فعله"
        # فقط: scrub إن لم يكن جارياً، وتفعيل fstrim إن كان معطلاً.

        if is_dry_run():
            plan = "\n".join(
                f"• {s.description}" + (f"\n  $ {s.command}" if s.command else "")
                for s in self.preview()
            )
            return ApplyResult(success=True,
                               message="[DRY-RUN] لن يُنفَّذ شيء — أدناه ما كان سيُنفَّذ.",
                               log_output=plan)

        logs, ok_all = [], True

        scrub_running = run_unprivileged(["btrfs", "scrub", "status", "/"]).stdout
        if "running" not in scrub_running.lower():
            r1 = run_privileged(["btrfs", "scrub", "start", "-B", "/"], timeout=3600)
            logs.append(f"$ btrfs scrub start -B /\n{r1.stdout}{r1.stderr}")
            ok_all &= r1.ok
        else:
            logs.append("scrub يعمل بالفعل — لم يبدأ آخر متوازٍ")

        enabled = run_unprivileged(["systemctl", "is-enabled", "fstrim.timer"]).stdout.strip()
        if enabled != "enabled":
            r2 = run_privileged(["systemctl", "enable", "--now", "fstrim.timer"])
            logs.append(f"$ systemctl enable --now fstrim.timer\n{r2.stdout}{r2.stderr}")
            ok_all &= r2.ok
        else:
            logs.append("fstrim.timer مفعّل بالفعل")

        return ApplyResult(
            success=ok_all,
            message="تم تنفيذ الإجراءات المطلوبة" if ok_all else "فشل جزئي — راجع المخرجات",
            log_output="\n".join(logs),
        )
