from pathlib import Path

from modules.duplicate_finder import (
    DuplicateFinderModule,
    _find_duplicates,
    _hash_file,
    _walk_files,
)


def test_duplicate_scan_finds_exact_content_without_deleting(tmp_path):
    content = b"same-content-" * 150_000
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(content)
    second.write_bytes(content)

    groups = _find_duplicates([str(tmp_path)], min_size=1024)
    assert len(groups) == 1
    assert set(next(iter(groups.values()))) == {str(first), str(second)}

    result = DuplicateFinderModule().apply()
    assert result.success
    assert "لم يُحذف" in result.message


def test_scanner_does_not_follow_symlink_files_or_directories(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    secret = outside / "secret.bin"
    secret.write_bytes(b"x" * (1024 * 1024 + 1))
    (root / "linked-file.bin").symlink_to(secret)
    (root / "linked-dir").symlink_to(outside, target_is_directory=True)

    entries = _walk_files([str(root)], max_files=100)
    assert all(path != root / "linked-file.bin" for path, _, _ in entries)
    assert all(path != secret for path, _, _ in entries)
    assert _hash_file(root / "linked-file.bin") == ""


def test_hardlinks_are_not_reported_as_reclaimable_duplicates(tmp_path):
    original = tmp_path / "original.bin"
    original.write_bytes(b"hardlink-data-" * 100_000)
    linked = tmp_path / "same-inode.bin"
    linked.hardlink_to(original)

    groups = _find_duplicates([str(tmp_path)], min_size=1024)
    assert groups == {}


def test_walk_is_bounded_by_file_count(tmp_path):
    for index in range(8):
        (tmp_path / f"{index}.bin").write_bytes(b"a" * (1024 * 1024 + 1))

    entries = _walk_files([str(tmp_path)], max_files=3)
    assert len(entries) == 3


def test_scan_finding_is_not_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.duplicate_finder._walk_files", lambda *args, **kwargs: [])
    result = DuplicateFinderModule().scan()
    assert result.findings[0].actionable is False
    assert "لا توجد" in result.findings[0].title
