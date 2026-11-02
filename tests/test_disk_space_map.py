from __future__ import annotations

from pathlib import Path

import pytest

from modules.disk_space_map import build_space_map


def test_aggregates_regular_files_and_directories(tmp_path: Path):
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "a.bin").write_bytes(b"a" * 100)
    (tmp_path / "top.bin").write_bytes(b"b" * 25)
    result = build_space_map(tmp_path)
    sizes = {entry.name: entry.size_bytes for entry in result.entries}
    assert sizes["Docs"] == 100
    assert sizes["top.bin"] == 25


def test_does_not_follow_symlink_directory(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.bin").write_bytes(b"x" * 1000)
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    result = build_space_map(root)
    assert all(entry.size_bytes == 0 for entry in result.entries)


def test_rejects_symlink_root(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        build_space_map(link)


def test_entry_limit_is_bounded(tmp_path: Path):
    for index in range(20):
        (tmp_path / f"f{index}").write_text("x")
    result = build_space_map(tmp_path, max_entries=5)
    assert result.scanned_entries == 5
    assert result.truncated is True
