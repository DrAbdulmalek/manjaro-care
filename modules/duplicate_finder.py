#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/duplicate_finder.py — البحث عن الملفات المكررة."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from collections import defaultdict
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("duplicate_finder")


def _hash_file(path: Path, block_size=65536) -> str:
    hasher = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(block_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""


def _find_duplicates(paths: list[str], min_size: int = 1024) -> dict[str, list[str]]:
    """يجد الملفات المكررة حسب الـ hash."""
    size_map = defaultdict(list)

    for base in paths:
        base_path = Path(base).expanduser()
        if not base_path.exists():
            continue
        for root, dirs, files in os.walk(base_path):
            # تجاهل المسارات المخفية
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                fpath = Path(root) / fname
                try:
                    fsize = fpath.stat().st_size
                    if fsize < min_size:
                        continue
                    size_map[fsize].append(str(fpath))
                except (OSError, PermissionError):
                    continue

    # الآن نحسب الـ hash للملفات التي لها نفس الحجم
    duplicates = defaultdict(list)
    for fsize, file_list in size_map.items():
        if len(file_list) < 2:
            continue
        hashes = defaultdict(list)
        for fpath in file_list:
            h = _hash_file(Path(fpath))
            if h:
                hashes[h].append(fpath)
        for h, files in hashes.items():
            if len(files) >= 2:
                duplicates[h] = files

    return dict(duplicates)


class DuplicateFinderModule(MaintenanceModule):
    name = "البحث عن الملفات المكررة 📑"
    slug = "duplicate_finder"
    description = "يجد الملفات المكررة في مجلدات المستخدم لتحرير المساحة"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "edit-find"

    def scan(self):
        findings = []
        # نبحث في المسارات الشائعة
        search_paths = [
            "~/Downloads",
            "~/Documents",
            "~/Pictures",
            "~/Music",
            "~/Videos",
            "~/.cache",
        ]

        dups = _find_duplicates(search_paths, min_size=1024)
        total_dups = 0
        total_size = 0

        for h, files in dups.items():
            # نحسب الحجم المهدرة (الملفات الزائدة)
            try:
                fsize = Path(files[0]).stat().st_size
                wasted = fsize * (len(files) - 1)
                total_size += wasted
                total_dups += len(files) - 1
            except OSError:
                continue

        if total_dups > 0:
            findings.append(ScanFinding(
                title=f"{total_dups} ملف مكرر ({self._human_size(total_size)} قابلة للتحرير)",
                detail=f"تم العثور على {len(dups)} مجموعات مكررة في مجلدات المستخدم.",
                severity=Severity.INFO,
                actionable=True,
                raw_value=dups,
            ))
        else:
            findings.append(ScanFinding(
                title="لا ملفات مكررة",
                detail="لم يُعثر على تكرارات كبيرة.",
                severity=Severity.OK,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        return [PreviewStep(description="حذف النسخ الزائدة من الملفات المكررة")]

    def apply(self):
        result = self.scan()
        dups = result.findings[0].raw_value if result.findings and result.findings[0].raw_value else {}
        deleted = 0
        freed = 0
        logs = []

        for h, files in dups.items():
            # نحتفظ بالأقدم ونحذف الباقي
            sorted_files = sorted(files, key=lambda p: Path(p).stat().st_mtime)
            for to_delete in sorted_files[1:]:
                try:
                    p = Path(to_delete)
                    size = p.stat().st_size
                    p.unlink()
                    deleted += 1
                    freed += size
                    logs.append(f"🗑️ {to_delete}")
                except Exception as exc:
                    logs.append(f"❌ فشل حذف {to_delete}: {exc}")

        return ApplyResult(
            success=True,
            message=f"تم حذف {deleted} ملف مكرر ({self._human_size(freed)} محررة)",
            log_output="\n".join(logs),
        )

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
