#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_update_check.py — اختبارات وحدة مؤشرات دورة التحديث.

الوحدة إخبارية: كل الاختبارات تحقق أن scan لا يعدّل شيئاً، والتحليل
نقي، والشبكة تتحلل برشاقة، وapply لا ينفّذ إجراء تعديلي أبداً.
"""
from __future__ import annotations

from unittest.mock import patch

from core.module_base import Severity
from core.privilege import CommandResult
from modules import update_check as uc
from modules.update_check import (
    UpdateCheckModule,
    parse_pacnew_paths,
    parse_rss_titles,
    sync_db_age_days,
)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Announcements</title>
  <item><title>Manjaro 25.0 released</title><link>https://x/1</link></item>
  <item><title><![CDATA[Kernel update & security notes]]></title></item>
  <item><title>Third news</title></item>
</channel></rss>
"""


class TestParsers:
    def test_parse_pacnew_paths(self):
        out = "/etc/pacman.conf.pacnew\n\n/etc/sddm.conf.pacsave\n"
        assert parse_pacnew_paths(out) == ["/etc/pacman.conf.pacnew", "/etc/sddm.conf.pacsave"]

    def test_sync_db_age_days(self):
        now = 1_000_000.0
        mtimes = {"core.db": now - 86400, "extra.db": now - 3 * 86400}
        assert sync_db_age_days(mtimes, now=now) == 3.0  # الأقدم يحكم

    def test_sync_db_age_empty(self):
        assert sync_db_age_days({}, now=1.0) is None

    def test_parse_rss_titles(self):
        titles = parse_rss_titles(SAMPLE_RSS, limit=5)
        assert titles[0] == "Manjaro 25.0 released"
        assert titles[1] == "Kernel update & security notes"  # CDATA مفكوكة
        assert len(titles) == 3

    def test_parse_rss_limit(self):
        assert len(parse_rss_titles(SAMPLE_RSS, limit=2)) == 2

    def test_parse_rss_garbage_graceful(self):
        assert parse_rss_titles("not xml at all <<<>>") == []


class TestFetchNews:
    def test_graceful_on_network_error(self):
        """غياب الشبكة لا يرمي استثناء — تدهور رشيق ([], سبب)."""
        with patch.object(uc.urllib.request, "urlopen", side_effect=OSError("no net")):
            titles, error = uc.fetch_news_titles()
        assert titles == []
        assert "no net" in (error or "")

    def test_success_parses_titles(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return SAMPLE_RSS.encode()

        with patch.object(uc.urllib.request, "urlopen", return_value=FakeResponse()):
            titles, error = uc.fetch_news_titles()
        assert error is None and titles[0] == "Manjaro 25.0 released"


class TestScan:
    def setup_method(self):
        self.module = UpdateCheckModule()

    def test_all_clean_is_ok(self):
        with patch.object(uc, "_find_pacnew_files", return_value=[]), \
             patch.object(uc, "_sync_db_mtimes", return_value={"core.db": 1.0}), \
             patch.object(uc, "sync_db_age_days", return_value=0.5), \
             patch.object(uc, "_get_failed_units", return_value=[]), \
             patch.object(uc, "fetch_news_titles", return_value=(["news"], None)):
            result = self.module.scan()
        assert result.worst_severity in (Severity.OK, Severity.INFO)

    def test_pacnew_files_listed(self):
        with patch.object(uc, "_find_pacnew_files",
                          return_value=["/etc/pacman.conf.pacnew"]), \
             patch.object(uc, "_sync_db_mtimes", return_value={}), \
             patch.object(uc, "_get_failed_units", return_value=[]), \
             patch.object(uc, "fetch_news_titles", return_value=([], "no net")):
            result = self.module.scan()
        assert any(".pacnew" in f.title for f in result.findings)
        assert "/etc/pacman.conf.pacnew" in result.findings[0].detail

    def test_stale_db_warns_about_partial_upgrade(self):
        with patch.object(uc, "_find_pacnew_files", return_value=[]), \
             patch.object(uc, "_sync_db_mtimes", return_value={"core.db": 1.0}), \
             patch.object(uc, "sync_db_age_days", return_value=30.0), \
             patch.object(uc, "_get_failed_units", return_value=[]), \
             patch.object(uc, "fetch_news_titles", return_value=([], None)):
            result = self.module.scan()
        stale = next(f for f in result.findings if "غير متزامنة" in f.title)
        assert stale.severity == Severity.WARNING
        assert "-Sy" in stale.detail and "-u" in stale.detail  # تحذير صريح

    def test_failed_services_critical_when_many(self):
        with patch.object(uc, "_find_pacnew_files", return_value=[]), \
             patch.object(uc, "_sync_db_mtimes", return_value={}), \
             patch.object(uc, "_get_failed_units",
                          return_value=["a.service", "b.service", "c.service"]), \
             patch.object(uc, "fetch_news_titles", return_value=([], None)):
            result = self.module.scan()
        assert any(f.severity == Severity.CRITICAL for f in result.findings)


class TestNoMutationGuarantees:
    """ضمانات الوحدة الإخبارية: لا تعديل أبداً."""
    def setup_method(self):
        self.module = UpdateCheckModule()

    def test_apply_never_mutates(self):
        with patch.object(uc, "run_unprivileged") as m_run:
            result = self.module.apply()
        m_run.assert_not_called()
        assert result.success
        assert "معلوماتية" in result.message

    def test_preview_shows_readonly_diff_commands(self):
        with patch.object(uc, "_find_pacnew_files",
                          return_value=["/etc/pacman.conf.pacnew"]):
            steps = self.module.preview()
        commands = [s.command for s in steps if s.command]
        assert "diff -u /etc/pacman.conf /etc/pacman.conf.pacnew" in commands

    def test_find_uses_argv_list_no_shell(self):
        with patch.object(uc, "run_unprivileged",
                          return_value=CommandResult(0, "", "")) as m_run:
            uc._find_pacnew_files()
        called = m_run.call_args.args[0]
        assert isinstance(called, list) and called[0] == "find"
        assert all(isinstance(a, str) for a in called)
