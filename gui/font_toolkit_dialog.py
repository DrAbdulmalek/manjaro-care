#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/font_toolkit_dialog.py — نافذة حقيبة أدوات الخطوط.
ثلاث عمليات: تفكيك/تجميع ttx، تقليص pyftsubset (بنطاقات جاهزة)،
ودمج pyftmerge. أوامر argv صريحة في خيوط خلفية، والأزرار موقوفة
إن كانت أدوات fonttools غير مثبتة.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
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

from core.runtime import is_dry_run
from gui.pdf_toolkit_dialog import CmdWorker  # عامل التنفيذ العام المشترك
from gui.workers import BusyCloseGuardMixin
from modules.font_toolkit import (
    QUICK_RANGES,
    build_merge_cmd,
    build_subset_cmd,
    build_ttx_compile_cmd,
    build_ttx_dump_cmd,
    font_tools_availability,
)


class FontToolkitDialog(BusyCloseGuardMixin, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔤 حقيبة أدوات الخطوط")
        self.resize(640, 560)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._avail = font_tools_availability()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        if is_dry_run():
            warn = QLabel("⚠️ وضع المعاينة الجافة مفعّل — الأوامر ستُعرض فقط.")
            warn.setStyleSheet("color: #ffb300; font-weight: bold;")
            layout.addWidget(warn)

        layout.addWidget(self._group_ttx())
        layout.addWidget(self._group_subset())
        layout.addWidget(self._group_merge())
        layout.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    # ---------------- الأقسام ----------------

    def _group_ttx(self) -> QGroupBox:
        g = QGroupBox("1) تفكيك/تجميع الخط ↔ XML (ttx)")
        grid = QGridLayout(g)

        self.ttx_font = QLineEdit(placeholderText="ملف الخط TTF/OTF أو ملف .ttx للتجميع…")
        self.ttx_font.setReadOnly(True)
        grid.addWidget(self.ttx_font, 0, 0)
        b1 = QPushButton("اختيار…")
        b1.clicked.connect(self._pick_ttx_font)
        grid.addWidget(b1, 0, 1)

        self.ttx_btn = QPushButton("🧬 تنفيذ (dump للخط / compile للـXML)")
        self.ttx_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.ttx_btn.clicked.connect(self._run_ttx)
        self.ttx_btn.setEnabled(self._avail.get("ttx", False))
        self.ttx_btn.setToolTip("" if self._avail.get("ttx") else
                                "ttx غير مثبت: pip install fonttools")
        grid.addWidget(self.ttx_btn, 1, 0, 1, 2)
        return g

    def _group_subset(self) -> QGroupBox:
        g = QGroupBox("2) تقليص خط إلى مجموعة رموز (pyftsubset)")
        grid = QGridLayout(g)

        self.sub_font = QLineEdit(placeholderText="ملف الخط المصدر…")
        self.sub_font.setReadOnly(True)
        grid.addWidget(self.sub_font, 0, 0)
        b1 = QPushButton("المصدر…")
        b1.clicked.connect(self._pick_sub_font)
        grid.addWidget(b1, 0, 1)

        self.sub_out = QLineEdit(placeholderText="ملف الخط الناتج…")
        self.sub_out.setReadOnly(True)
        grid.addWidget(self.sub_out, 1, 0)
        b2 = QPushButton("الناتج…")
        b2.clicked.connect(self._pick_sub_out)
        grid.addWidget(b2, 1, 1)

        grid.addWidget(QLabel("نطاق جاهز:"), 2, 0)
        self.sub_range = QComboBox()
        self.sub_range.addItems(list(QUICK_RANGES.keys()))
        grid.addWidget(self.sub_range, 2, 1)

        self.sub_custom = QLineEdit(placeholderText="أو نطاق مخصص: U+0600-06FF,…")
        grid.addWidget(self.sub_custom, 3, 0, 1, 2)

        grid.addWidget(QLabel("الصيغة:"), 4, 0)
        self.sub_flavor = QComboBox()
        self.sub_flavor.addItems(["ttf", "woff", "woff2"])
        grid.addWidget(self.sub_flavor, 4, 1)

        self.sub_btn = QPushButton("✂️ تقليص الخط")
        self.sub_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.sub_btn.clicked.connect(self._run_subset)
        self.sub_btn.setEnabled(self._avail.get("pyftsubset", False))
        self.sub_btn.setToolTip("" if self._avail.get("pyftsubset") else
                                "pyftsubset غير مثبت: pip install fonttools")
        grid.addWidget(self.sub_btn, 5, 0, 1, 2)
        return g

    def _group_merge(self) -> QGroupBox:
        g = QGroupBox("3) دمج خطوط (pyftmerge)")
        grid = QGridLayout(g)

        self.merge_fonts = QLineEdit(placeholderText="خطان أو أكثر…")
        self.merge_fonts.setReadOnly(True)
        self._merge_paths: list[Path] = []
        grid.addWidget(self.merge_fonts, 0, 0)
        b1 = QPushButton("إضافة…")
        b1.clicked.connect(self._pick_merge_fonts)
        grid.addWidget(b1, 0, 1)

        self.merge_out = QLineEdit(placeholderText="ملف الدمج الناتج…")
        self.merge_out.setReadOnly(True)
        grid.addWidget(self.merge_out, 1, 0)
        b2 = QPushButton("الناتج…")
        b2.clicked.connect(self._pick_merge_out)
        grid.addWidget(b2, 1, 1)

        self.merge_btn = QPushButton("🔗 دمج الخطوط")
        self.merge_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.merge_btn.clicked.connect(self._run_merge)
        self.merge_btn.setEnabled(self._avail.get("pyftmerge", False))
        self.merge_btn.setToolTip("" if self._avail.get("pyftmerge") else
                                  "pyftmerge غير مثبت: pip install fonttools")
        grid.addWidget(self.merge_btn, 2, 0, 1, 2)
        return g

    # ---------------- الالتقاطات ----------------

    def _pick_ttx_font(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "اختيار خط أو XML", str(Path.home()),
            "خطوط وXML (*.ttf *.otf *.woff *.woff2 *.ttx *.xml)")
        self.ttx_font.setText(f)

    def _pick_sub_font(self):
        f, _ = QFileDialog.getOpenFileName(self, "الخط المصدر", str(Path.home()),
                                           "خطوط (*.ttf *.otf *.woff *.woff2)")
        self.sub_font.setText(f)

    def _pick_sub_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "الخط الناتج",
                                           str(Path.home() / "subset.ttf"),
                                           "خطوط (*.ttf *.woff *.woff2)")
        self.sub_out.setText(f)

    def _pick_merge_fonts(self):
        files, _ = QFileDialog.getOpenFileNames(self, "خطوط للدمج", str(Path.home()),
                                                "خطوط (*.ttf *.otf)")
        self._merge_paths = [Path(x) for x in files]
        self.merge_fonts.setText(f"{len(self._merge_paths)} خطوط مختارة"
                                 if self._merge_paths else "")

    def _pick_merge_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "ملف الدمج",
                                           str(Path.home() / "merged.ttf"),
                                           "خطوط (*.ttf)")
        self.merge_out.setText(f)

    # ---------------- التنفيذ ----------------

    def _start(self, cmd: list[str]):
        self.setEnabled(False)
        self.progress.setVisible(True)
        self._worker = CmdWorker(cmd, parent=self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _run_ttx(self):
        path = self.ttx_font.text()
        if not path:
            QMessageBox.warning(self, "تنبيه", "اختر ملف خط أو XML أولاً.")
            return
        try:
            if path.lower().endswith((".ttx", ".xml")):
                cmd = build_ttx_compile_cmd(path)
            else:
                out = str(Path(path).with_suffix(".ttx"))
                cmd = build_ttx_dump_cmd(path, out)
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self._start(cmd)

    def _run_subset(self):
        if not self.sub_font.text().strip():
            QMessageBox.warning(self, "تنبيه", "اختر الخط المصدر أولاً.")
            return
        out_text = self.sub_out.text().strip()
        if not out_text:
            QMessageBox.warning(self, "تنبيه", "حدّد ملف الخط الناتج أولاً.")
            return
        custom = self.sub_custom.text().strip()
        unicodes = custom or QUICK_RANGES[self.sub_range.currentText()]
        flavor = self.sub_flavor.currentText()
        try:
            cmd = build_subset_cmd(
                self.sub_font.text().strip(), out_text,
                unicodes=unicodes,
                flavor=None if flavor == "ttf" else flavor)
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self._start(cmd)

    def _run_merge(self):
        out_text = self.merge_out.text().strip()
        if not out_text:
            QMessageBox.warning(self, "تنبيه", "حدّد ملف الدمج الناتج أولاً.")
            return
        try:
            cmd = build_merge_cmd([str(p) for p in self._merge_paths],
                                  out_text)
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

    def _on_fail(self, err: str):
        self.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "خطأ", err)
