#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/boot_guard.py
=====================
وحدة الوقاية من عطل الإقلاع الكلاسيكي على btrfs: يحدث العطل عندما
يُعيد GRUB توليد grub.cfg بينما النظام يعمل من داخل لقطة (timeshift
أو snapper) فيسجّل مسار subvolume الخاص باللقطة بدل الجذر الحقيقي
(@) في سطور linux — الإقلاع التالي ينزلق إلى اللقطة وكل تحديثات
ما بعدها تُكتب في المكان الخاطئ.

المرجع التوثيقي: manjaro-doctor/issues/grub-btrfs-snapshot-boot.md
(نفس المشكلة الحقيقية التي تعالجها boot_sanity، لكن boot_guard هنا
وحدة إصلاح مستقلة بضمانات أشد):

  - تحديد subvolume الجذر الفعلي من /proc/mounts (لا افتراض @ ثابتاً).
  - نسخة احتياطية بطابع زمني من /etc/default/grub قبل أي تعديل.
  - تعديل محافظ: لا يُلمس إلا token الجذر flags في سطور
    GRUB_CMDLINE_LINUX(_DEFAULT) — كل سطر آخر يُحفظ بايت-ببايت.
  - التحقق بعد grub-mkconfig، وعند أي فشل: استعادة تلقائية للنسخة
    الاحتياطية + إعادة توليد ثم إبلاغ صادق.
  - رفض التنفيذ عند أي عدم يقين (نفس روح kernel_cleanup):
    subvolume غير محدد، عمل من داخل لقطة، غياب /etc/default/grub
    أو grub.cfg، أو غياب متغيري GRUB_CMDLINE أصلاً.
  - نظام غير btrfs → حالة "غير قابل للتطبيق" وليست خطأ.
  - يلتزم وضع dry-run العام (core/runtime.py) — طبقة أولى.

جميع الأوامر تُمرَّر كقوائم argv (قاعدة shell=False) والكتابات
الجذرية عبر core/file_ops.py (بلا shell ولا مسارات مؤقتة متوقعة).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from core.file_ops import backup_root_file, restore_root_file, write_root_file
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

log = get_logger("boot_guard")

# مسارات النظام (ثوابت على مستوى الوحدة لسهولة الاختبار)
PROC_MOUNTS = "/proc/mounts"
GRUB_DEFAULT = "/etc/default/grub"
GRUB_CFG = "/boot/grub/grub.cfg"

# أي token subvol في grub.cfg يحتوي أحد هذين المسارين يعني "إقلاع من لقطة"
_SNAPSHOT_MARKERS = (".snapshots", "timeshift-btrfs/snapshots")

_LINUX_LINE_RE = re.compile(r"^linux(?:16|efi)?\s")
_SUBVOL_TOKEN_RE = re.compile(r"subvol=([^\s'\"]+)")


# ---------------------------------------------------------------------------
# أدوات قراءة محايدة (تُعاد كتابتها في الاختبارات)
# ---------------------------------------------------------------------------

