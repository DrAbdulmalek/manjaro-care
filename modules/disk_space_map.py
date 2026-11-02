#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only, bounded home-directory space inventory for the Disk Space Map."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from core.module_base import ApplyResult, MaintenanceModule, PreviewStep, RiskLevel, ScanFinding, ScanResult, Severity

_MAX_ENTRIES = 30_000
_MAX_DEPTH = 6
_DEFAULT_ROOT = Path.home()


@dataclass(frozen=True)
class SpaceEntry:
    name: str
    path: str
    size_bytes: int
    kind: str


@dataclass(frozen=True)
class SpaceMapResult:
    root: str
    entries: tuple[SpaceEntry, ...]
    scanned_entries: int
    skipped_entries: int
    truncated: bool


def build_space_map(root: str | Path = _DEFAULT_ROOT, max_entries: int = _MAX_ENTRIES,
                    max_depth: int = _MAX_DEPTH) -> SpaceMapResult:
    """Aggregate immediate children without following symlinks; never mutates files."""
    base = Path(root).expanduser()
    root_stat = base.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("The selected root must be a real directory, not a symlink")

    totals: dict[str, int] = {}
    kinds: dict[str, str] = {}
    scanned = skipped = 0
    truncated = False
    stack: list[tuple[Path, int, str]] = [(base, 0, "")]
    while stack:
        current, depth, top_name = stack.pop()
        try:
            with os.scandir(current) as iterator:
                for item in iterator:
                    if scanned >= max_entries:
                        truncated = True
                        stack.clear()
                        break
                    scanned += 1
                    try:
                        st = item.stat(follow_symlinks=False)
                        if stat.S_ISLNK(st.st_mode):
                            skipped += 1
                            continue
                        if depth == 0:
                            label = item.name
                            kinds[label] = "directory" if stat.S_ISDIR(st.st_mode) else "file"
                            totals.setdefault(label, 0)
                        else:
                            label = top_name
                        if stat.S_ISREG(st.st_mode):
                            totals[label] = totals.get(label, 0) + st.st_size
                        elif stat.S_ISDIR(st.st_mode) and depth < max_depth:
                            stack.append((Path(item.path), depth + 1, label))
                    except OSError:
                        skipped += 1
        except OSError:
            skipped += 1

    entries = tuple(
        SpaceEntry(name=n, path=str(base / n), size_bytes=size, kind=kinds.get(n, "other"))
        for n, size in sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    )
    return SpaceMapResult(str(base), entries, scanned, skipped, truncated)


def human_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


class DiskSpaceMapModule(MaintenanceModule):
    name = "خريطة مساحة القرص"
    slug = "disk_space_map"
    description = "تصنيف بصري لاستهلاك مجلد المنزل — قراءة فقط، دون حذف"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "drive-harddisk"
    has_custom_ui = True

    def scan(self) -> ScanResult:
        try:
            result = build_space_map()
        except (OSError, ValueError) as exc:
            return ScanResult(module_name=self.name, error=f"تعذّر فحص مساحة المنزل: {exc}")
        largest = result.entries[:5]
        detail = "\n".join(f"{e.name}: {human_size(e.size_bytes)}" for e in largest)
        if result.truncated:
            detail += "\nتوقف الفحص عند بلوغ الحد الوقائي؛ الأرقام جزئية."
        if result.skipped_entries:
            detail += f"\nعناصر متعذرة/مستبعدة: {result.skipped_entries}"
        return ScanResult(module_name=self.name, findings=[ScanFinding(
            title=f"تم تحليل {len(result.entries)} عنصراً مباشراً في {result.root}",
            detail=detail or "لا توجد بيانات قابلة للعرض.",
            severity=Severity.INFO, actionable=False, raw_value=result,
        )])

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="خريطة معلوماتية فقط؛ لا توجد أوامر تعديل أو حذف.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="خريطة المساحة للقراءة فقط؛ لم يتم تغيير أي ملف.")
