from __future__ import annotations

from pathlib import Path

from core.privilege import CommandResult
from modules import firmware_overview


def test_uefi_report_uses_only_read_only_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(
        firmware_overview.Path,
        "is_dir",
        lambda self: str(self) == "/sys/firmware/efi",
    )
    monkeypatch.setattr(firmware_overview.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(args, timeout=30):
        calls.append(args)
        return CommandResult(0, "sample output", "")

    monkeypatch.setattr(firmware_overview, "run_unprivileged", fake_run)
    result = firmware_overview.collect_firmware_report()

    assert result["is_uefi"] is True
    assert "وضع الإقلاع الحالي: UEFI" in result["report"]
    assert calls == [
        ["uname", "-r"],
        ["bootctl", "status", "--no-pager"],
        ["efibootmgr", "-v"],
        ["mokutil", "--sb-state"],
    ]
    assert all(args[0] not in {"efibootmgr-write", "grub-mkconfig", "systemctl"} for args in calls)


def test_legacy_report_does_not_call_efi_tools(monkeypatch):
    calls = []
    monkeypatch.setattr(firmware_overview.Path, "is_dir", lambda self: False)
    monkeypatch.setattr(firmware_overview.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        firmware_overview,
        "run_unprivileged",
        lambda args, timeout=30: (
            calls.append(args) or CommandResult(0, "sample", "")
        ),
    )
    result = firmware_overview.collect_firmware_report()
    assert result["is_uefi"] is False
    assert calls == [["uname", "-r"]]
    assert "لم تُجرَ محاولة لتعديل نمط الإقلاع" in result["report"]