def _read_text(path: str) -> str | None:
    """قراءة نصية آمنة، مع محاولة cat عبر argv إن منعت الصلاحيات.
    تُرجع None عند الفشل الكامل."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except PermissionError:
        result = run_unprivileged(["cat", path])
        return result.stdout if result.ok else None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# محللات نقيّة (بلا I/O) — تُختبر مباشرة
# ---------------------------------------------------------------------------

def _parse_root_mount(mounts_content: str) -> tuple[str | None, str | None]:
    """يُرجع (نظام_الملفات, subvol) لمدخل نقطة الجذر "/" من محتوى
    /proc/mounts. subvol منزوع شرطة البداية ("/@" → "@") ليطابق عرف
    GRUB. يُرجع (None, None) إن لم يوجد مدخل الجذر."""
    for line in mounts_content.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "/":
            fstype = parts[2]
            subvol = None
            for opt in parts[3].split(","):
                if opt.startswith("subvol="):
                    subvol = opt[len("subvol="):].lstrip("/")
            return fstype, subvol
    return None, None


def _is_snapshot_subvol(subvol: str) -> bool:
    """هل يبدو أن هذا subvol مسار لقطة وليس جذراً حقيقياً؟"""
    return any(marker in subvol for marker in _SNAPSHOT_MARKERS)


def _analyze_grub_default(content: str, subvol: str) -> dict:
    """تحليل نقي لـ /etc/default/grub مقابل subvol الجذر المتوقع.

    يُرجع dict بالحقول:
      default_line / cmdline_line: وجود سطري الإعداد غير المعوّقين
      default_ok / cmdline_ok: هل يحوي المتغير rootflags=subvol=<subvol>؟
      default_wrong / cmdline_wrong: rootflags موجود لكن بقيمة subvol أخرى
      any_var: هل يوجد أي متغير GRUB_CMDLINE (لحكم الرفض عند الغياب الكامل)
      needs_edit: هل التعديل ضروري إطلاقاً؟
      editable: هل يمكن إصلاح آلي محافظ (يوجد سطر قابل للتعديل)؟
    """
    result = {
        "default_line": False, "cmdline_line": False,
        "default_ok": False, "cmdline_ok": False,
        "default_wrong": False, "cmdline_wrong": False,
        "any_var": False,
    }
    expected = f"rootflags=subvol={subvol}"
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key == "GRUB_CMDLINE_LINUX_DEFAULT":
            result["default_line"] = True
            result["any_var"] = True
            if expected in line:
                result["default_ok"] = True
            elif _SUBVOL_TOKEN_RE.search(line):
                result["default_wrong"] = True
        elif key == "GRUB_CMDLINE_LINUX":
            result["cmdline_line"] = True
            result["any_var"] = True
            if expected in line:
                result["cmdline_ok"] = True
            elif _SUBVOL_TOKEN_RE.search(line):
                result["cmdline_wrong"] = True

    result["needs_edit"] = not (result["default_ok"] or result["cmdline_ok"])
    # إصلاح آلي ممكن فقط إن وُجد سطر غير معوّق نعدّله — لا نُنشئ
    # متغيرات جديدة من العدم (محافظة مقصودة).
    result["editable"] = result["default_line"] or result["cmdline_line"]
    return result


def _build_grub_default_edit(content: str, subvol: str) -> str | None:
    """ينتج المحتوى المصحَّح لـ /etc/default/grub، أو None إن تعذّر
    الإصلاح المحافظ (لا سطر مناسب أو لا حاجة للتعديل). لا يُغيّر إلا
    token rootflags في سطري GRUB_CMDLINE_LINUX(_DEFAULT) — باقي
    الملف بايت-ببايت.

    القواعد (محافظة ومحدّدة):
      - rootflags الصحيح موجود أصلاً → None (لا تعديل).
      - rootflags بقيمة خاطئة في أي سطر → يُستبدل token بالقيمة الصحيحة.
      - rootflags غير موجود إطلاقاً → يُلحق في GRUB_CMDLINE_LINUX_DEFAULT
        إن وُجد، وإلا في GRUB_CMDLINE_LINUX (سطر واحد فقط — لا تكرار:
        إلحاقه في المتغيرين معاً غير ضروري ومضلِّل).
      - لا يُنشأ سطر جديد إذا غاب المتغيران عن الملف تماماً.
    """
    expected = f"rootflags=subvol={subvol}"
    if any(expected in line for line in content.splitlines()
           if not line.strip().startswith("#")):
        return None  # الإعداد الصحيح موجود في سطر فعلي (لا تعليق) — لا تعديل

    lines = content.splitlines()
    has_default = any(
        line.strip().startswith("GRUB_CMDLINE_LINUX_DEFAULT=") for line in lines
    )
    target_key = ("GRUB_CMDLINE_LINUX_DEFAULT" if has_default
                  else "GRUB_CMDLINE_LINUX")

    changed = False
    appended = False
    out_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        is_cmdline_key = key in ("GRUB_CMDLINE_LINUX_DEFAULT", "GRUB_CMDLINE_LINUX")

        if is_cmdline_key and not stripped.startswith("#"):
            if _SUBVOL_TOKEN_RE.search(line):
                # قيمة subvol خاطئة → استبدال token فقط (في كل السطور)
                line = _SUBVOL_TOKEN_RE.sub(f"subvol={subvol}", line, count=1)
                changed = True
                out_lines.append(line)
                continue
            # لا rootflags في السطر: إلحاق في السطر الهدف مرة واحدة فقط
            if key == target_key and not appended:
                quote = line.rstrip()[-1:] if line.rstrip()[-1:] in ("'", '"') else None
                if quote:
                    line = line.rstrip()[:-1] + f" rootflags=subvol={subvol}" + quote
                else:
                    # سطر بلا تنصيص (نادر) — القيمة المولدة من subvol
                    # بلا فراغات (من /proc/mounts) فالإلحاق المباشر آمن
                    line = line.rstrip() + f" rootflags=subvol={subvol}"
                appended = True
                changed = True
        out_lines.append(line)

    if not changed:
        return None
    if content.endswith("\n"):
        return "\n".join(out_lines) + "\n"
    return "\n".join(out_lines)


def _scan_grub_cfg_snapshot_lines(content: str) -> list[tuple[int, str]]:
    """سطور linux في grub.cfg التي يشير subvol= فيها إلى مسار لقطة.
    تُرجع قائمة (رقم_سطر, السطر)."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not _LINUX_LINE_RE.match(stripped):
            continue
        match = _SUBVOL_TOKEN_RE.search(stripped)
        if match and _is_snapshot_subvol(match.group(1)):
            hits.append((lineno, stripped))
    return hits


