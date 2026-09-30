#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/archive_extract_dialog.py — نافذة الاستخراج الآمن للأرشيفات.
اختيار أرشيفات متعددة، عرض خطة كلٍّ منها (الأداة/الهدف/تخطي موجود)،
ثم التنفيذ المتسلسل في خيط خلفي وفق سلوك safe_extract.sh.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.logger import get_logger
from core.runtime import is_dry_run
from gui.workers import BusyCloseGuardMixin
from modules.archive_extract import (
    COMMON_ARCHIVE_EXTS,
    ExtractionOutcome,
    plan_extraction,
    run_extraction,
)

log = get_logger("archive_extract_dialog")

_ARCHIVE_FILTER = "أرشيفات (*.zip *.rar *.7z *.tar *.gz *.bz2 *.xz *.zst *.tgz)"


class ExtractWorker(QThread):
    """ينفّذ الخطط تسلسلياً ويرسل نتيجة كل أرشيف فور انتهائه."""
    row_result = pyqtSignal(int, object)   # (رقم الصف، ExtractionOutcome)
    all_done = pyqtSignal(int, int)        # (نجاح، فشل)
    failed = pyqtSignal(str)

    def __init__(self, plans: list, delete_on_success: bool, rows: list[int], parent=None):
        super().__init__(parent)
        self._plans = plans
        self._delete = delete_on_success
        self._rows = rows

    def run(self):
        ok = bad = 0
        try:
            for row, plan in zip(self._rows, self._plans, strict=True):
                outcome: ExtractionOutcome = run_extraction(plan, delete_on_success=self._delete)
                if outcome.success:
                    ok += 1
                else:
                    bad += 1
                self.row_result.emit(row, outcome)
        except Exception as exc:  # حماية الواجهة من أي مفاجأة
            log.exception("فشل عامل الاستخراج")
            self.failed.emit(str(exc))
            return
        self.all_done.emit(ok, bad)


class ArchiveExtractDialog(BusyCloseGuardMixin, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 الاستخراج الآمن للأرشيفات")
        self.resize(680, 480)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "يستخرج كل أرشيف إلى مجلد بنفس اسمه، ويحذف الأرشيف عند النجاح،\n"
            "وينظّف المجلد الجزئي عند الفشل مع الإبقاء على الأرشيف.\n"
            "المجلدات الموجودة مسبقاً تُتخطى بأمان."
        )
        info.setStyleSheet("color: #aaaaaa;")
        info.setWordWrap(True)
        layout.addWidget(info)

        if is_dry_run():
            warn = QLabel("⚠️ وضع المعاينة الجافة مفعّل — لن يُنفَّذ أي استخراج أو حذف.")
            warn.setStyleSheet("color: #ffb300; font-weight: bold;")
            layout.addWidget(warn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["الأرشيف", "الأداة", "المجلد الهدف", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        opts = QHBoxLayout()
        self.chk_delete = QCheckBox("حذف الأرشيف الأصلي بعد نجاح الاستخراج")
        self.chk_delete.setChecked(True)
        opts.addWidget(self.chk_delete)
        opts.addStretch()
        layout.addLayout(opts)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ اختيار أرشيفات")
        add_btn.clicked.connect(self._pick_archives)
        btn_row.addWidget(add_btn)

        self.run_btn = QPushButton("🚀 استخراج الكل")
        self.run_btn.setStyleSheet(
            "background-color: #1565c0; color: white; font-weight: bold; padding: 8px;")
        self.run_btn.clicked.connect(self._run)
        btn_row.addWidget(self.run_btn)

        btn_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _pick_archives(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختيار أرشيفات", str(Path.home() / "Downloads"), _ARCHIVE_FILTER)
        skipped = 0
        for f in files:
            path = Path(f)
            if path.suffix.lower() not in COMMON_ARCHIVE_EXTS:
                skipped += 1
                continue
            try:
                plan = plan_extraction(path)
            except Exception as exc:  # ملف تالف/غير قابل للتحليل — نبقي الباقي
                log.warning("تعذّر تحليل %s: %s", path, exc)
                QMessageBox.warning(
                    self, "تنبيه", f"تعذّر تحليل «{path.name}»: {exc}")
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(plan.archive.name)
            item.setData(Qt.UserRole, plan)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem(plan.tool))
            target_item = QTableWidgetItem(plan.target_dir.name)
            if plan.skip_existing:
                target_item.setText(f"{plan.target_dir.name} (موجود — سيُتخطى)")
            self.table.setItem(row, 2, target_item)
            self.table.setItem(row, 3, QTableWidgetItem("بانتظار التنفيذ"))
        if skipped:
            QMessageBox.information(
                self, "ملاحظة",
                f"تم تجاهل {skipped} ملفاً بامتداد غير مدعوم "
                f"(المسموح: {', '.join(sorted(COMMON_ARCHIVE_EXTS))}).")

    def _run(self):
        plans, rows = [], []
        for row in range(self.table.rowCount()):
            plan = self.table.item(row, 0).data(Qt.UserRole)
            if plan and self.table.item(row, 3).text() == "بانتظار التنفيذ":
                plans.append(plan)
                rows.append(row)
        if not plans:
            QMessageBox.information(self, "لا يوجد", "اختر أرشيفات أولاً.")
            return
        self.setEnabled(False)
        self.progress.setVisible(True)
        self._worker = ExtractWorker(plans, self.chk_delete.isChecked(), rows, parent=self)
        self._worker.row_result.connect(self._on_row)
        self._worker.all_done.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_row(self, row: int, outcome: ExtractionOutcome):
        mark = "✅" if outcome.success else "❌"
        if outcome.skipped:
            mark = "⏭️"
        elif outcome.dry_run:
            mark = "🔍"
        self.table.item(row, 3).setText(f"{mark} {outcome.message}")

    def _on_done(self, ok: int, bad: int):
        self.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.information(self, "انتهى", f"نجاح: {ok} | فشل: {bad}")
        self._refresh_status()

    def _on_fail(self, err: str):
        self.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "خطأ", err)

    def _refresh_status(self):
        for row in range(self.table.rowCount()):
            text = self.table.item(row, 3).text()
            if "بانتظار التنفيذ" in text:
                continue
            item = self.table.item(row, 0)
            plan = item.data(Qt.UserRole)
            plan.skip_existing = plan.target_dir.is_dir()
            if plan.skip_existing:
                self.table.item(row, 2).setText(
                    f"{plan.target_dir.name} (موجود — سيُتخطى)")
