#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/snapshot_dialog.py
======================
نافذة «إدارة فردية» لوحدة لقطة-قبل-التحديث: قائمة لقطات موحّدة
(timeshift/snapper)، إنشاء لقطة pre-update، تحديث اختياري بتأكيد
منفصل، ورجوع بتأكيد مزدوج مع تحذير صريح.

ما لم تُنفَّذ هنا: أي إجراء بلا معاينة — كل زر يعرض أولاً ماذا سيُنفَّذ
ثم يطلب التأكيد. كل الأوامر عبر core/privilege (pkexec، argv فقط).
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from core.logger import get_logger
from core.privilege import run_privileged
from gui.workers import FunctionWorker
from modules.snapper_cleanup import read_keep_count, write_keep_count
from modules.snapshot_before_update import (
    SNAPSHOT_TAG,
    detect_tool,
    list_snapshots,
)

log = get_logger("snapshot_dialog")


class SnapshotDialog(QDialog):
    """نافذة إدارة اللقطات: إنشاء / قائمة / رجوع (تأكيد مزدوج) / تحديث."""

    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self._worker: FunctionWorker | None = None
        self._snapshot_created_this_session = False
        self.setWindowTitle(f"{module.name} — إدارة فردية")
        self.resize(640, 520)
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self._refresh_list()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tool = detect_tool() or "لا أداة"
        info = QLabel(f"الأداة المكتشفة: {tool}")
        info.setStyleSheet("color: #bbbbbb;")
        layout.addWidget(info)

        # ---- جدول اللقطات ----
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "التاريخ", "الوصف"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # ---- منطقة المخرجات ----
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFixedHeight(110)
        self.output.setStyleSheet(
            "background-color: #1e1e1e; color: #9fdc9f; font-family: monospace; font-size: 9pt;"
        )
        layout.addWidget(self.output)

        # ---- إنشاء لقطة ----
        create_row = QHBoxLayout()
        create_btn = QPushButton(f"إنشاء لقطة موسومة '{SNAPSHOT_TAG}'")
        create_btn.setStyleSheet("background-color: #2e7d32; font-weight: bold;")
        create_btn.clicked.connect(self._on_create)
        create_row.addWidget(create_btn)
        create_row.addStretch()
        layout.addLayout(create_row)

        # ---- تحديث اختياري (تأكيد منفصل تماماً) ----
        update_group = QGroupBox("التحديث بعد اللقطة — اختياري وتأكيده منفصل")
        ug_layout = QHBoxLayout(update_group)
        update_btn = QPushButton("تحديث النظام الآن (pacman -Syu)")
        update_btn.setStyleSheet("background-color: #1565c0;")
        update_btn.clicked.connect(self._on_update)
        ug_layout.addWidget(update_btn)
        ug_layout.addStretch()
        layout.addWidget(update_group)

        # ---- الرجوع + إعداد الاحتفاظ ----
        restore_row = QHBoxLayout()
        restore_btn = QPushButton("رجوع إلى اللقطة المحددة")
        restore_btn.setStyleSheet("background-color: #c62828; font-weight: bold;")
        restore_btn.clicked.connect(self._on_restore)
        restore_row.addWidget(restore_btn)
        restore_row.addStretch()

        keep_label = QLabel("احتفظ بآخر N (snapper):")
        restore_row.addWidget(keep_label)
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(1, 200)
        self.keep_spin.setValue(read_keep_count())
        restore_row.addWidget(self.keep_spin)
        save_btn = QPushButton("حفظ N")
        save_btn.clicked.connect(self._on_save_keep)
        restore_row.addWidget(save_btn)
        layout.addLayout(restore_row)

        close_row = QHBoxLayout()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        close_row.addStretch()
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ------------------------------------------------------------------
    def _refresh_list(self) -> None:
        tool = detect_tool()
        if tool is None:
            self._log("لا أداة لقطات مثبتة — ثبّت timeshift أو snapper.")
            return
        snaps, error = list_snapshots(tool)
        if error:
            self._log(f"تعذّرت القراءة: {error}")
            return
        self.table.setRowCount(len(snaps))
        for row, s in enumerate(snaps):
            for col, value in enumerate((f"#{s['num']}", s["date"], s["desc"] or "بدون وصف")):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
        self._log(f"تم تحديث القائمة: {len(snaps)} لقطة عبر {tool}.")

    def _selected_snapshot(self) -> tuple[str, str] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        num = self.table.item(row, 0).text().lstrip("#")
        desc = self.table.item(row, 2).text()
        return num, desc

    def _log(self, text: str) -> None:
        self.output.append(text)
        log.info(text)

    def _run_bg(self, func, on_done) -> None:
        """كل العمل الذي يستدعي pkexec يمر بخيط خلفي (نفس نمط ModuleCard)."""
        self._worker = FunctionWorker(func)
        self._worker.finished_ok.connect(on_done)
        self._worker.failed.connect(lambda e: self._log(f"خطأ: {e}"))
        self._worker.start()

    # ------------------------------------------------------------------
    def _on_create(self) -> None:
        tool = detect_tool()
        if tool is None:
            QMessageBox.information(self, "غير متاح", "لا أداة لقطات مثبتة.")
            return
        confirm = QMessageBox.question(
            self, "تأكيد إنشاء لقطة",
            f"سيُنفَّذ الآن:\n  {self.module.preview()[0].command}\nهل أنت متأكد؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._log(f"جارٍ إنشاء اللقطة عبر {tool}...")
        self._run_bg(self.module.apply, self._on_create_done)

    def _on_create_done(self, result) -> None:
        self._log(result.message)
        if result.log_output:
            self._log(result.log_output[:500])
        if result.success and "DRY-RUN" not in result.message:
            self._snapshot_created_this_session = True
        self._refresh_list()

    # ------------------------------------------------------------------
    def _on_update(self) -> None:
        """التحديث: تأكيد منفصل صريح — ولا ننفّذه إن لم توجد لقطة."""
        if not self._snapshot_created_this_session:
            QMessageBox.warning(
                self, "لا لقطة من هذه الجلسة",
                "أنشئ لقطة pre-update أولاً من الزر أعلاه — لن يُنفَّذ تحديث "
                "دون لقطة رجوع حديثة.",
            )
            return
        confirm = QMessageBox.question(
            self, "تأكيد التحديث (منفصل)",
            "سيُنفَّذ الآن:\n  pkexec pacman -Syu --noconfirm\n\n"
            "هذا تحديث كامل للنظام وقد يستغرق دقائق. أنشأتَ لقطة قبل قليل. "
            "هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._log("جارٍ التحديث (قد يستغرق دقائق)...")
        self._run_bg(
            lambda: run_privileged(["pacman", "-Syu", "--noconfirm"], timeout=3600),
            lambda r: self._log(
                ("اكتمل التحديث." if r.ok else f"انتهى التحديث برمز {r.returncode} — "
                 "راجع المخرجات في بطاقة الوحدة أو journalctl.")
                + (f"\n{r.stdout[-800:]}" if r.stdout else "")
            ),
        )

    # ------------------------------------------------------------------
    def _on_restore(self) -> None:
        """الرجوع: تأكيد مزدوج + تحذير صريح. timeshift تفاعلي بطبيعته
        فيُعرض كأمر حرفي للنسخ إلى الطرفية (لا أتمتة قاتلة)."""
        selection = self._selected_snapshot()
        if selection is None:
            QMessageBox.information(self, "لا تحديد", "حدّد لقطة من الجدول أولاً.")
            return
        num, desc = selection
        if num == "0":
            QMessageBox.warning(self, "غير صالح", "اللقطة 0 هي الحالة الحية — لا يمكن الرجوع إليها.")
            return

        tool = detect_tool()
        if tool == "timeshift":
            QMessageBox.warning(
                self, "الرجوع في timeshift تفاعلي",
                "timeshift --restore يطالب بالتأكيد داخل الطرفية — الأتمتة "
                "من واجهة رسومية كانت ستضغط 'y' نيابةً عنك في عملية تدميرية، "
                "وهذا يخالف فلسفة الأداة. انسخ الأمر ونفّذه في طرفية:\n\n"
                f"  sudo timeshift --restore --snapshot '{self._timeshift_date(num)}'\n\n"
                "أغلق التطبيقات واحفظ عملك قبل التنفيذ.",
            )
            return

        # تأكيد 1 من 2
        confirm1 = QMessageBox.question(
            self, "تأكيد الرجوع 1/2",
            f"سيُرجع النظام إلى اللقطة #{num} ({desc}).\n"
            "أي تغييرات بعد هذه اللقطة ستُلغى (ملفات وإعدادات وحزم).\n"
            "هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm1 != QMessageBox.Yes:
            return
        # تأكيد 2 من 2 — رسالة أخطر وأفعال No افتراضياً
        confirm2 = QMessageBox.question(
            self, "تأكيد الرجوع 2/2 — تحذير أخير",
            f"سيُنفَّذ الآن:\n  snapper -c root rollback {num}\n\n"
            "⚠ هذا إجراء حساس: لا يمكن إلغاؤه بعد التنفيذ، ويُنصح بإغلاق "
            "التطبيقات أولاً. هل تؤكد فعلاً؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm2 != QMessageBox.Yes:
            return
        self._log(f"جارٍ الرجوع إلى اللقطة #{num}...")
        self._run_bg(
            lambda: run_privileged(["snapper", "-c", "root", "rollback", num], timeout=1800),
            lambda r: self._log(
                ("تم الرجوع — أعد التشغيل للتحقق." if r.ok
                 else f"فشل الرجوع (كود {r.returncode}).") + f"\n{r.stderr[:400]}"
            ),
        )

    def _timeshift_date(self, num: str) -> str:
        """استخراج تاريخ اللقطة المطلوب لصياغة أمر timeshift الحرفي."""
        snaps, _ = list_snapshots("timeshift")
        for s in snaps:
            if s["num"] == num:
                return s["date"]
        return "<التاريخ من timeshift --list>"

    def _on_save_keep(self) -> None:
        n = self.keep_spin.value()
        if write_keep_count(n):
            self._log(f"تم الحفظ: snapper_cleanup سيحتفظ بآخر {n} لقطات.")
        else:
            self._log("فشل حفظ الإعداد (راجع اللوغ).")
