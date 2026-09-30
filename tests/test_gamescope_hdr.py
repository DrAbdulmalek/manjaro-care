#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_gamescope_hdr.py — اختبارات بنّاء أمر Gamescope HDR.

تتحقق من مطابقة السلوك الافتراضي لسكربت gamescope-hdr.sh الأصلي، ومن
الخيارات القابلة للضبط، ومن رفض الأوامر الفارغة.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.gamescope_hdr import build_gamescope_cmd, gamescope_available


class TestBuilderDefaults:
    def test_matches_original_script_semantics(self):
        """1920×1080@144 + --hdr-enabled + --hdr-itm-enable + env WSI/DXVK_HDR/DISPLAY=:1"""
        cmd = build_gamescope_cmd(["game", "--arg"])
        assert cmd[:8] == ["gamescope", "-W", "1920", "-H", "1080", "-r", "144",
                           "--hdr-enabled"]
        assert "--hdr-itm-enable" in cmd
        assert "--" in cmd
        tail = cmd[cmd.index("--") + 1:]
        assert tail[0] == "env"
        assert "ENABLE_GAMESCOPE_WSI=1" in tail
        assert "DXVK_HDR=1" in tail
        assert "DISPLAY=:1" in tail
        assert tail[-2:] == ["game", "--arg"]  # أمر اللعبة محفوظ كما هو

    def test_hdr_off_removes_both_flags(self):
        cmd = build_gamescope_cmd(["game"], hdr=False, itm=True)
        assert "--hdr-enabled" not in cmd
        # ITM بلا HDR بلا معنى — لكن يبقى قراراً صريحاً للمستخدم
        assert "--hdr-itm-enable" in cmd

    def test_itm_off(self):
        cmd = build_gamescope_cmd(["game"], hdr=True, itm=False)
        assert "--hdr-enabled" in cmd and "--hdr-itm-enable" not in cmd

    def test_custom_geometry_and_display(self):
        cmd = build_gamescope_cmd(["game"], width=2560, height=1440, rate=120,
                                  display=":2")
        assert cmd[:8] == ["gamescope", "-W", "2560", "-H", "1440", "-r", "120",
                           "--hdr-enabled"]
        assert "DISPLAY=:2" in cmd

    def test_env_flags_can_be_disabled(self):
        cmd = build_gamescope_cmd(["game"], enable_wsi=False, dxvk_hdr=False, hdr=False)
        tail = cmd[cmd.index("--") + 1:]
        assert tail == ["env", "DISPLAY=:1", "game"]

    def test_empty_game_cmd_raises(self):
        with pytest.raises(ValueError):
            build_gamescope_cmd([])


class TestAvailability:
    def test_which_probe(self):
        with patch("modules.gamescope_hdr.shutil.which", return_value=None):
            assert gamescope_available() is False
        with patch("modules.gamescope_hdr.shutil.which", return_value="/usr/bin/gamescope"):
            assert gamescope_available() is True
