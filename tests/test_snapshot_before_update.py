#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_snapshot_before_update.py — اختبارات وحدة لقطة-قبل-التحديث.

لا أوامر حقيقية: تحليل المخرجات نقي، وكل subprocess وهمي.
الحالات: اكتشاف الأداة، غياب الأداة (غير قابل للتطبيق بلا خطأ)،
أوامر المعاينة الحرفية، التنفيذ عبر pkexec، وضع dry-run، ومساحة القرص.
"""
from __future__ import annotations

from unittest.mock import patch

from core.module_base import Severity
from core.privilege import CommandResult
from core.runtime import set_dry_run
from modules import snapshot_before_update as sbu
from modules.snapshot_before_update import (
    SnapshotBeforeUpdateModule,
    detect_tool,
    parse_snapper_list,
    parse_timeshift_list,
)

SNAPPER_OUTPUT = """\
    # | Type   | Pre # | Date                     | User | Cleanup | Description      | Userdata
-----+--------+-------+--------------------------+------+---------+------------------+---------
   0 | single |       |                          | root |         | current          |
   1 | single |       | Tue Jan  2 12:00:00 2026 | root | number  | manjaro-care pre-update |
   2 | pre    |       | Wed Jan  3 09:30:00 2026 | root | number  | before grub fix  |
"""

TIMESHIFT_OUTPUT = """\
Mode : BTRFS

0  >  2026-01-02 12:00:00  4567 MB  O  /dev/sda2  -- manjaro-care pre-update
1     2026-01-01 10:00:00  4400 MB  O  /dev/sda2  -- weekly
"""


class TestParsers:
    def test_parse_snapper_list(self):
        snaps = parse_snapper_list(SNAPPER_OUTPUT)
        assert [s["num"] for s in snaps] == ["0", "1", "2"]
        assert snaps[1]["desc"] == "manjaro-care pre-update"
        assert "Jan  2" in snaps[1]["date"]

    def test_parse_snapper_list_empty(self):
        assert parse_snapper_list("") == []

    def test_parse_timeshift_list(self):
        snaps = parse_timeshift_list(TIMESHIFT_OUTPUT)
        assert [s["num"] for s in snaps] == ["0", "1"]
        assert snaps[0]["date"] == "2026-01-02 12:00:00"
        assert snaps[0]["desc"] == "manjaro-care pre-update"
        assert snaps[1]["desc"] == "weekly"

    def test_parse_timeshift_garbage_ignored(self):
        assert parse_timeshift_list("Mode : BTRFS\n\nno data here") == []


class TestDetectTool:
    def test_timeshift_preferred(self):
        with patch.object(sbu.shutil, "which", side_effect=lambda b: b == "timeshift"):
            assert detect_tool() == "timeshift"

    def test_snapper_fallback(self):
        with patch.object(sbu.shutil, "which", side_effect=lambda b: b == "snapper"):
            assert detect_tool() == "snapper"

    def test_none(self):
        with patch.object(sbu.shutil, "which", return_value=None):
            assert detect_tool() is None


class TestScan:
    def setup_method(self):
        self.module = SnapshotBeforeUpdateModule()

    def test_no_tool_is_not_applicable_not_error(self):
        with patch.object(sbu, "detect_tool", return_value=None), \
             patch.object(sbu.shutil, "which", return_value=None):
            result = self.module.scan()
        assert result.error is None  # ليست حالة خطأ
        assert "لا أداة لقطات مثبتة" in result.findings[0].title

    def test_scan_lists_snapshots_and_space(self):
        with patch.object(sbu, "detect_tool", return_value="snapper"), \
             patch.object(sbu.shutil, "which", return_value="/usr/bin/snapper"), \
             patch.object(sbu, "list_snapshots",
                          return_value=(parse_snapper_list(SNAPPER_OUTPUT), None)), \
             patch.object(sbu, "free_bytes_on_root", return_value=50 * 1024 ** 3):
            result = self.module.scan()
        titles = [f.title for f in result.findings]
        assert any("3 لقطة" in t for t in titles)
        assert any("المساحة" in t for t in titles)

    def test_scan_low_space_warns(self):
        with patch.object(sbu, "detect_tool", return_value="snapper"), \
             patch.object(sbu.shutil, "which", return_value="/usr/bin/snapper"), \
             patch.object(sbu, "list_snapshots", return_value=([], None)), \
             patch.object(sbu, "free_bytes_on_root", return_value=512 * 1024 ** 2):
            result = self.module.scan()
        assert result.worst_severity == Severity.WARNING
        assert any("منخفضة" in f.title for f in result.findings)


class TestPreviewAndApply:
    def setup_method(self):
        self.module = SnapshotBeforeUpdateModule()

    def test_preview_snapper_command_literal(self):
        with patch.object(sbu, "detect_tool", return_value="snapper"):
            steps = self.module.preview()
        assert steps[0].command == 'snapper -c root create --description "manjaro-care pre-update"'

    def test_preview_timeshift_command_literal(self):
        with patch.object(sbu, "detect_tool", return_value="timeshift"):
            steps = self.module.preview()
        assert steps[0].command == 'timeshift --create --comments "manjaro-care pre-update"'

    def test_apply_snapper_via_pkexec_argv(self):
        with patch.object(sbu, "detect_tool", return_value="snapper"), \
             patch.object(sbu, "run_privileged",
                          return_value=CommandResult(0, "created", "")) as m_run:
            result = self.module.apply()
        m_run.assert_called_once()
        called = m_run.call_args.args[0]
        assert called == ["snapper", "-c", "root", "create",
                          "--description", "manjaro-care pre-update"]
        assert result.success

    def test_apply_failure_honest_no_update_claim(self):
        with patch.object(sbu, "detect_tool", return_value="snapper"), \
             patch.object(sbu, "run_privileged",
                          return_value=CommandResult(1, "", "snap error")):
            result = self.module.apply()
        assert not result.success
        assert "لم يُنفَّذ أي تحديث" in result.message

    def test_apply_dry_run_creates_nothing(self):
        set_dry_run(True)
        try:
            with patch.object(sbu, "detect_tool", return_value="snapper"), \
                 patch.object(sbu, "run_privileged") as m_run:
                result = self.module.apply()
        finally:
            set_dry_run(False)
        m_run.assert_not_called()
        assert "[DRY-RUN]" in result.message
