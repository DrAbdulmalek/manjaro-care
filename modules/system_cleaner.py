#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/system_cleaner.py — التنظيف العميق للنظام (CCleaner for Linux)."""
from __future__ import annotations
import shutil
import os
from pathlib import Path
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("system_cleaner")

# مسارات التنظيف
_CLEAN_TARGETS = {
    "pacman_cache": ("/var/cache/pacman/pkg", True, "ذاكرة pacman المؤقتة"),
    "yay_cache": ("~/.cache/yay", False, "بقايا بناء AUR (yay)"),
    "paru_cache": ("~/.cache/paru", False, "بقايا بناء AUR (paru)"),
    "tmp_files": ("/tmp", True, "ملفات /tmp القديمة"),
    "trash": ("~/.local/share/Trash", False, "سلة المحذوفات"),
    "thumbnail_cache": ("~/.cache/thumbnails", False, "صور مصغرة قديمة"),
    "journal_old": ("journal", True, "سجلات systemd القديمة"),
    "flatpak_cache": ("~/.var/app", False, "بيانات Flatpak القديمة"),
    "pip_cache": ("~/.cache/pip", False, "ذاكرة pip"),
}


def _expand(path: str) -> Path:
    if path.startswith("~"):
        home = os.path.expanduser("~")
        path = path.replace("~", home, 1)
    return Path(path)


def _get_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size
        for entry in os.scandir(path):
            if entry.is_symlink():
                continue
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += _get_size(Path(entry.path))
    except PermissionError:
        pass
    return total


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class SystemCleanerModule(MaintenanceModule):
    name = "التنظيف العميق (System Cleaner)"
    slug = "system_cleaner"
    description = "تنظيف الكاش، الملفات المؤقتة، بقايا AUR، والسجلات القديمة"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "edit-clear-all"

    def scan(self):
        findings = []
        total_size = 0

        for key, (path, needs_root, desc) in _CLEAN_TARGETS.items():
            p = _expand(path)
            size = _get_size(p)
            if size > 0:
                findings.append(ScanFinding(
                    title=f"{desc}: {_human_size(size)}",
                    detail=f"المسار: {p}",
                    severity=Severity.WARNING if size > 500 * 1024 * 1024 else Severity.INFO,
                    actionable=True,
                    raw_value={"path": str(p), "size": size, "needs_root": needs_root},
                ))
                total_size += size

        if not findings:
            findings.append(ScanFinding(
                title="النظام نظيف ✨",
                detail="لم يُعثر على ملفات قابلة للحذف.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.insert(0, ScanFinding(
                title=f"إجمالي قابل للتحرير: {_human_size(total_size)}",
                detail="يمكن تنظيف هذه الملفات لاسترداد المساحة.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        steps = []
        for key, (path, needs_root, desc) in _CLEAN_TARGETS.items():
            p = _expand(path)
            if p.exists():
                if key == "journal_old":
                    steps.append(PreviewStep(
                        description=f"تقليص سجلات journal إلى 7 أيام",
                        command="journalctl --vacuum-time=7d",
                    ))
                elif needs_root:
                    steps.append(PreviewStep(
                        description=f"حذف {desc}",
                        command=f"rm -rf {p}/*",
                    ))
                else:
                    steps.append(PreviewStep(
                        description=f"حذف {desc}",
                        command=f"rm -rf {p}/*",
                    ))
        return steps or [PreviewStep(description="لا شيء للتنظيف.")]

    def apply(self):
        logs = []
        success = True

        for key, (path, needs_root, desc) in _CLEAN_TARGETS.items():
            p = _expand(path)
            if not p.exists():
                continue

            if key == "journal_old":
                r = run_privileged(["journalctl", "--vacuum-time=7d"])
                logs.append(r.stdout + r.stderr)
                if not r.ok:
                    success = False
            elif key in ("pacman_cache", "tmp_files"):
                # نحذف فقط الملفات القديمة جداً في /tmp (>3 أيام) أو نستخدم paccache
                if key == "pacman_cache" and shutil.which("paccache"):
                    r = run_privileged(["paccache", "-rk2"])
                    logs.append(r.stdout + r.stderr)
                else:
                    r = run_privileged(["bash", "-c", f"find {p} -type f -atime +3 -delete 2>/dev/null; true"])
                if not r.ok:
                    success = False
            else:
                # مسارات المستخدم
                if needs_root:
                    r = run_privileged(["bash", "-c", f"rm -rf {p}/* 2>/dev/null; true"])
                else:
                    r = run_unprivileged(["bash", "-c", f"rm -rf {p}/* 2>/dev/null; true"])
                logs.append(r.stdout + r.stderr)

        return ApplyResult(
            success=success,
            message="تم التنظيف العميق" if success else "فشل جزئي",
            log_output="\n".join(logs),
        )
