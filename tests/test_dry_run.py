#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_dry_run.py — اختبارات وضع المعاينة الجافة العالمي.

تغطي الطبقات الثلاث:
  1) بوابة core/privilege.py: لا تنفيذ فعلي إطلاقاً عندما يكون العلم
     مفعّلاً (حتى subprocess.run لا يُستدعى).
  2) الوضع العادي: الأمر يُمرَّر كقائمة argv عبر pkexec كما هو متوقع.
  3) core/runtime.py نفسه: الضبط/القراءة/التسريب بين الحالات.
لا يُنفَّذ أي أمر حقيقي في هذه الاختبارات (كل subprocess وهمي).
"""
from __future__ import annotations

from unittest.mock import patch

from core.privilege import run_privileged, run_unprivileged
from core.runtime import is_dry_run, set_dry_run


class TestRuntimeFlag:
    def test_default_is_off(self):
        assert is_dry_run() is False

    def test_set_and_reset(self):
        set_dry_run(True)
        assert is_dry_run() is True
        set_dry_run(False)
        assert is_dry_run() is False

    def test_truthy_values_coerced_to_bool(self):
        set_dry_run(1)  # أرقام/سلاسل تُحوَّل إلى bool
        assert is_dry_run() is True
        set_dry_run("")
        assert is_dry_run() is False


class TestPrivilegeGate:
    def test_dry_run_blocks_execution_entirely(self):
        """البوابة يجب أن تمنع subprocess.run نفسه — لا أمر يصل للنظام."""
        set_dry_run(True)
        with patch("core.privilege.subprocess.run") as mock_run:
            mock_run.side_effect = AssertionError(
                "subprocess.run استُدعي رغم وضع dry-run!"
            )
            result = run_privileged(["pacman", "-Rns", "linux54"])
        mock_run.assert_not_called()
        assert result.ok  # نتيجة سليمة بنيوياً (لا انهيار في الوحدات)
        assert "[DRY-RUN]" in result.stdout
        assert "pacman -Rns linux54" in result.stdout

    def test_dry_run_works_without_pkexec_installed(self):
        """dry-run يعمل حتى لو pkexec غير موجود (بيئة CI بلا polkit)."""
        set_dry_run(True)
        with patch("core.privilege._pkexec_available", return_value=False):
            result = run_privileged(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
        assert "[DRY-RUN]" in result.stdout

    def test_normal_mode_passes_argv_via_pkexec(self):
        """بدون dry-run: الأمر يُنفَّذ كقائمة argv عبر pkexec (قاعدة shell=False)."""
        set_dry_run(False)
        with patch("core.privilege._pkexec_available", return_value=True), \
             patch("core.privilege.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "ok"
            mock_run.return_value.stderr = ""
            result = run_privileged(["pacman", "-Syu"])
        called_args = mock_run.call_args.args[0]
        assert called_args == ["pkexec", "pacman", "-Syu"]  # قائمة argv صريحة
        assert result.ok

    def test_unprivileged_scan_commands_still_run_in_dry_run(self):
        """فحوص القراءة (scan) تظل تعمل في dry-run — النافذة تحتاج نتائج
        فحص حقيقية؛ ما يُمنع هو أوامر التعديل المرتفعة الصلاحية فقط."""
        set_dry_run(True)
        with patch("core.privilege.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "btrfs"
            mock_run.return_value.stderr = ""
            result = run_unprivileged(["findmnt", "-no", "FSTYPE", "/"])
        assert result.stdout.strip() == "btrfs"
        mock_run.assert_called_once()
