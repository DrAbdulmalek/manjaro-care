#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_archive_extract.py — اختبارات الاستخراج الآمن للأرشيفات.

تغطي منطق التخطيط (نوع الأرشيف/المجلد الهدف/تخطي الموجود)، بناء الأوامر
argv، وسلوك التنفيذ: الحذف عند النجاح والتنظيف عند الفشل واحترام dry-run.
لا يُنفَّذ أي أمر حقيقي — كل subprocess وهمي.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch



class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.pid = 12345

    def poll(self):
        return self.returncode

    def communicate(self):
        return self._stdout, self._stderr

    def wait(self, timeout=None):
        return self.returncode

from core.runtime import set_dry_run
from modules.archive_extract import (
    ExtractionPlan,
    archive_kind,
    build_extract_cmd,
    plan_extraction,
    run_extraction,
)


class TestKindAndCmds:
    def test_zip_rar_other(self, tmp_path):
        assert archive_kind(tmp_path / "a.ZIP") == "zip"
        assert archive_kind(tmp_path / "b.rar") == "rar"
        assert archive_kind(tmp_path / "c.7z") == "other"
        assert archive_kind(tmp_path / "d.tar.gz") == "other"

    def test_build_cmds_shape(self, tmp_path):
        a, t = tmp_path / "x.zip", tmp_path / "x"
        tool, cmd = build_extract_cmd(a, t)
        assert tool == "unzip"
        assert cmd == ["unzip", "-o", str(a), "-d", str(t)]

        a2 = tmp_path / "y.rar"
        tool2, cmd2 = build_extract_cmd(a2, tmp_path / "y")
        assert tool2 == "unrar" and cmd2[0] == "unrar" and "-o+" in cmd2

        a3 = tmp_path / "z.7z"
        tool3, cmd3 = build_extract_cmd(a3, tmp_path / "z")
        assert tool3 == "7z" and cmd3[0] == "7z"


class TestPlanning:
    def test_plan_names_and_skip_flag(self, tmp_path):
        a = tmp_path / "book.tar.gz"
        a.write_bytes(b"x")
        plan = plan_extraction(a)
        assert isinstance(plan, ExtractionPlan)
        # stem يقطع أول امتداد فقط — السلوك المقبول من safe_extract.sh
        assert plan.target_dir == tmp_path / "book.tar"
        assert plan.skip_existing is False

    def test_plan_skips_when_target_exists(self, tmp_path):
        a = tmp_path / "book.zip"
        a.write_bytes(b"x")
        (tmp_path / "book").mkdir()
        assert plan_extraction(a).skip_existing is True


class TestRunExtraction:
    def _plan(self, tmp_path: Path) -> ExtractionPlan:
        a = tmp_path / "f.zip"
        a.write_bytes(b"PK")
        return plan_extraction(a)

    def test_dry_run_never_executes(self, tmp_path):
        set_dry_run(True)
        plan = self._plan(tmp_path)
        with patch("modules.archive_extract.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = AssertionError("تنفيذ حقيقي أثناء dry-run!")
            out = run_extraction(plan)
        mock_popen.assert_not_called()
        assert out.dry_run and out.success
        assert "[DRY-RUN]" in out.message
        assert plan.archive.exists()  # لا حذف أيضاً

    def test_success_deletes_archive(self, tmp_path):
        plan = self._plan(tmp_path)
        with patch("modules.archive_extract.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _FakeProc(0, "done", "")
            out = run_extraction(plan, delete_on_success=True)
        assert out.success and out.deleted_archive
        assert not plan.archive.exists()

    def test_success_keeps_archive_when_requested(self, tmp_path):
        plan = self._plan(tmp_path)
        with patch("modules.archive_extract.subprocess.run") as mock_run:
            mock_popen.return_value = _FakeProc(0, "", "")
            out = run_extraction(plan, delete_on_success=False)
        assert out.success and not out.deleted_archive
        assert plan.archive.exists()

    def test_failure_cleans_partial_and_keeps_archive(self, tmp_path):
        plan = self._plan(tmp_path)
        # استخراج جزئي: مجلد الهدف أنشأ ملفاً ثم فشل الأمر
        class FakeFailProc(_FakeProc):
            def __init__(self):
                super().__init__(2, "", "error")
                plan.target_dir.mkdir(exist_ok=True)
                (plan.target_dir / "partial.bin").write_bytes(b"p")

        with patch("modules.archive_extract.subprocess.Popen", return_value=FakeFailProc()):
            out = run_extraction(plan)
        assert not out.success and out.cleaned_partial_dir
        assert not plan.target_dir.exists()   # نُظّف الجزئي
        assert plan.archive.exists()          # الأرشيف محفوظ

    def test_missing_tool_reported_without_crash(self, tmp_path):
        plan = self._plan(tmp_path)
        with patch("modules.archive_extract.subprocess.Popen",
                   side_effect=FileNotFoundError("no 7z")):
            out = run_extraction(plan)
        assert not out.success and "غير مثبتة" in out.message
        assert plan.archive.exists()
