#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بحث آمن عن الملفات المكررة؛ لا يحذف ولا ينقل أي ملف."""
from __future__ import annotations

import hashlib
import os
import stat
from collections import defaultdict
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

log = get_logger("duplicate_finder")

_MIN_SIZE = 1024 * 1024
_MAX_FILES = 200_000
_MAX_GROUPS = 200
_BLOCK_SIZE = 1024 * 1024
_SKIP_DIRS = {
    ".cache", ".git", ".hg", ".svn", "__pycache__", ".venv",
    "node_modules", ".local/share/trash", ".trash",
}


def _hash_file(path: Path, block_size: int = _BLOCK_SIZE) -> str:
    """SHA-256 using O_NOFOLLOW and inode verification to avoid symlink races."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open(path, flags)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            return ""
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = None
            while chunk := stream.read(block_size):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            return ""
        return digest.hexdigest()
    except (OSError, ValueError):
        return ""
    finally:
        if fd is not None:
            os.close(fd)


def _walk_files(paths: list[str], max_files: int = _MAX_FILES) -> list[tuple[Path, int, tuple[int, int]]]:
    """Iterative lstat-based walk. Never follows symlinks; bounded by max_files."""
    found: list[tuple[Path, int, tuple[int, int]]] = []
    visited_dirs: set[tuple[int, int]] = set()
    stack: list[Path] = []
    for raw in paths:
        base = Path(raw).expanduser()
        try:
            st = base.lstat()
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode):
            stack.append(base)

    while stack and len(found) < max_files:
        current = stack.pop()
        try:
            dst = current.lstat()
            if not stat.S_ISDIR(dst.st_mode):
                continue
            identity = (dst.st_dev, dst.st_ino)
            if identity in visited_dirs:
                continue
            visited_dirs.add(identity)
            with os.scandir(current) as entries:
                for entry in entries:
                    if len(found) >= max_files:
                        break
                    try:
                        est = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISLNK(est.st_mode):
                        continue
                    child = Path(entry.path)
                    if stat.S_ISDIR(est.st_mode):
                        if entry.name.startswith(".") or entry.name.lower() in _SKIP_DIRS:
                            continue
                        stack.append(child)
                    elif stat.S_ISREG(est.st_mode) and est.st_size >= _MIN_SIZE:
                        found.append((child, est.st_size, (est.st_dev, est.st_ino)))
        except OSError:
            continue
    return found


def _find_duplicates(
    paths: list[str],
    min_size: int = _MIN_SIZE,
    max_files: int = _MAX_FILES,
) -> dict[str, list[str]]:
    """Group exact byte-identical files; hardlinks and symlinks are not counted."""
    by_size: dict[int, list[tuple[Path, tuple[int, int]]]] = defaultdict(list)
    for path, size, inode in _walk_files(paths, max_files=max_files):
        if size >= min_size:
            by_size[size].append((path, inode))

    duplicates: dict[str, list[str]] = {}
    seen_inodes: set[tuple[int, int]] = set()
    for _size, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        hashes: dict[str, list[str]] = defaultdict(list)
        for path, inode in candidates:
            if inode in seen_inodes:
                continue
            digest = _hash_file(path)
            if digest:
                hashes[digest].append(str(path))
                seen_inodes.add(inode)
        for digest, matches in hashes.items():
            if len(matches) > 1:
                duplicates[digest] = matches
                if len(duplicates) >= _MAX_GROUPS:
                    return duplicates
    return duplicates


class DuplicateFinderModule(MaintenanceModule):
    name = "البحث عن الملفات المكررة"
    slug = "duplicate_finder"
    description = "يعثر على النسخ المتطابقة في مجلدات المستخدم؛ الفحص للقراءة فقط ولا يحذف الملفات"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "edit-find"

    def scan(self) -> ScanResult:
        search_paths = [
            "~/Downloads", "~/Documents", "~/Pictures",
            "~/Music", "~/Videos", "~/Desktop",
        ]
        candidates = _walk_files(search_paths)
        by_size: dict[int, list[tuple[Path, tuple[int, int]]]] = defaultdict(list)
        for path, size, inode in candidates:
            by_size[size].append((path, inode))

        duplicates: dict[str, list[str]] = {}
        wasted_bytes = 0
        seen_inodes: set[tuple[int, int]] = set()
        for _size, group in by_size.items():
            if len(group) < 2:
                continue
            hashes: dict[str, list[str]] = defaultdict(list)
            for path, inode in group:
                if inode in seen_inodes:
                    continue
                digest = _hash_file(path)
                if digest:
                    hashes[digest].append(str(path))
                    seen_inodes.add(inode)
            for digest, matches in hashes.items():
                if len(matches) > 1:
                    duplicates[digest] = matches
                    wasted_bytes += _size * (len(matches) - 1)
                    if len(duplicates) >= _MAX_GROUPS:
                        break
            if len(duplicates) >= _MAX_GROUPS:
                break

        duplicate_count = sum(len(files) - 1 for files in duplicates.values())
        truncated = len(candidates) >= _MAX_FILES
        if duplicate_count:
            lines = []
            for index, files in enumerate(duplicates.values(), start=1):
                lines.append(f"المجموعة {index}:")
                lines.extend(f"  {item}" for item in files[:8])
                if len(files) > 8:
                    lines.append(f"  ... و{len(files) - 8} نسخ أخرى")
            detail = (
                f"المجموعات: {len(duplicates)} | النسخ الزائدة: {duplicate_count} | "
                f"المساحة النظرية: {self._human_size(wasted_bytes)}\n"
                "هذه ملفات شخصية محتملة؛ راجع كل نسخة يدوياً قبل أي نقل أو حذف.\n"
                + "\n".join(lines)
            )
            severity = Severity.INFO
        else:
            detail = "لم يُعثر على ملفات متطابقة ضمن المسارات والحدود المفحوصة."
            severity = Severity.OK
        if truncated:
            detail += f"\nتنبيه: بلغ الفحص حد { _MAX_FILES } ملف؛ النتائج جزئية."

        finding = ScanFinding(
            title=(
                f"{duplicate_count} نسخة مكررة ضمن {len(duplicates)} مجموعات "
                f"({self._human_size(wasted_bytes)} مساحة نظرية)"
                if duplicate_count else "لا توجد ملفات مكررة مؤكدة"
            ),
            detail=detail,
            severity=severity,
            actionable=False,
            raw_value={"groups": duplicates, "truncated": truncated},
        )
        return ScanResult(module_name=self.name, findings=[finding])

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description=(
                "عرض معلومات فقط. لا توجد عملية حذف أو نقل تلقائي للملفات الشخصية. "
                "افتح المسارات وراجع كل نسخة بنفسك."
            )
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="وحدة البحث عن المكررات للقراءة فقط؛ لم يُحذف أو يُنقل أو يُعدّل أي ملف.",
        )

    @staticmethod
    def _human_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024:
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} PB"
