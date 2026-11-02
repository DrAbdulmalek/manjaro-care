#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تنظيف محافظ: فحص شامل، وتنفيذ محدود لأوامر صيانة معروفة فقط."""
from __future__ import annotations

import os
import re
import shutil
import stat
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
from core.privilege import run_privileged, run_unprivileged

log = get_logger("system_cleaner")

# السياسة الرابعة تحدد هل يسمح بالتطبيق أم تبقى النتيجة للمراجعة فقط.
# لا تُعامل بيانات التطبيقات أو ملفات المستخدم المحذوفة على أنها cache.
_CLEAN_TARGETS = {
    "pacman_cache": ("/var/cache/pacman/pkg", "ذاكرة pacman المؤقتة", "paccache"),
    "journal_old": ("journal", "سجلات systemd القديمة", "journal"),
    "yay_cache": ("~/.cache/yay", "كاش بناء AUR الخاص بـ yay", "review"),
    "paru_cache": ("~/.cache/paru", "كاش بناء AUR الخاص بـ paru", "review"),
    "tmp_files": ("/tmp", "ملفات مؤقتة قد تستخدمها عمليات جارية", "review"),
    "trash": ("~/.local/share/Trash", "سلة المحذوفات — قد تحتوي ملفات شخصية", "review"),
    "thumbnail_cache": ("~/.cache/thumbnails", "ذاكرة الصور المصغرة", "review"),
    "pip_cache": ("~/.cache/pip", "ذاكرة pip", "review"),
    "flatpak_app_data": ("~/.var/app", "بيانات تطبيقات Flatpak وليست كاش تنظيف عاماً", "review"),
}
_MAX_SIZE_ENTRIES = 250_000


def _expand(raw_path: str) -> Path:
    if raw_path.startswith("~"):
        raw_path = os.path.expanduser(raw_path)
    return Path(raw_path)


def _get_size(path: Path, max_entries: int = _MAX_SIZE_ENTRIES) -> int:
    """حساب محدود للقراءة فقط، لا يتبع symlinks ولا يعبر إلى أهدافها."""
    try:
        root_stat = path.lstat()
    except OSError:
        return 0
    if stat.S_ISLNK(root_stat.st_mode):
        return 0
    if stat.S_ISREG(root_stat.st_mode):
        return root_stat.st_size
    if not stat.S_ISDIR(root_stat.st_mode):
        return 0

    total = 0
    entries_seen = 0
    visited: set[tuple[int, int]] = set()
    stack = [path]
    while stack and entries_seen < max_entries:
        current = stack.pop()
        try:
            current_stat = current.lstat()
            if not stat.S_ISDIR(current_stat.st_mode):
                continue
            identity = (current_stat.st_dev, current_stat.st_ino)
            if identity in visited:
                continue
            visited.add(identity)
            with os.scandir(current) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > max_entries:
                        break
                    try:
                        item_stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISLNK(item_stat.st_mode):
                        continue
                    if stat.S_ISREG(item_stat.st_mode):
                        total += item_stat.st_size
                    elif stat.S_ISDIR(item_stat.st_mode):
                        stack.append(Path(entry.path))
        except OSError:
            continue
    return total


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


