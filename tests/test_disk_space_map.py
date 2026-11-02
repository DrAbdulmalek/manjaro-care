from __future__ import annotations

from pathlib import Path

import pytest

from modules.disk_space_map import SpaceEntry, build_space_map


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

 
 
def test_depth_limit_is_reported_as_partial(tmp_path: Path):
    current = tmp_path
    for index in range(4):
        current = current / f"level{index}"
        current.mkdir()
    (current / "payload.bin").write_bytes(b"x" * 50)
    result = build_space_map(tmp_path, max_depth=1)
    assert result.truncated is True


def test_treemap_tiles_partition_the_requested_area():
    from PyQt5.QtCore import QRectF
    from gui.disk_space_map_dialog import _treemap_rectangles

    entries = [
        SpaceEntry("large", "/large", 900, "file"),
        SpaceEntry("small", "/small", 100, "file"),
    ]
    bounds = QRectF(0, 0, 100, 50)
    tiles = _treemap_rectangles(entries, bounds)
    assert len(tiles) == 2
    assert sum(rect.width() * rect.height() for _, rect in tiles) == pytest.approx(5000)
    areas = [rect.width() * rect.height() for _, rect in tiles]
    assert areas[0] / areas[1] == pytest.approx(9)
