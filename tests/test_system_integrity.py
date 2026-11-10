#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import patch

from core.privilege import CommandResult
from modules.system_integrity import (
    SystemIntegrityModule,
    enabled_preset_names,
    parse_mkinitcpio_preset,
    parse_root_mount,
)


def test_parse_root_mount():
    result = parse_root_mount("/dev/sda2[/@] btrfs 1234-uuid rw,relatime,subvol=/@\n")
    assert result["source"] == "/dev/sda2[/@]"
    assert result["fstype"] == "btrfs"
    assert result["uuid"] == "1234-uuid"


def test_enabled_preset_names_are_parsed_without_shell_execution():
    assert enabled_preset_names("PRESETS=('default' 'fallback')\n") == {"default", "fallback"}
    assert enabled_preset_names("PRESETS=('default')\n") == {"default"}


def test_parse_mkinitcpio_preset_without_executing_shell():
    rows = parse_mkinitcpio_preset(
        'ALL_kver="/boot/vmlinuz-6.18-x86_64"\n'
        'default_image="/boot/initramfs-6.18-x86_64.img"\n'
        'fallback_image="$default_image"\n'
    )
    assert rows == [
        ("ALL_kver", "/boot/vmlinuz-6.18-x86_64"),
        ("default_image", "/boot/initramfs-6.18-x86_64.img"),
    ]


def test_scan_reports_fstab_problem_and_missing_initramfs_paths():
    def fake(args, timeout=30):
        if args[0] == "findmnt" and "--output" in args:
            return CommandResult(0, "/dev/sda2[/@] btrfs uuid-123 rw,subvol=/@\n", "")
        if args[0] == "findmnt" and "--verify" in args:
            return CommandResult(1, "parse error\n", "bad fstab")
        if args[0] == "grub-script-check":
            return CommandResult(0, "", "")
        if args[0] == "btrfs":
            return CommandResult(1, "", "permission denied")
        return CommandResult(1, "", "not found")

    with patch("modules.system_integrity.run_unprivileged", side_effect=fake), \
         patch("modules.system_integrity.shutil.which", return_value="/usr/bin/grub-script-check"), \
         patch.object(Path, "glob", return_value=[Path("/etc/mkinitcpio.d/linux.preset")]), \
         patch.object(Path, "read_text", return_value='PRESETS=("default")\ndefault_image="/boot/not-here.img"\nfallback_image="/boot/not-active.img"\n'), \
         patch.object(Path, "is_file", return_value=True), \
         patch.object(Path, "exists", return_value=False):
        result = SystemIntegrityModule().scan()

    assert any("fstab" in f.title for f in result.findings)
    assert any("مفقودة" in f.title for f in result.findings)


def test_apply_is_read_only():
    result = SystemIntegrityModule().apply()
    assert result.success
    assert "لم تُعدّل" in result.message
