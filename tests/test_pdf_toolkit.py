#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_pdf_toolkit.py — اختبارات حقيبة أدوات PDF (منطق نقّي فقط).

تغطي بنّائات أوامر img2pdf/ocrmypdf/استخراج النص، أولوية أداة النص،
وتحقق المدخلات. لا أوامر حقيقية.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from modules.pdf_toolkit import (
    build_img2pdf_cmd,
    build_ocrmypdf_cmd,
    build_text_extract_cmd,
    text_extract_tool,
    tools_availability,
)


class TestImg2Pdf:
    def test_basic_cmd(self, tmp_path):
        imgs = [tmp_path / "1.jpg", tmp_path / "2.png"]
        out = tmp_path / "o.pdf"
        cmd = build_img2pdf_cmd(imgs, out)
        assert cmd[0] == "img2pdf"
        assert cmd[-2] == "-o" and cmd[-1] == str(out)
        assert str(imgs[0]) in cmd and str(imgs[1]) in cmd

    def test_empty_images_raises(self):
        with pytest.raises(ValueError):
            build_img2pdf_cmd([], Path("o.pdf"))


class TestOcrMyPdf:
    def test_default_ara_eng_skip_text(self, tmp_path):
        cmd = build_ocrmypdf_cmd(tmp_path / "s.pdf", tmp_path / "o.pdf")
        assert cmd[0] == "ocrmypdf"
        assert "--skip-text" in cmd          # تخطي الصفحات ذات النص
        assert cmd[cmd.index("-l") + 1] == "ara+eng"
        assert cmd[-2] == str(tmp_path / "s.pdf") and cmd[-1] == str(tmp_path / "o.pdf")

    def test_no_skip_and_lang_choices(self, tmp_path):
        cmd = build_ocrmypdf_cmd(tmp_path / "s.pdf", tmp_path / "o.pdf",
                                 lang="ara", skip_text=False)
        assert "--skip-text" not in cmd
        assert cmd[cmd.index("-l") + 1] == "ara"

    def test_bad_lang_raises(self, tmp_path):
        with pytest.raises(ValueError):
            build_ocrmypdf_cmd(tmp_path / "s.pdf", tmp_path / "o.pdf", lang="fr")


class TestTextExtract:
    def test_prefers_pdftotext(self, tmp_path):
        with patch("modules.pdf_toolkit.shutil.which",
                   side_effect=lambda t: "/usr/bin/" + t if t == "pdftotext" else None):
            assert text_extract_tool() == "pdftotext"
            cmd = build_text_extract_cmd(tmp_path / "s.pdf", tmp_path / "o.txt")
            assert cmd[:2] == ["pdftotext", "-layout"]

    def test_falls_back_to_pdf2txt(self, tmp_path):
        with patch("modules.pdf_toolkit.shutil.which",
                   side_effect=lambda t: "/usr/bin/" + t if t == "pdf2txt.py" else None):
            cmd = build_text_extract_cmd(tmp_path / "s.pdf", tmp_path / "o.txt")
            assert cmd[0] == "pdf2txt.py"
            assert cmd[cmd.index("-o") + 1] == str(tmp_path / "o.txt")

    def test_no_tool_raises(self, tmp_path):
        with patch("modules.pdf_toolkit.shutil.which", return_value=None):
            with pytest.raises(ValueError):
                build_text_extract_cmd(tmp_path / "s.pdf", tmp_path / "o.txt")


class TestAvailability:
    def test_map_shape_and_bools(self):
        with patch("modules.pdf_toolkit.shutil.which",
                   side_effect=lambda t: "/x" if t == "img2pdf" else None):
            avail = tools_availability()
        assert avail["img2pdf"] is True
        assert avail["ocrmypdf"] is False
        assert set(avail) == {"img2pdf", "ocrmypdf", "pdftotext", "pdf2txt.py", "pypdfium2"}