def _grub_cfg_is_clean(content: str) -> bool:
    """لا يوجد أي سطر linux يشير إلى subvol لقطة."""
    return not _scan_grub_cfg_snapshot_lines(content)


def _grub_cfg_has_rootflags(content: str, subvol: str) -> bool:
    """هل يحوي أي سطر linux في grub.cfg الـ rootflags المتوقع؟"""
    expected = f"rootflags=subvol={subvol}"
    for line in content.splitlines():
        stripped = line.strip()
        if _LINUX_LINE_RE.match(stripped) and expected in stripped:
            return True
    return False


def _unified_diff(old: str, new: str, path: str) -> str:
    """فرق موحد للعرض في المعاينة (نفس أسلوب diff -u)."""
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a{path}",
        tofile=f"b{path}",
    ))


# ---------------------------------------------------------------------------
# الوحدة نفسها
# ---------------------------------------------------------------------------

class BootGuardModule(MaintenanceModule):
    name = "حارس الإقلاع (btrfs + GRUB)"
    slug = "boot_guard"
    description = (
        "يمنع تكرار عطل انزلاق الإقلاع إلى لقطة btrfs: يتحقق من "
        "rootflags=subvol في إعدادات GRUB، ويكشف سطور grub.cfg التي تشير "
        "إلى مسارات اللقطات، ويصلح مع نسخة احتياطية وتراجع تلقائي"
    )
    needs_root = True
    risk_level = RiskLevel.DESTRUCTIVE  # تعديل GRUB — حساس بالتعريف
    icon = "drive-harddisk"
    doc_url = ("https://github.com/DrAbdulmalek/manjaro-doctor/blob/main/"
               "issues/grub-btrfs-snapshot-boot.md")

    # ------------------------------------------------------------------
    # scan — قراءة فقط
    # ------------------------------------------------------------------
    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        fstype, subvol = _parse_root_mount(_read_text(PROC_MOUNTS) or "")
        if fstype is None:
            return ScanResult(
                module_name=self.name,
                findings=[ScanFinding(
                    title="تعذّرت قراءة معلومات الجذر",
                    detail=f"لم يُعثر على مدخل الجذر في {PROC_MOUNTS}.",
                    severity=Severity.WARNING, actionable=False,
                )],
            )

        if fstype != "btrfs":
            # حالة "غير قابل للتطبيق" عمداً — ليست خطأ (قاعدة المهمة)
            findings.append(ScanFinding(
                title=f"غير قابل للتطبيق: الجذر {fstype} وليس btrfs",
                detail="وحدة حارس الإقلاع مخصصة لأنظمة btrfs فقط "
                       "(هنا تكون لقطات timeshift/snapper هي خطر الانزلاق).",
                severity=Severity.OK, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        if subvol is None:
            findings.append(ScanFinding(
                title="الجذر btrfs لكن subvolume غير محدد",
                detail=f"لم يُعثر على خيار subvol= في {PROC_MOUNTS} — "
                       "لن يُسمح بأي إصلاح آلي (رفض عند عدم اليقين).",
                severity=Severity.WARNING, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        if _is_snapshot_subvol(subvol):
            findings.append(ScanFinding(
                title=f"النظام يعمل من داخل لقطة (subvol=/{subvol}) وليس من الجذر الحقيقي!",
                detail="أي إصلاح آلي من هذه الجلسة سيكتب في اللقطة لا في الجذر — "
                       "أعد الإقلاع من الجذر الحقيقي أولاً وراجع manjaro-doctor.",
                severity=Severity.CRITICAL, actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        findings.append(ScanFinding(
            title=f"الجذر btrfs على subvol=/{subvol} (سليم)",
            detail="تم تحديد subvolume الجذر الفعلي من /proc/mounts.",
            severity=Severity.OK, actionable=False, raw_value=subvol,
        ))

        # ---- /etc/default/grub ----
        grub_default = _read_text(GRUB_DEFAULT)
        if grub_default is None:
            findings.append(ScanFinding(
                title=f"{GRUB_DEFAULT} غير موجود أو غير مقروء",
                detail="لا يمكن تقييم أو إصلاح rootflags بدون هذا الملف.",
                severity=Severity.WARNING, actionable=False,
            ))
        else:
            analysis = _analyze_grub_default(grub_default, subvol)
            if analysis["default_ok"] or analysis["cmdline_ok"]:
                findings.append(ScanFinding(
                    title=f"rootflags=subvol={subvol} مُفعّل في {GRUB_DEFAULT} (الحل الوقائي)",
                    detail="الإقلاع سيُثبَّت دائماً على الجذر الحقيقي مهما كانت اللقطات.",
                    severity=Severity.OK, actionable=False,
                ))
            else:
                wrong = analysis["default_wrong"] or analysis["cmdline_wrong"]
                findings.append(ScanFinding(
                    title="rootflags غير مضبوط في /etc/default/grub"
                          + (" — وقيمة موجودة تشير إلى subvol آخر!" if wrong else ""),
                    detail=(
                        f"المطلوب: rootflags=subvol={subvol} داخل GRUB_CMDLINE_LINUX(_DEFAULT).\n"
                        f"قابل للإصلاح الآلي المحافظ: {'نعم' if analysis['editable'] else 'لا — لا يوجد سطر إعداد غير معوّق'}"
                    ),
                    severity=Severity.CRITICAL if wrong else Severity.WARNING,
                    actionable=analysis["editable"],
                    raw_value=analysis,
                ))

        # ---- /boot/grub/grub.cfg ----
        grub_cfg = _read_text(GRUB_CFG)
        if grub_cfg is None:
            findings.append(ScanFinding(
                title=f"{GRUB_CFG} غير موجود أو غير مقروء",
                detail="قد يستخدم النظام systemd-boot، أو الصلاحيات غير كافية.",
                severity=Severity.INFO, actionable=False,
            ))
        else:
            snapshot_lines = _scan_grub_cfg_snapshot_lines(grub_cfg)
            if snapshot_lines:
                findings.append(ScanFinding(
                    title=f"{len(snapshot_lines)} سطر linux في grub.cfg يشير إلى مسار لقطة!",
                    detail="\n".join(
                        f"  سطر {n}: {text[:110]}..." if len(text) > 110 else f"  سطر {n}: {text}"
                        for n, text in snapshot_lines[:6]
                    ),
                    severity=Severity.CRITICAL,
                    actionable=True,
                    raw_value=snapshot_lines,
                ))
            else:
                findings.append(ScanFinding(
                    title="grub.cfg نظيف — لا سطور إقلاع تشير إلى لقطات",
                    detail=f"تم فحص كل سطور linux في {GRUB_CFG}.",
                    severity=Severity.OK, actionable=False,
                ))

        return ScanResult(module_name=self.name, findings=findings)

    # ------------------------------------------------------------------
    # preview — يعرض الأوامر الفعلية حرفياً
    # ------------------------------------------------------------------
    def preview(self) -> list[PreviewStep]:
        steps: list[PreviewStep] = []

        fstype, subvol = _parse_root_mount(_read_text(PROC_MOUNTS) or "")
        if fstype != "btrfs" or subvol is None or _is_snapshot_subvol(subvol):
            return [PreviewStep(
                description="لا يوجد إجراء آمن للتنفيذ (انظر نتائج الفحص — الرفض عند عدم اليقين)."
            )]

        grub_default = _read_text(GRUB_DEFAULT)
        grub_cfg = _read_text(GRUB_CFG)
        if grub_default is None or grub_cfg is None:
            return [PreviewStep(description="لا يوجد إجراء — ملفات GRUB غير متوفرة للقراءة.")]

        analysis = _analyze_grub_default(grub_default, subvol)
        new_content = _build_grub_default_edit(grub_default, subvol) if analysis["needs_edit"] else None

        if new_content is not None:
            stamp_note = f"{GRUB_DEFAULT}.bak-manjaro-care-<طابع زمني>"
            steps.append(PreviewStep(
                description=f"1) نسخة احتياطية إلى: {stamp_note}",
                command=f"pkexec cp -a -- {GRUB_DEFAULT} {stamp_note}",
            ))
            diff_text = _unified_diff(grub_default, new_content, GRUB_DEFAULT)
            steps.append(PreviewStep(
                description="2) التعديل المقترح (فرق موحد) — token الجذر flags فقط، باقي الملف بايت-ببايت:\n"
                            + diff_text.rstrip(),
                command=f"pkexec install -m 644 <ملف مؤقت عشوائي> {GRUB_DEFAULT}",
            ))
            steps.append(PreviewStep(
                description="3) إعادة توليد إعدادات GRUB ثم التحقق من نظافة الناتج",
                command=f"grub-mkconfig -o {GRUB_CFG}",
            ))
            steps.append(PreviewStep(
                description="4) عند فشل أي خطوة: استعادة تلقائية للنسخة الاحتياطية + إعادة توليد + إبلاغ.",
            ))
        elif _scan_grub_cfg_snapshot_lines(grub_cfg):
            # المشكلة في grub.cfg فقط — إعادة توليد تلتقط الإعداد الحالي
            steps.append(PreviewStep(
                description="1) لا تعديل على /etc/default/grub (الإعداد سليم) — المشكلة في grub.cfg المولّد سابقاً.",
            ))
            steps.append(PreviewStep(
                description="2) إعادة توليد grub.cfg من الإعداد الحالي (سيُلتقط rootflags الصحيح):",
                command=f"grub-mkconfig -o {GRUB_CFG}",
            ))
        else:
            steps.append(PreviewStep(description="لا توجد مشكلة تحتاج إجراءً — كل الفحوص سليمة."))

        return steps

    # ------------------------------------------------------------------
    # apply — بعد تأكيد صريح فقط
    # ------------------------------------------------------------------
    def apply(self) -> ApplyResult:
        # طبقة الحماية 1: وضع dry-run العام — رسالة صادقة بلا أي عمل
        if is_dry_run():
            preview_steps = self.preview()
            plan = "\n".join(
                f"• {s.description}" + (f"\n  $ {s.command}" if s.command else "")
                for s in preview_steps
            )
            return ApplyResult(
                success=True,
                message="[DRY-RUN] لم يُنفَّذ أي تعديل — أدناه خطة ما كان سيُنفَّذ.",
                log_output=plan,
            )

        fstype, subvol = _parse_root_mount(_read_text(PROC_MOUNTS) or "")

        # ---- بوابات الرفض (نفس روح kernel_cleanup) ----
        if fstype is None:
            return ApplyResult(success=False,
                               message="رفض التنفيذ: تعذّرت قراءة معلومات الجذر من /proc/mounts.")
        if fstype != "btrfs":
            # ليست حالة خطأ — "غير قابل للتطبيق" عمداً
            return ApplyResult(success=True,
                               message=f"غير قابل للتطبيق: الجذر {fstype} وليس btrfs — لم يُنفَّذ أي شيء.")
        if subvol is None:
            return ApplyResult(success=False,
                               message="رفض التنفيذ: الجذر btrfs لكن subvolume غير محدد من /proc/mounts — "
                                       "لا تخمين في ملفات الإقلاع.")
        if _is_snapshot_subvol(subvol):
            return ApplyResult(success=False,
                               message=f"رفض التنفيذ: النظام يعمل من داخل لقطة (subvol=/{subvol}) — "
                                       "أي إصلاح هنا سيكتب في اللقطة لا في الجذر الحقيقي. راجع manjaro-doctor.")

        grub_default = _read_text(GRUB_DEFAULT)
        grub_cfg = _read_text(GRUB_CFG)
        if grub_default is None:
            return ApplyResult(success=False,
                               message=f"رفض التنفيذ: {GRUB_DEFAULT} غير موجود أو غير مقروء.")
        if grub_cfg is None:
            return ApplyResult(success=False,
                               message=f"رفض التنفيذ: {GRUB_CFG} غير موجود أو غير مقروء — "
                                       "لا يمكن التحقق من نتيجة grub-mkconfig.")

        analysis = _analyze_grub_default(grub_default, subvol)
        cfg_snapshot_lines = _scan_grub_cfg_snapshot_lines(grub_cfg)
        needs_edit = analysis["needs_edit"]
        needs_regen = needs_edit or bool(cfg_snapshot_lines)

        if not needs_regen:
            # كل شيء سليم أصلاً — لا تعديل ولا إعادة توليد (لا-op صادق)
            return ApplyResult(
                success=True,
                message=f"كل شيء سليم — لم يُنفَّذ أي شيء: rootflags=subvol={subvol} "
                        f"مُفعّل في {GRUB_DEFAULT} و{GRUB_CFG} لا يشير إلى أي لقطة.",
            )

        if needs_edit:
            new_content = _build_grub_default_edit(grub_default, subvol)
            if new_content is None:
                return ApplyResult(success=False,
                                   message="رفض التنفيذ: لا يوجد سطر GRUB_CMDLINE_LINUX(_DEFAULT) غير معوّق "
                                           "يمكن تعديله محافظاً — راجع التوثيق للإصلاح اليدوي.")

            # 1) نسخة احتياطية إلزامية قبل أي لمس
            backup_path = backup_root_file(GRUB_DEFAULT)
            if backup_path is None:
                return ApplyResult(success=False,
                                   message=f"فشل إنشاء نسخة احتياطية من {GRUB_DEFAULT} — "
                                           "لن يُعدَّل الملف دون نسخة احتياطية (شرط إلزامي).")

            # 2) الكتابة الآمنة
            ok, err = write_root_file(GRUB_DEFAULT, new_content)
            if not ok:
                self._rollback(backup_path, regenerate=False)
                return ApplyResult(success=False,
                                   message=f"فشل تعديل {GRUB_DEFAULT}: {err} — استُعيدت النسخة الاحتياطية.",
                                   log_output=err)
        else:
            backup_path = None  # لا تعديل على default — لا حاجة لتراجع

        # 3) إعادة توليد grub.cfg
        regen = run_privileged(["grub-mkconfig", "-o", GRUB_CFG], timeout=120)
        new_cfg = _read_text(GRUB_CFG) or ""

        if not regen.ok:
            detail = f"grub-mkconfig فشل (كود {regen.returncode})."
            if backup_path is not None:
                self._rollback(backup_path, regenerate=True)
                detail += " استُعيدت النسخة الاحتياطية وأُعيدت توليد grub.cfg من الإعداد الأصلي."
            return ApplyResult(success=False, message=detail,
                               log_output=regen.stdout + regen.stderr)

        # 4) التحقق من النتيجة — أي شك = تراجع
        verification_failures = []
        if not _grub_cfg_is_clean(new_cfg):
            verification_failures.append("ما زالت هناك سطور linux تشير إلى مسارات لقطات في grub.cfg الجديد.")
        if needs_edit and not _grub_cfg_has_rootflags(new_cfg, subvol):
            verification_failures.append(f"rootflags=subvol={subvol} غير ظاهر في grub.cfg الجديد.")

        if verification_failures:
            detail = "فشل التحقق بعد إعادة التوليد: " + " ".join(verification_failures)
            if backup_path is not None:
                self._rollback(backup_path, regenerate=True)
                detail += " استُعيدت النسخة الاحتياطية كاملة."
            else:
                detail += " (لا تعديل كان قد أُجري على /etc/default/grub — راجع يدوياً.)"
            return ApplyResult(success=False, message=detail,
                               log_output=regen.stdout + regen.stderr)

        # 5) نجاح
        msg = "تم إعادة توليد grub.cfg والتحقق منها: لا إشارة لأي لقطة."
        if needs_edit:
            msg += (f"\nتمت إضافة/تصحيح rootflags=subvol={subvol} في {GRUB_DEFAULT}"
                    f"\nالنسخة الاحتياطية: {backup_path}"
                    f"\nأعد التشغيل وتحقق بـ: findmnt /")
        else:
            msg += f"\nلم يُعدَّل {GRUB_DEFAULT} — كان الإعداد سليماً وأُعيد توليد grub.cfg فقط."
        return ApplyResult(success=True, message=msg,
                           log_output=regen.stdout + regen.stderr)

    def _rollback(self, backup_path: str, regenerate: bool) -> None:
        """استعادة النسخة الاحتياطية (ومحاولة إعادة توليد) — أفضل جهد،
        والفشل يُسجَّل في اللوغ ولا يُخفى."""
        ok, err = restore_root_file(backup_path, GRUB_DEFAULT)
        if not ok:
            log.error("فشلت استعادة النسخة الاحتياطية %s: %s", backup_path, err)
            return
        log.info("استُعيد %s من %s", GRUB_DEFAULT, backup_path)
        if regenerate:
            regen = run_privileged(["grub-mkconfig", "-o", GRUB_CFG], timeout=120)
            if not regen.ok:
                log.error("فشلت إعادة توليد grub.cfg بعد الاستعادة: %s", regen.stderr)
