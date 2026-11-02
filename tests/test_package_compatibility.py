#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest.mock import patch

from core.privilege import CommandResult
from modules.package_compatibility import PackageCompatibilityModule


def test_scan_reports_foreign_packages_without_treating_them_as_errors():
    def fake(args, timeout=30):
        if args[:2] == ["pacman", "-Dk"]:
            return CommandResult(0, "checking dependencies...\n", "")
        if args[:2] == ["pacman", "-Qm"]:
            return CommandResult(0, "orthanc 1.13.0-1\n", "")
        return CommandResult(1, "", "not found")

    with patch("modules.package_compatibility.run_unprivileged", side_effect=fake), \
         patch("modules.package_compatibility.shutil.which", return_value=None):
        result = PackageCompatibilityModule().scan()

    foreign = next(f for f in result.findings if "أجنبية" in f.title)
    assert foreign.severity.value == "info"
    assert "orthanc" in foreign.detail


def test_scan_reports_rebuild_candidates_only_when_tool_says_so():
    def fake(args, timeout=30):
        if args[:2] == ["pacman", "-Dk"]:
            return CommandResult(0, "", "")
        if args[:2] == ["pacman", "-Qm"]:
            return CommandResult(0, "", "")
        if args == ["checkrebuild"]:
            return CommandResult(0, "orthanc: libprotobuf.so.36.0.0 not found\n", "")
        return CommandResult(1, "", "")

    with patch("modules.package_compatibility.run_unprivileged", side_effect=fake), \
         patch("modules.package_compatibility.shutil.which", return_value="/usr/bin/checkrebuild"):
        result = PackageCompatibilityModule().scan()

    assert any("checkrebuild أظهر" in f.title and "orthanc" in f.detail for f in result.findings)


def test_checkrebuild_no_rebuild_message_is_not_a_warning():
    def fake(args, timeout=30):
        if args[:2] == ["pacman", "-Dk"]:
            return CommandResult(0, "", "")
        if args[:2] == ["pacman", "-Qm"]:
            return CommandResult(0, "", "")
        if args == ["checkrebuild"]:
            return CommandResult(0, "No packages need to be rebuilt.\\n", "")
        return CommandResult(1, "", "")

    with patch("modules.package_compatibility.run_unprivileged", side_effect=fake), \\
         patch("modules.package_compatibility.shutil.which", return_value="/usr/bin/checkrebuild"):
        result = PackageCompatibilityModule().scan()

    assert any("لم يُرجع تحذيرات" in f.title for f in result.findings)
    assert not any("أظهر عناصر" in f.title for f in result.findings)


def test_apply_never_rebuilds_packages():
    result = PackageCompatibilityModule().apply()
    assert result.success
    assert "لم تُحدّث" in result.message