class SystemCleanerModule(MaintenanceModule):
    name = "التنظيف العميق (System Cleaner)"
    slug = "system_cleaner"
    description = "فحص محافظ للكاش والسجلات؛ لا يحذف بيانات التطبيقات أو ملفات المستخدم تلقائياً"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "edit-clear-all"

    def scan(self) -> ScanResult:
        findings = []
        total_size = 0
        for _key, (raw_path, desc, policy) in _CLEAN_TARGETS.items():
            path = _expand(raw_path)
            size = _get_size(path) if raw_path != "journal" else 0
            if raw_path == "journal":
                journal = shutil.which("journalctl")
                if journal:
                    result_size = run_unprivileged(["journalctl", "--disk-usage"])
                    if result_size.ok:
                        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B?)", result_size.stdout, re.I)
                        if match:
                            number = float(match.group(1))
                            unit = match.group(2).upper().rstrip("B")
                            multiplier = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}.get(unit, 1)
                            size = int(number * multiplier)
            if size <= 0:
                continue
            actionable = policy in {"paccache", "journal"}
            explanation = (
                "يمكن تقليصه مع الإبقاء على آخر نسختين من كل حزمة."
                if policy == "paccache" else
                "يمكن تقليص السجلات إلى آخر 7 أيام بعد المعاينة والموافقة."
                if policy == "journal" else
                "معلومة فقط: لن تُحذف هذه البيانات تلقائياً؛ قد تتضمن ملفات قيد الاستخدام أو بيانات شخصية."
            )
            findings.append(ScanFinding(
                title=f"{desc}: {_human_size(size)}",
                detail=f"المسار: {path if raw_path != 'journal' else 'systemd journal'}\n{explanation}",
                severity=Severity.WARNING if size > 500 * 1024 * 1024 else Severity.INFO,
                actionable=actionable,
                raw_value={"path": str(path), "size": size, "policy": policy},
            ))
            total_size += size

        if not findings:
            findings.append(ScanFinding(
                title="لم يُعثر على بيانات ضمن أهداف الفحص",
                detail="عدم ظهور نتائج لا يعني أن جميع أجزاء النظام خالية من البيانات المؤقتة.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.insert(0, ScanFinding(
                title=f"إجمالي حجم العناصر المفحوصة: {_human_size(total_size)}",
                detail="الإجمالي يشمل عناصر للمراجعة فقط، وليس كله قابلاً للحذف.",
                severity=Severity.INFO,
                actionable=False,
            ))
        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        steps = []
        for _key, (_raw_path, desc, policy) in _CLEAN_TARGETS.items():
            if policy == "paccache":
                if shutil.which("paccache"):
                    steps.append(PreviewStep(
                        description=f"{desc}: الإبقاء على آخر نسختين من كل حزمة",
                        command="paccache -rk2",
                    ))
                else:
                    steps.append(PreviewStep(
                        description="تخطي كاش pacman لأن paccache غير مثبت؛ لا يوجد fallback للحذف اليدوي."
                    ))
            elif policy == "journal":
                if shutil.which("journalctl"):
                    steps.append(PreviewStep(
                        description="تقليص سجلات systemd إلى آخر 7 أيام",
                        command="journalctl --vacuum-time=7d",
                    ))
                else:
                    steps.append(PreviewStep(description="تخطي سجلات systemd: journalctl غير متاح."))
            else:
                steps.append(PreviewStep(
                    description=f"للمراجعة فقط — لن يتم حذف {desc}."
                ))
        return steps or [PreviewStep(description="لا توجد عمليات تنظيف مسموحة حالياً.")]

    def apply(self) -> ApplyResult:
        logs = []
        failures = []
        applied = []
        if shutil.which("paccache"):
            result = run_privileged(["paccache", "-rk2"])
            logs.append(result.stdout + result.stderr)
            if result.ok:
                applied.append("كاش pacman")
            else:
                failures.append("فشل تقليص كاش pacman")
        else:
            logs.append("تم تخطي كاش pacman: paccache غير مثبت؛ لم يُستخدم حذف بديل.")

        if shutil.which("journalctl"):
            result = run_privileged(["journalctl", "--vacuum-time=7d"])
            logs.append(result.stdout + result.stderr)
            if result.ok:
                applied.append("سجلات systemd الأقدم من 7 أيام")
            else:
                failures.append("فشل تقليص سجلات systemd")
        if failures:
            return ApplyResult(
                success=False,
                message="؛ ".join(failures) + ". لم تُمس ملفات المستخدم أو بيانات التطبيقات.",
                log_output="\n".join(logs),
            )
        if not applied:
            return ApplyResult(
                success=True,
                message="لم يُنفذ أي حذف: أدوات التنظيف الآمن غير متاحة. بقيت جميع الملفات كما هي.",
                log_output="\n".join(logs),
            )
        return ApplyResult(
            success=True,
            message="اكتملت عمليات الصيانة المحدودة: " + "، ".join(applied) +
                    ". لم تُحذف ملفات /tmp أو سلة المحذوفات أو بيانات Flatpak أو كاش المستخدم.",
            log_output="\n".join(logs),
        )
