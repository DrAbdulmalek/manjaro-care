#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/pdf_toolkit_dialog.py — نافذة حقيبة أدوات PDF.
ثلاث عمليات مستقلة: صور→PDF (img2pdf)، OCR (ocrmypdf)، استخراج نص
(pdftotext / pdf2txt.py). كل عملية تُنفَّذ في خيط خلفي بأوامر argv
صريحة، والأزرار تُعطَّل تلقائياً إن كانت أداتها غير مثبتة.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.logger import get_logger
from core.privilege import run_unprivileged
from core.runtime import is_dry_run
from gui.workers import BusyCloseGuardMixin
from modules.pdf_toolkit import (
    build_img2pdf_cmd,
    build_ocrmypdf_cmd,
    build_text_extract_cmd,
    text_extract_tool,
    tools_availability,
)

log = get_logger("pdf_toolkit_dialog")


class CmdWorker(QThread):
    """عامل عام: ينفّذ argv صريحاً ويعيد (نجاح، خرج)."""
    finished_ok = pyqtSignal(bool, str)
    failed = pyqtSignal(str)

    def __init__(self, cmd: list[str], timeout: int = 1800, parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._timeout = timeout

    def run(self):
        if is_dry_run():
            self.finished_ok.emit(True, "[DRY-RUN] لم يُنفَّذ: " + " ".join(self._cmd))
            return
        try:
            r = run_unprivileged(self._cmd, timeout=self._timeout)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(r.ok, (r.stdout + r.stderr)[-2000:] or
                              ("تم" if r.ok else f"فشل (رمز {r.returncode})"))


class PdfToolkitDialog(BusyCloseGuardMixin, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📄 حقيبة أدوات PDF")
        self.resize(640, 520)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._images: list[Path] = []   # مهيّأة فوراً — الضغط قبل الاختيار يُعالج كتنبيه لا انهيار
        self._avail = tools_availability()
        self._build_ui()

    # ---------------- بناء الواجهة ----------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        if is_dry_run():
            warn = QLabel("⚠️ وضع المعاينة الجافة مفعّل — الأوامر ستُعرض فقط.")
            warn.setStyleSheet("color: #ffb300; font-weight: bold;")
            layout.addWidget(warn)

        layout.addWidget(self._group_images_to_pdf())
        layout.addWidget(self._group_ocr())
        layout.addWidget(self._group_text_extract())
        layout.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _group_images_to_pdf(self) -> QGroupBox:
        g = QGroupBox("1) صور → PDF (img2pdf — بلا إعادة ترميز)")
        grid = QGridLayout(g)

        self.imgs_edit = QLineEdit(placeholderText="اختر صورة أو أكثر (jpg/png/tiff)…")
        self.imgs_edit.setReadOnly(True)
        grid.addWidget(self.imgs_edit, 0, 0)
        pick = QPushButton("اختيار…")
        pick.clicked.connect(self._pick_images)
        grid.addWidget(pick, 0, 1)

        self.imgpdf_out = QLineEdit(placeholderText="ملف الناتج…")
        self.imgpdf_out.setReadOnly(True)
        grid.addWidget(self.imgpdf_out, 1, 0)
        out_btn = QPushButton("الناتج…")
        out_btn.clicked.connect(self._pick_imgpdf_out)
        grid.addWidget(out_btn, 1, 1)

        self.imgpdf_btn = QPushButton("🧩 دمج الصور في PDF")
        self.imgpdf_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.imgpdf_btn.clicked.connect(self._run_images_to_pdf)
        self.imgpdf_btn.setEnabled(self._avail.get("img2pdf", False))
        self.imgpdf_btn.setToolTip("" if self._avail.get("img2pdf") else
                                   "img2pdf غير مثبت: pamac install img2pdf")
        grid.addWidget(self.imgpdf_btn, 2, 0, 1, 2)
        return g

    def _group_ocr(self) -> QGroupBox:
        g = QGroupBox("2) OCR لملف ممسوح ضوئياً (ocrmypdf — الناتج قابل للبحث)")
        grid = QGridLayout(g)

        self.ocr_src = QLineEdit(placeholderText="ملف PDF الأصلي…")
        self.ocr_src.setReadOnly(True)
        grid.addWidget(self.ocr_src, 0, 0)
        b1 = QPushButton("المصدر…")
        b1.clicked.connect(self._pick_ocr_src)
        grid.addWidget(b1, 0, 1)

        self.ocr_out = QLineEdit(placeholderText="ملف PDF الناتج…")
        self.ocr_out.setReadOnly(True)
        grid.addWidget(self.ocr_out, 1, 0)
        b2 = QPushButton("الناتج…")
        b2.clicked.connect(self._pick_ocr_out)
        grid.addWidget(b2, 1, 1)

        grid.addWidget(QLabel("اللغة:"), 2, 0)
        self.ocr_lang = QComboBox()
        self.ocr_lang.addItems(["ara+eng", "ara", "eng"])
        grid.addWidget(self.ocr_lang, 2, 1)

        self.ocr_btn = QPushButton("🔍 تشغيل OCR")
        self.ocr_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.ocr_btn.clicked.connect(self._run_ocr)
        self.ocr_btn.setEnabled(self._avail.get("ocrmypdf", False))
        self.ocr_btn.setToolTip("" if self._avail.get("ocrmypdf") else
                                "ocrmypdf غير مثبت: pamac install ocrmypdf")
        grid.addWidget(self.ocr_btn, 3, 0, 1, 2)
        return g

    def _group_text_extract(self) -> QGroupBox:
        g = QGroupBox(f"3) استخراج نص ({text_extract_tool() or 'لا أداة — ثبّت poppler'})")
        grid = QGridLayout(g)

        self.txt_src = QLineEdit(placeholderText="ملف PDF…")
        self.txt_src.setReadOnly(True)
        grid.addWidget(self.txt_src, 0, 0)
        b1 = QPushButton("المصدر…")
        b1.clicked.connect(self._pick_txt_src)
        grid.addWidget(b1, 0, 1)

        self.txt_out = QLineEdit(placeholderText="ملف النص الناتج…")
        self.txt_out.setReadOnly(True)
        grid.addWidget(self.txt_out, 1, 0)
        b2 = QPushButton("الناتج…")
        b2.clicked.connect(self._pick_txt_out)
        grid.addWidget(b2, 1, 1)

        self.txt_btn = QPushButton("📝 استخراج النص")
        self.txt_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.txt_btn.clicked.connect(self._run_text_extract)
        self.txt_btn.setEnabled(text_extract_tool() is not None)
        grid.addWidget(self.txt_btn, 2, 0, 1, 2)
        return g

    # ---------------- الالتقاطات ----------------

    def _pick_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختيار الصور", str(Path.home()),
            "صور (*.jpg *.jpeg *.png *.tif *.tiff *.bmp)")
        self._images = [Path(f) for f in files]
        self.imgs_edit.setText(f"{len(self._images)} صورة مختارة" if self._images else "")

    def _pick_imgpdf_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "ملف الناتج", str(Path.home() / "merged.pdf"),
                                           "PDF (*.pdf)")
        self.imgpdf_out.setText(f)

    def _pick_ocr_src(self):
        f, _ = QFileDialog.getOpenFileName(self, "PDF الأصلي", str(Path.home()),
                                           "PDF (*.pdf)")
        self.ocr_src.setText(f)

    def _pick_ocr_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "PDF الناتج",
                                           str(Path.home() / "ocr_output.pdf"), "PDF (*.pdf)")
        self.ocr_out.setText(f)

    def _pick_txt_src(self):
        f, _ = QFileDialog.getOpenFileName(self, "PDF المصدر", str(Path.home()),
                                           "PDF (*.pdf)")
        self.txt_src.setText(f)

    def _pick_txt_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "ملف النص", str(Path.home() / "out.txt"),
                                           "نص (*.txt)")
        self.txt_out.setText(f)

    # ---------------- التنفيذ ----------------

    def _required_out(self, text: str) -> Path | None:
        """يمنع بناء أمر بمسار ناتج فارغ (Path("") = "." — خطأ غامض لاحقاً)."""
        if not text.strip():
            QMessageBox.warning(self, "تنبيه", "حدّد ملف الناتج أولاً.")
            return None
        return Path(text.strip())

    def _start(self, cmd: list[str]):
        self.setEnabled(False)
        self.progress.setVisible(True)
        self._worker = CmdWorker(cmd, parent=self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _run_images_to_pdf(self):
        if not self._images:
            QMessageBox.warning(self, "تنبيه", "اختر صورة واحدة على الأقل أولاً.")
            return
        out = self._required_out(self.imgpdf_out.text())
        if out is None:
            return
        try:
            cmd = build_img2pdf_cmd(self._images, out)
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self._start(cmd)

    def _run_ocr(self):
        src_text = self.ocr_src.text().strip()
        if not src_text:
            QMessageBox.warning(self, "تنبيه", "اختر ملف PDF الأصلي أولاً.")
            return
        out = self._required_out(self.ocr_out.text())
        if out is None:
            return
        try:
            cmd = build_ocrmypdf_cmd(
                Path(src_text), out,
                lang=self.ocr_lang.currentText())
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self._start(cmd)

    def _run_text_extract(self):
        src_text = self.txt_src.text().strip()
        if not src_text:
            QMessageBox.warning(self, "تنبيه", "اختر ملف PDF أولاً.")
            return
        out = self._required_out(self.txt_out.text())
        if out is None:
            return
        try:
            cmd = build_text_extract_cmd(Path(src_text), out)
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self._start(cmd)

    def _on_done(self, ok: bool, msg: str):
        self.setEnabled(True)
        self.progress.setVisible(False)
        if ok:
            QMessageBox.information(self, "تم", msg)
        else:
            QMessageBox.critical(self, "فشل", msg)
        log.info("pdf_toolkit: %s", msg)

    def _on_fail(self, err: str):
        self.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "خطأ", err)
