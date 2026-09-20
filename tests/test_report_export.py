#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_report_export.py — اختبارات التنقيح والتجميع (المهمة 5).

التنقيح هو المنطق الأكثر أماناً-حرجاً: كل اختبار يفشل لو تسرب أي
جزء من المعلومة الحساسة إلى النص المنقّى.
"""
from __future__ import annotations

from unittest.mock import patch

from core.module_base import Severity
from core.runtime import set_dry_run
from modules import report_export as re_mod
from modules.report_export import (
    ReportExportModule,
    build_report_text,
    redact_home_paths,
    redact_ipv4,
    redact_ipv6,
    redact_mac,
    redact_serials,
    redact_text,
)


class TestRedactionIPv4:
    def test_redacts_valid_ipv4(self):
        assert redact_ipv4("connected to 192.168.1.55 ok") == "connected to «عنوان-IP» ok"

    def test_keeps_non_ip_dotted_numbers(self):
        """إصدار نواة مثل 6.6.10-1 ليس عنوان IP (مقطع > 255) — يبقى."""
        text = "kernel 6.6.100.300 version"
        assert redact_ipv4(text) == text  # 300 > 255 → ليس IP

    def test_redacts_lan_and_public(self):
        assert "10.0.0.1" not in redact_ipv4("gw 10.0.0.1")
        assert "8.8.8.8" not in redact_ipv4("dns 8.8.8.8")


class TestRedactionIPv6:
    def test_redacts_full_ipv6(self):
        assert "2001:0db8:85a3:0000:0000:8a2e:0370:7334" not in redact_ipv6(
            "addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334")

    def test_redacts_compressed_ipv6(self):
        out = redact_ipv6("link fe80::1 gw 2001:db8::8a2e:370:7334")
        assert "fe80::1" not in out
        assert "2001:db8::" not in out
        assert "«عنوان-IP»" in out

    def test_redacts_loopback_shorthand(self):
        assert "::1" not in redact_ipv6("lo ::1")

    def test_time_not_redacted_as_ipv6(self):
        assert "12:34:56" in redact_ipv6("at 12:34:56")


class TestRedactionMAC:
    def test_colon_mac(self):
        assert "aa:bb:cc:dd:ee:ff" not in redact_mac("mac aa:bb:cc:dd:ee:ff")

    def test_dash_mac(self):
        assert "AA-BB-CC-DD-EE-FF" not in redact_mac("MAC AA-BB-CC-DD-EE-FF")

    def test_time_not_redacted(self):
        """12:34:56 ليست MAC (تحتوي أجزاء قصيرة)."""
        assert "12:34:56" in redact_mac("at 12:34:56")


class TestRedactionSerials:
    def test_serial_value_masked_key_kept(self):
        text = "Serial Number: SNX123456789\nDisk OK"
        out = redact_serials(text)
        assert "SNX123456789" not in out
        assert "Serial Number:" in out  # اسم المفتاح يبقى للسياق

    def test_slash_n_variant(self):
        out = redact_serials("S/N = ABC-9911")
        assert "ABC-9911" not in out

    def test_normal_lines_untouched(self):
        assert redact_serials("nothing serial here") == "nothing serial here"


class TestRedactionPathsAndIdentity:
    def test_home_paths_all_users(self):
        out = redact_home_paths("reading /home/alice/x and /home/bob_y")
        assert "/home/alice" not in out and "/home/bob_y" not in out
        assert out.count("/home/«مستخدم»") == 2

    def test_hostname_replaced(self):
        out = redact_text("host manjaro-box is up", "u", "manjaro-box")
        assert "manjaro-box" not in out and "«اسم-الجهاز»" in out

    def test_username_replaced(self):
        out = redact_text("owner alice logged in", "alice", "h")
        assert "alice" not in out and "«مستخدم»" in out

    def test_full_pipeline_all_at_once(self):
        secret_report = (
            "user: alice\nhost: manjaro-box\nip: 192.168.10.7\n"
            "mac: aa:bb:cc:dd:ee:ff\nSerial Number: SNX-42\nlog: /home/alice/x.log\n"
        )
        out = redact_text(secret_report, "alice", "manjaro-box")
        for leaked in ("alice", "manjaro-box", "192.168.10.7",
                       "aa:bb:cc:dd:ee:ff", "SNX-42", "/home/alice"):
            assert leaked not in out, f"تسرب: {leaked}"


class TestReportAssembly:
    def test_build_report_includes_sections_and_is_redacted(self):
        with patch.object(re_mod, "getpass") as m_gp, \
             patch.object(re_mod, "socket") as m_sock:
            m_gp.getuser.return_value = "alice"
            m_sock.gethostname.return_value = "manjaro-box"
            text = build_report_text()
        assert "تقرير صيانة manjaro-care" in text
        assert "## " in text  # أقسام الوحدات
        assert "alice" not in text and "manjaro-box" not in text

    def test_failing_module_does_not_break_report(self):
        with patch.object(re_mod, "_curated_modules") as m_mods, \
             patch.object(re_mod, "getpass", side_effect=lambda: None) as m_gp, \
             patch.object(re_mod, "socket") as m_sock:
            m_gp.getuser.return_value = ""
            m_sock.gethostname.return_value = ""

            broken = type("Broken", (), {
                "name": "مكسورة", "scan": lambda self: 1 / 0,
            })()
            working = type("Working", (), {
                "name": "سليمة",
                "scan": lambda self: type("R", (), {
                    "error": None,
                    "findings": [type("F", (), {
                        "title": "كل شيء سليم", "detail": "",
                        "severity": Severity.OK,
                    })()],
                })(),
            })()
            m_mods.return_value = [broken, working]
            text = build_report_text()
        assert "تعذّر فحص هذه الوحدة" in text
        assert "كل شيء سليم" in text


class TestApply:
    def setup_method(self):
        self.module = ReportExportModule()

    def test_apply_writes_redacted_report_to_home(self, tmp_path=None):
        written = {}
        import builtins

        real_open = builtins.open

        def fake_open(path, mode="r", *a, **kw):
            if str(path).endswith(".md") and "w" in mode:
                written["path"] = str(path)
                written["content"] = None
                import io
                buf = io.StringIO()
                original_write = buf.write

                def capture(s):
                    written["content"] = (written["content"] or "") + s
                    return original_write(s)
                buf.write = capture
                buf.close = lambda: None
                return buf
            return real_open(path, mode, *a, **kw)

        with patch.object(re_mod, "default_report_path", return_value="/home/x/r.md"), \
             patch.object(re_mod, "build_report_text", return_value="# تقرير منقّى\n"), \
             patch.object(re_mod, "open", fake_open):
            result = self.module.apply()

        assert result.success
        assert written["path"] == "/home/x/r.md"
        assert "«مستخدم»" in (written["content"] or "") or "# تقرير" in (written["content"] or "")

    def test_apply_dry_run_writes_nothing(self):
        set_dry_run(True)
        try:
            with patch.object(re_mod, "default_report_path", return_value="/home/x/r.md"), \
                 patch("builtins.open", side_effect=AssertionError("open استُدعي رغم dry-run!")):
                result = self.module.apply()
        finally:
            set_dry_run(False)
        assert "[DRY-RUN]" in result.message

    def test_scan_marks_ready_with_preview_hint(self):
        with patch.object(re_mod, "build_report_text", return_value="report"):
            result = self.module.scan()
        assert result.findings[0].actionable
        assert "إدارة فردية" in result.findings[0].detail
