#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_kernel_cleanup.py — الحالة الحرجة الإلزامية:
وحدة تنظيف النُوى **لا تحذف النواة العاملة أبداً** تحت أي ظرف،
وترفض العمل كله عند تعذّر تحديد النواة الحالية بثقة.

كل subprocess وهمي (uname / pacman) — لا حزم حقيقية.
"""
from __future__ import annotations

from unittest.mock import patch

from core.module_base import Severity
from modules import kernel_cleanup as kc
from modules.kernel_cleanup import KernelCleanupModule


def _patch_system(uname_release: str | None, installed: list[str]):
    """بيئة وهمية: uname -r و pacman -Qq."""
    def fake_run_unprivileged(args, timeout=30):
        if args == ["uname", "-r"]:
            if uname_release is None:
                return kc.CommandResult(1, "", "no uname")
            return kc.CommandResult(0, uname_release + "\n", "")
        if args == ["pacman", "-Qq"]:
            return kc.CommandResult(0, "\n".join(installed) + "\n", "")
        return kc.CommandResult(1, "", "mock miss")
    return patch.object(kc, "run_unprivileged", side_effect=fake_run_unprivileged)


class TestRunningKernelDetection:
    def test_uname_maps_to_package(self):
        with _patch_system("6.6.10-1-MANJARO", ["linux54", "linux66"]):
            assert kc._running_kernel_package() == "linux66"

    def test_unknown_mapping_returns_none_not_guess(self):
        """uname لا يطابق أي حزمة مثبتة → None (لا تخمين — روح kernel_cleanup)."""
        with _patch_system("6.12.1-1-MANJARO", ["linux54", "linux66"]):
            assert kc._running_kernel_package() is None

    def test_bad_uname_returns_none(self):
        with _patch_system(None, ["linux66"]):
            assert kc._running_kernel_package() is None

    def test_nonstandard_uname_returns_none(self):
        with _patch_system("weird-output", ["linux66"]):
            assert kc._running_kernel_package() is None


class TestNeverDeleteRunningKernel:
    """العقد الأساسي: النواة العاملة + الأحدث محفوظتان دائماً."""

    def test_running_kernel_never_in_removable(self):
        with _patch_system("6.6.10-1-MANJARO", ["linux54", "linux61", "linux66"]):
            module = KernelCleanupModule()
            removable = module._compute_removable(
                ["linux54", "linux61", "linux66"], "linux66")
        assert "linux66" not in removable  # العاملة
        assert "linux61" not in removable  # الأحدث
        assert removable == ["linux54"]

    def test_running_older_than_newest_still_kept(self):
        """حتى لو كانت العاملة أقدم من الأحدث — لا تُحذف أبداً."""
        with _patch_system("5.15.0-1-MANJARO", ["linux515", "linux61", "linux66"]):
            removable = KernelCleanupModule()._compute_removable(
                ["linux515", "linux61", "linux66"], "linux515")
        assert "linux515" not in removable
        assert removable == []

    def test_removable_empty_when_running_unknown(self):
        assert KernelCleanupModule()._compute_removable(
            ["linux54", "linux66"], None) == []

    def test_apply_refuses_entirely_when_running_unknown(self):
        """تعذّر التحديد = رفض التنفيذ الكامل، لا حذف أي شيء."""
        with _patch_system(None, ["linux54", "linux61", "linux66"]), \
             patch.object(kc, "run_privileged") as m_run:
            result = KernelCleanupModule().apply()
        m_run.assert_not_called()  # صفر أوامر حذف
        assert not result.success
        assert "رفض" in result.message

    def test_apply_removes_only_candidates_and_appends_headers(self):
        calls = []
        with _patch_system("6.6.10-1-MANJARO", ["linux54", "linux61", "linux66"]), \
             patch.object(kc, "run_privileged",
                          side_effect=lambda a, timeout=300: calls.append(a)
                          or kc.CommandResult(0, "ok", "")):
            result = KernelCleanupModule().apply()
        called = calls[0]
        assert called[0:3] == ["pacman", "-Rns", "--noconfirm"]
        assert "linux66" not in called and "linux66-headers" not in called
        assert "linux61" not in called  # الأحدث تبقى
        assert "linux54" in called and "linux54-headers" in called
        assert result.success

    def test_scan_not_actionable_when_running_unknown(self):
        """الواجهة لن تعرض زر تنفيذ إن تعذّر تحديد النواة — أمان الواجهة."""
        with _patch_system(None, ["linux54", "linux61", "linux66"]):
            result = KernelCleanupModule().scan()
        assert not any(f.actionable for f in result.findings)

    def test_scan_few_kernels_is_ok(self):
        with _patch_system("6.6.10-1-MANJARO", ["linux66"]):
            result = KernelCleanupModule().scan()
        assert result.findings[0].severity == Severity.OK
