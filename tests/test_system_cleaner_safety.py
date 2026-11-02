from unittest.mock import patch

from core.privilege import CommandResult
from modules import system_cleaner


def test_size_scanner_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    payload = outside / "payload.bin"
    payload.write_bytes(b"x" * 4096)
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "link-file").symlink_to(payload)

    assert system_cleaner._get_size(root) == 0
    assert system_cleaner._get_size(root / "link") == 0


def test_cleaner_only_marks_explicit_maintenance_targets_actionable(tmp_path, monkeypatch):
    cache = tmp_path / "pacman"
    cache.mkdir()
    (cache / "pkg.tar.zst").write_bytes(b"x" * 4096)
    trash = tmp_path / "Trash"
    trash.mkdir()
    (trash / "personal.txt").write_text("keep me", encoding="utf-8")
    flatpak = tmp_path / "flatpak"
    flatpak.mkdir()
    (flatpak / "app-data.db").write_bytes(b"private")

    monkeypatch.setattr(system_cleaner, "_CLEAN_TARGETS", {
        "pacman_cache": (str(cache), "pacman cache", "paccache"),
        "trash": (str(trash), "Trash", "review"),
        "flatpak_app_data": (str(flatpak), "Flatpak data", "review"),
    })
    result = system_cleaner.SystemCleanerModule().scan()
    assert next(f for f in result.findings if "pacman cache" in f.title).actionable
    assert not next(f for f in result.findings if "Trash" in f.title).actionable
    assert not next(f for f in result.findings if "Flatpak data" in f.title).actionable


def test_apply_runs_only_allowlisted_maintenance_commands():
    calls = []

    def fake_run(args, timeout=300):
        calls.append(args)
        return CommandResult(0, "ok", "")

    with patch("modules.system_cleaner.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), patch(
        "modules.system_cleaner.run_privileged", side_effect=fake_run
    ):
        result = system_cleaner.SystemCleanerModule().apply()

    assert result.success
    assert calls == [
        ["paccache", "-rk2"],
        ["journalctl", "--vacuum-time=7d"],
    ]


def test_preview_never_contains_recursive_delete_commands():
    with patch("modules.system_cleaner.shutil.which", return_value="/usr/bin/tool"):
        steps = system_cleaner.SystemCleanerModule().preview()
    commands = [step.command or "" for step in steps]
    assert all("rm -rf" not in command for command in commands)
    assert all("find " not in command or "-delete" not in command for command in commands)
    assert any("للمراجعة فقط" in step.description for step in steps)
