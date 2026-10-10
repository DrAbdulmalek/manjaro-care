#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_snapper_cleanup.py — اختبارات وحدة تنظيف لقطات snapper.

الحالة الحرجة: compute_deletions يحمي اللقطة 0 ("current") ولا يحذف
أبداً أكثر من المسموح، والمعاينة تعرض المعرّفات بالتحديد، وdry-run
يمنع الحذف كلياً.
"""
from __future__ import annotations

from unittest.mock import patch

from core.privilege import CommandResult
from core.runtime import set_dry_run
from modules import snapper_cleanup as sc
from modules.snapper_cleanup import (
    SnapperCleanupModule,
    compute_deletions,
    read_keep_count,
    write_keep_count,
)


class TestComputeDeletions:
    def test_keeps_last_n(self):
        nums = [str(i) for i in range(1, 8)]  # 1..7
        assert compute_deletions(nums, keep=5) == ["1", "2"]

    def test_never_deletes_zero_current(self):
        """لقطة 0 (current) مقدسة — حتى لو كانت الأقدم."""
        nums = ["0", "1", "2", "3"]
        assert "0" not in compute_deletions(nums, keep=1)

    def test_no_deletions_when_within_keep(self):
        assert compute_deletions(["1", "2", "3"], keep=5) == []

    def test_ignores_non_numeric(self):
        assert compute_deletions(["a", "b", "1", "2", "3"], keep=1) == ["1", "2"]

    def test_numeric_order_independent(self):
        assert compute_deletions(["9", "3", "5"], keep=1) == ["3", "5"]

    def test_keep_minimum_one(self):
        assert compute_deletions(["1", "2"], keep=0) == ["1"]  # 0→يُعالج كـ1

    def test_empty_input(self):
        assert compute_deletions([], keep=3) == []


class TestKeepCountConfig:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "KEEP_FILE", tmp_path / "keep_n")
        monkeypatch.setattr(sc, "CONFIG_DIR", tmp_path)
        assert write_keep_count(7) is True
        assert read_keep_count() == 7

    def test_invalid_file_falls_back_to_default(self, tmp_path, monkeypatch):
        bad = tmp_path / "keep_n"
        bad.write_text("not-a-number")
        monkeypatch.setattr(sc, "KEEP_FILE", bad)
        assert read_keep_count() == sc.DEFAULT_KEEP

    def test_rejects_less_than_one(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CONFIG_DIR", tmp_path)
        assert write_keep_count(0) is False


class TestApply:
    def setup_method(self):
        self.module = SnapperCleanupModule()

    def _patch_list(self, nums):
        snaps = [{"num": n, "date": "d", "desc": "x"} for n in nums]
        return patch("modules.snapshot_before_update.list_snapshots",
                     return_value=(snaps, None))

    def test_apply_deletes_exact_ids_only(self):
        with patch.object(sc.shutil, "which", return_value="/usr/bin/snapper"), \
             self._patch_list(["0", "1", "2", "3", "4", "5", "6", "7"]), \
             patch.object(sc, "read_keep_count", return_value=5), \
             patch.object(sc, "run_privileged",
                          return_value=CommandResult(0, "ok", "")) as m_run:
            result = self.module.apply()
        deleted = [c.args[0][-1] for c in m_run.call_args_list]
        assert deleted == ["1", "2"]  # آخر 5 = 3..7 + 0 محمية
        assert result.success

    def test_apply_nothing_when_within_keep(self):
        with patch.object(sc.shutil, "which", return_value="/usr/bin/snapper"), \
             self._patch_list(["0", "1", "2"]), \
             patch.object(sc, "read_keep_count", return_value=10), \
             patch.object(sc, "run_privileged") as m_run:
            result = self.module.apply()
        m_run.assert_not_called()
        assert result.success and "لا لقطات زائدة" in result.message

    def test_apply_partial_failure_honest(self):
        results = [CommandResult(0, "", ""), CommandResult(1, "", "busy")]
        with patch.object(sc.shutil, "which", return_value="/usr/bin/snapper"), \
             self._patch_list(["0", "1", "2", "3"]), \
             patch.object(sc, "read_keep_count", return_value=1), \
             patch.object(sc, "run_privileged", side_effect=results):
            result = self.module.apply()
        assert not result.success
        assert "فشل حذف" in result.message and "#2" in result.message

    def test_apply_dry_run_deletes_nothing(self):
        set_dry_run(True)
        try:
            with patch.object(sc.shutil, "which", return_value="/usr/bin/snapper"), \
                 self._patch_list(["0", "1", "2", "3"]), \
                 patch.object(sc, "read_keep_count", return_value=1), \
                 patch.object(sc, "run_privileged") as m_run:
                result = self.module.apply()
        finally:
            set_dry_run(False)
        m_run.assert_not_called()
        assert "[DRY-RUN]" in result.message

    def test_preview_lists_exact_ids(self):
        with patch.object(sc.shutil, "which", return_value="/usr/bin/snapper"), \
             self._patch_list(["0", "1", "2", "3"]), \
             patch.object(sc, "read_keep_count", return_value=1):
            steps = self.module.preview()
        text = " ".join(s.description for s in steps)
        assert "#1" in text and "#2" in text  # المعرّفات بالتحديد ظاهرة
        commands = [s.command for s in steps if s.command]
        assert commands == ["snapper -c root delete 1", "snapper -c root delete 2"]
