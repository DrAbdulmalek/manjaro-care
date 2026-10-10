#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui/update_check_dialog.py — نافذة «إدارة فردية» لمؤشرات دورة
التحديث: قائمة ملفات .pacnew/.pacsave مع زر عرض الفرق (قراءة فقط)
لكل ملف، وقائمة الخدمات الفاشلة، وأخبار مانجارو.

ملاحظة: لا يوجد هنا أي زر دمج/حذف — عرض الفروق فقط (قراءة فقط)."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.logger import get_logger
from core.privilege import run_unprivileged
from gui.workers import FunctionWorker
from modules.update_check import (
    _find_pacnew_files,
    _get_failed_units,
    fetch_news_titles,
)

log = get_logger("update_check_dialog")


class UpdateCheckDialog(QDialog):
    """عرض الفروق المعلقة + الخدمات الفاشلة + الأخبار — كل القراءة فقط."""

    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self._worker: FunctionWorker | None = None
        self.setWindowTitle(f"{module.name} — إدارة فردية")
        self.resize(680, 520)
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self._load_pacnew()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        note = QLabel(
            "قراءة فقط — لا يوجد دمج أو حذف تلقائي لملفات .pacnew. "
            "راجع كل فرق وقرر بنفسك (pacman -Qo <الملف> يخبرك بمالكه)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #ffca28;")
        layout.addWidget(note)

        # ---- قائمة الملفات المعلقة + أزرار الفروق ----
        pacnew_group = QGroupBox("ملفات .pacnew/.pacsave المعلقة")
        pg_layout = QVBoxLayout(pacnew_group)
        self.pacnew_list = QListWidget()
        pg_layout.addWidget(self.pacnew_list)
        diff_row = QHBoxLayout()
        diff_btn = QPushButton("عرض الفرق (diff -u — قراءة فقط)")
        diff_btn.clicked.connect(self._on_show_diff)
        diff_row.addWidget(diff_btn)
        diff_row.addStretch()
        pg_layout.addLayout(diff_row)
        layout.addWidget(pacnew_group)

        # ---- منطقة المخرجات ----
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "background-color: #1e1e1e; color: #9fdc9f; "
            "font-family: monospace; font-size: 9pt;"
        )
        layout.addWidget(self.output, stretch=1)

        # ---- الخدمات الفاشلة + الأخبار ----
        info_row = QHBoxLayout()
        failed_btn = QPushButton("الخدمات الفاشلة (systemctl --failed)")
        failed_btn.clicked.connect(self._on_show_failed)
        info_row.addWidget(failed_btn)
        news_btn = QPushButton("أخبار مانجارو (إن توفرت الشبكة)")
        news_btn.clicked.connect(self._on_show_news)
        info_row.addWidget(news_btn)
        info_row.addStretch()
        layout.addLayout(info_row)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ------------------------------------------------------------------
    def _load_pacnew(self) -> None:
        self.pacnew_list.clear()
        for path in _find_pacnew_files():
            self.pacnew_list.addItem(path)
        if not self.pacnew_list.count():
            self.output.setPlainText("لا ملفات .pacnew/.pacsave معلقة — كل الإعدادات مدمجة.")

    def _log(self, text: str) -> None:
        self.output.append(text)

    def _run_bg(self, func, on_done) -> None:
        self._worker = FunctionWorker(func)
        self._worker.finished_ok.connect(on_done)
        self._worker.failed.connect(lambda e: self._log(f"خطأ: {e}"))
        self._worker.start()

    # ------------------------------------------------------------------
    def _on_show_diff(self) -> None:
        """عرض فرق .pacnew — أمر قراءة فقط عبر argv، بلا أي صلاحيات
        مرتفعة ولا أي كتابة."""
        selected = self.pacnew_list.currentItem()
        if selected is None:
            QMessageBox.information(self, "لا تحديد", "حدّد ملفاً من القائمة أولاً.")
            return
        path = selected.text()
        if not path.endswith(".pacnew"):
            self._log(f"{path}: نسخة محفوظة (.pacsave) — لا ملف أصلي يقارن به.")
            return
        base = path[: -len(".pacnew")]

        def read_diff():
            return run_unprivileged(["diff", "-u", base, path], timeout=30)

        def show(result):
            # diff يُرجع 1 عند وجود فروق — ليس خطأ
            if result.returncode in (0, 1):
                self._log(f"$ diff -u {base} {path}\n{result.stdout or '(لا فروق)'}")
            else:
                self._log(f"فشل diff (كود {result.returncode}): {result.stderr}")

        self._log(f"جارٍ قراءة فرق {path}...")
        self._run_bg(read_diff, show)

    def _on_show_failed(self) -> None:
        units = _get_failed_units()
        self._log("الخدمات الفاشلة:\n" + ("\n".join(f"  • {u}" for u in units)
                                          if units else "  لا خدمات فاشلة ✅"))

    def _on_show_news(self) -> None:
        def do_fetch():
            return fetch_news_titles()

        def show(packed):
            titles, error = packed
            if titles:
                self._log("آخر أخبار مانجارو:\n" + "\n".join(f"  • {t}" for t in titles))
            else:
                self._log(f"تعذر جلب الأخبار ({error}) — جرّب لاحقاً أو زر الرابط مباشرة.")
        self._log("جارٍ جلب الأخبار (مهلة 3 ثوانٍ)...")
        self._run_bg(do_fetch, show)
