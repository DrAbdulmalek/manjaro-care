#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_font_toolkit.py — اختبارات حقيبة الخطوط (منطق نقّي فقط)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.font_toolkit import (
    QUICK_RANGES,
    build_merge_cmd,
    build_subset_cmd,
    build_ttx_compile_cmd,
    build_ttx_dump_cmd,
    font_tools_availability,
)


class TestTtx:
    def test_dump_with_output(self):
        cmd = build_ttx_dump_cmd("f.ttf", "f.ttx")
        assert cmd == ["ttx", "-o", "f.ttx", "f.ttf"]

    def test_dump_writes_alongside_by_default(self):
        assert build_ttx_dump_cmd("f.ttf") == ["ttx", "f.ttf"]

    def test_compile_requires_xml(self):
        assert build_ttx_compile_cmd("f.ttx") == ["ttx", "f.ttx"]
        with pytest.raises(ValueError):
            build_ttx_compile_cmd("f.ttf")


class TestSubset:
    def test_with_unicode_range(self):
        cmd = build_subset_cmd("in.ttf", "out.ttf", unicodes="U+0600-06FF")
        assert cmd[0] == "pyftsubset"
        assert "--output-file=out.ttf" in cmd
        assert "--unicodes=U+0600-06FF" in cmd
        assert "--flavor=" not in " ".join(cmd)

    def test_with_text_file_and_flavor(self):
        cmd = build_subset_cmd("in.otf", "out.woff2", text_file="t.txt", flavor="woff2")
        assert "--text-file=t.txt" in cmd and "--flavor=woff2" in cmd

    def test_requires_a_source_of_glyphs(self):
        with pytest.raises(ValueError):
            build_subset_cmd("in.ttf", "out.ttf")

    def test_bad_flavor_raises(self):
        with pytest.raises(ValueError):
            build_subset_cmd("in.ttf", "out.ttf", unicodes="U+0041", flavor="eot")

    def test_quick_ranges_are_valid_shapes(self):
        # النطاقات الجاهزة صالحة كقيم --unicodes (حروف/فواصل/U+/أرقام/شرطات)
        for name, rng in QUICK_RANGES.items():
            assert rng.startswith("U+"), name
            assert " " not in rng, name


class TestMerge:
    def test_needs_two_fonts_min(self):
        with pytest.raises(ValueError):
            build_merge_cmd(["a.ttf"], "m.ttf")

    def test_cmd_shape(self):
        cmd = build_merge_cmd(["a.ttf", "b.otf"], "m.ttf")
        assert cmd == ["pyftmerge", "-o", "m.ttf", "a.ttf", "b.otf"]


class TestAvailability:
    def test_map(self):
        with patch("modules.font_toolkit.shutil.which",
                   side_effect=lambda t: "/x" if t == "ttx" else None):
            avail = font_tools_availability()
        assert avail == {"ttx": True, "pyftsubset": False, "pyftmerge": False}
