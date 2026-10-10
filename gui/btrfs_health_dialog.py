#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/btrfs_health_dialog.py — نافذة «إدارة فردية» لصحة btrfs:
إجراءان اختياريان منفصلان (بدء scrub / تفعيل fstrim.timer)، كلٌّ
بمعاينة أمره الحرفي وتأكيده الخاص — بلا أي إجراء مدمج غامض."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.logger import get_logger
from core.privilege import run_privileged
from gui.workers import FunctionWorker

log = get_logger("btrfs_health_dialog")


class BtrfsHealthDialog(QDialog):
    """إجراءان مستقلان بمعاينة وتأكيد لكل منهما + منطقة مخرجات."""

    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self._worker: FunctionWorker | None = None
        self.setWindowTitle(f"{module.name} — إجراءات")
        self.resize(560, 420)
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        note = QLabel(
            "كل إجراء يعرض أمره الحرفي ويطلب تأكيده الخاص — لا شيء يُنفَّذ تلقائياً."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #ffca28;")
        layout.addWidget(note)

        # ---- الإجراء 1: scrub ----
        scrub_group = QGroupBox("بدء scrub — فحص كامل لسلامة البيانات (قراءة كل البيانات، لا حذف)")
        sg = QHBoxLayout(scrub_group)
        self.scrub_preview = QLabel("$ btrfs scrub start -B /")
        self.scrub_preview.setStyleSheet("font-family: monospace; color: #9fdc9f;")
        sg.addWidget(self.scrub_preview, stretch=1)
        scrub_btn = QPushButton("بدء scrub…")
        scrub_btn.clicked.connect(self._on_scrub)
        sg.addWidget(scrub_btn)
        layout.addWidget(scrub_group)

        # ---- الإجراء 2: fstrim ----
        trim_group = QGroupBox("fstrim.timer — صيانة SSD الأسبوعية")
        tg = QHBoxLayout(trim_group)
        self.trim_preview = QLabel("$ systemctl enable --now fstrim.timer")
        self.trim_preview.setStyleSheet("font-family: monospace; color: #9fdc9f;")
        tg.addWidget(self.trim_preview, stretch=1)
        trim_btn = QPushButton("تفعيل…")
        trim_btn.clicked.connect(self._on_trim)
        tg.addWidget(trim_btn)
        layout.addWidget(trim_group)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "background-color: #1e1e1e; color: #9fdc9f; font-family: monospace; font-size: 9pt;"
        )
        layout.addWidget(self.output, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _log(self, text: str) -> None:
        self.output.append(text)
        log.info(text)

    def _run_bg(self, func, on_done) -> None:
        self._worker = FunctionWorker(func)
        self._worker.finished_ok.connect(on_done)
        self._worker.failed.connect(lambda e: self._log(f"خطأ: {e}"))
        self._worker.start()

    def _on_scrub(self) -> None:
        confirm = QMessageBox.question(
            self, "تأكيد بدء scrub",
            "سيُنفَّذ:\n  pkexec btrfs scrub start -B /\n\n"
            "قراءة كاملة لكل بيانات القرص — قد يستغرق دقائق إلى ساعات "
            "حسب الحجم، ويُفضَّل ألا يكون النظام تحت ضغط إدخال/إخراج شديد. "
            "لا يحذف شيئاً. متابعة؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._log("جارٍ scrub (قد يستغرق وقتاً طويلاً)...")
        self._run_bg(
            lambda: run_privileged(["btrfs", "scrub", "start", "-B", "/"], timeout=3600 * 3),
            lambda r: self._log(
                ("اكتمل scrub." if r.ok else f"فشل scrub (كود {r.returncode}).")
                + f"\n{(r.stdout + r.stderr)[-600:]}"
            ),
        )

    def _on_trim(self) -> None:
        confirm = QMessageBox.question(
            self, "تأكيد تفعيل fstrim.timer",
            "سيُنفَّذ:\n  pkexec systemctl enable --now fstrim.timer\n\n"
            "مفعّل = trim أسبوعي تلقائي. على أقراص HDD عديم الفائدة (لا ضرر). متابعة؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._run_bg(
            lambda: run_privileged(["systemctl", "enable", "--now", "fstrim.timer"]),
            lambda r: self._log(
                ("تم تفعيل fstrim.timer." if r.ok else f"فشل التفعيل (كود {r.returncode}).")
                + f"\n{r.stderr[:300]}"
            ),
        )
