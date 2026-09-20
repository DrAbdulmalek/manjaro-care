#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_btrfs_health.py — اختبارات وحدة صحة btrfs.

المحللات نقية، والفحوص التي تتطلب جذر تُظهر ذلك بصدق (لا نجاح مختلق)،
والإجراءان يمرران argv صريحين عبر pkexec، وdry-run يمنع كل شيء.
"""
from __future__ import annotations

from unittest.mock import patch

from core.module_base import Severity
from core.privilege import CommandResult
from core.runtime import set_dry_run
from modules import btrfs_health as bh
from modules.btrfs_health import (
    BtrfsHealthModule,
    parent_device,
    parse_blame,
    parse_device_stats,
    parse_scrub_status,
)

SCRUB_OK = """\
UUID:             abc-def
Scrub started:    Sun Sep 20 10:00:00 2026
Status:           finished
Duration:         0:05:23
Total to scrub:   100.00GiB
Rate:             500.00MiB/s
Error summary:    no errors found
"""
SCRUB_ERRORS = SCRUB_OK.replace("no errors found", "5 errors found")
SCRUB_RUNNING = SCRUB_OK.replace("finished", "running")
DEVICE_STATS_CLEAN = "/dev/sda2 0\n"
DEVICE_STATS_BAD = "/dev/sda2 0\n/dev/sdb1 5\n"
BLAME = """\
2.500s systemd-journald.service
1min 30.200s NetworkManager-wait-online.service
900ms ufw.service
1.200s NetworkManager.service
"""


class TestParsers:
    def test_parse_scrub_status_ok(self):
        info = parse_scrub_status(SCRUB_OK)
        assert info["state"] == "finished"
        assert "no errors" in info["errors"]
        assert info["duration"] == "0:05:23"

    def test_parse_scrub_status_missing(self):
        assert parse_scrub_status("")["state"] is None

    def test_parse_device_stats_clean(self):
        assert parse_device_stats(DEVICE_STATS_CLEAN) == [("/dev/sda2", 0.0)]

    def test_parse_device_stats_bad(self):
        parsed = parse_device_stats(DEVICE_STATS_BAD)
        assert ("/dev/sdb1", 5.0) in parsed

    def test_parse_blame(self):
        rows = parse_blame(BLAME)
        assert rows[0] == ("2.500s", "systemd-journald.service")
        assert len(rows) == 4
        assert rows[1] == ("1min 30.200s", "NetworkManager-wait-online.service")  # صيغة الدقائق

    def test_parse_blame_top_limit(self):
        assert len(parse_blame(BLAME, top=2)) == 2

    def test_parent_device_variants(self):
        assert parent_device("/dev/sda2[/@]") == "/dev/sda"
        assert parent_device("/dev/nvme0n1p2[/@]") == "/dev/nvme0n1"
        assert parent_device("/dev/mmcblk0p1") == "/dev/mmcblk0"
        assert parent_device("/dev/sda2") == "/dev/sda"

    def test_parent_device_uuid_not_guessed(self):
        """مصدر UUID لا يُخمَّن جهازه — يبقى None (رفض التخمين)."""
        assert parent_device("UUID=abcd-ef") is None


def _healthy_env():
    """بيئة وهمية كاملة لنظام btrfs سليم."""
    def fake_run_unprivileged(args, timeout=30):
        key = " ".join(args)
        responses = {
            "findmnt -no FSTYPE /": CommandResult(0, "btrfs\n", ""),
            "findmnt -no SOURCE /": CommandResult(0, "/dev/sda2[/@]\n", ""),
            "btrfs scrub status /": CommandResult(0, SCRUB_OK, ""),
            "btrfs device stats /": CommandResult(0, DEVICE_STATS_CLEAN, ""),
            "systemctl is-enabled fstrim.timer": CommandResult(0, "enabled\n", ""),
            "systemctl is-active fstrim.timer": CommandResult(0, "active\n", ""),
            "systemd-analyze blame": CommandResult(0, BLAME, ""),
            "smartctl --health /dev/sda": CommandResult(0, "SMART overall-health self-assessment test result: PASSED", ""),
        }
        return responses.get(key, CommandResult(1, "", "mock miss"))
    return patch.object(bh, "run_unprivileged", side_effect=fake_run_unprivileged)


class TestScan:
    def setup_method(self):
        self.module = BtrfsHealthModule()

    def test_non_btrfs_not_applicable(self):
        with patch.object(bh, "run_unprivileged",
                          return_value=CommandResult(0, "ext4\n", "")):
            result = self.module.scan()
        assert "غير قابل للتطبيق" in result.findings[0].title

    def test_healthy_system_all_ok(self):
        with _healthy_env():
            result = self.module.scan()
        assert result.worst_severity in (Severity.OK, Severity.INFO)
        assert any("scrub سليم" in f.title for f in result.findings)
        assert any("SMART لـ /dev/sda" in f.title for f in result.findings)

    def test_scrub_errors_critical(self):
        with _healthy_env(), \
             patch.object(bh, "run_unprivileged", side_effect=[
                 CommandResult(0, "btrfs\n", ""),       # FSTYPE
                 CommandResult(0, SCRUB_ERRORS, ""),    # scrub status
                 CommandResult(0, "/dev/sda2[/@]\n", ""),  # SOURCE
                 CommandResult(0, DEVICE_STATS_CLEAN, ""),  # device stats
                 CommandResult(0, "PASSED", ""),        # smartctl
                 CommandResult(0, "enabled\n", ""),     # is-enabled
                 CommandResult(0, BLAME, ""),           # blame
             ]):
            result = self.module.scan()
        assert result.worst_severity == Severity.CRITICAL

    def test_root_required_reads_are_honest_not_faked(self):
        """فحص يتطلب جذر = نتيجة صادقة صريحة، لا نجاح مختلق."""
        with patch.object(bh, "run_unprivileged", side_effect=[
            CommandResult(0, "btrfs\n", ""),                       # FSTYPE
            CommandResult(1, "", "ERROR: access denied by kernel"),  # scrub status
            CommandResult(1, "", "denied"),                        # device stats
            CommandResult(0, "/dev/sda2[/@]\n", ""),               # SOURCE
            CommandResult(1, "", "denied"),                        # smartctl
            CommandResult(0, "enabled\n", ""),                     # is-enabled
            CommandResult(0, BLAME, ""),                           # blame
        ]):
            result = self.module.scan()
        assert any("تتطلب صلاحيات جذر" in f.title for f in result.findings)


class TestApply:
    def setup_method(self):
        self.module = BtrfsHealthModule()

    def test_apply_runs_both_actions_via_pkexec_argv(self):
        calls = []
        with patch.object(bh, "run_privileged",
                          side_effect=lambda a, timeout=300: calls.append(a) or CommandResult(0, "ok", "")), \
             patch.object(bh, "run_unprivileged", side_effect=[
                 CommandResult(0, "finished\n", ""),   # scrub status (ليس جارياً)
                 CommandResult(0, "disabled\n", ""),   # is-enabled
                 CommandResult(0, "enabled\n", ""),    # is-enabled بعد التنفيذ (غير مستخدم هنا)
             ]):
            result = self.module.apply()
        assert ["btrfs", "scrub", "start", "-B", "/"] in calls
        assert ["systemctl", "enable", "--now", "fstrim.timer"] in calls
        assert result.success

    def test_apply_skips_running_scrub(self):
        calls = []
        with patch.object(bh, "run_privileged",
                          side_effect=lambda a, timeout=300: calls.append(a) or CommandResult(0, "ok", "")), \
             patch.object(bh, "run_unprivileged", side_effect=[
                 CommandResult(0, "Status: running\n", ""),  # scrub جارٍ
                 CommandResult(0, "enabled\n", ""),          # fstrim مفعّل
             ]):
            result = self.module.apply()
        assert calls == []  # لا إجراء لازماً — لا تنفيذ
        assert "بالفعل" in result.log_output

    def test_apply_dry_run_executes_nothing(self):
        set_dry_run(True)
        try:
            with patch.object(bh, "run_privileged") as m_run:
                result = self.module.apply()
        finally:
            set_dry_run(False)
        m_run.assert_not_called()
        assert "[DRY-RUN]" in result.message
