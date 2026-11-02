#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BootEase-inspired firmware information and explicit UEFI setup handoff."""
from __future__ import annotations

import shutil
from pathlib import Path

from PyQt5.QtCore import QProcess, Qt
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout,
)

from gui.workers import BusyCloseGuardMixin, FunctionWorker
from modules.firmware_overview import collect_firmware_report


class FirmwareOverviewDialog(BusyCloseGuardMixin, QDialog):
    _GUARD_ATTRS = ("_worker",)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("معلومات Firmware وUEFI")
        self.resize(820, 650)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        layout = QVBoxLayout(self)
        note = QLabel(
            "يعرض معلومات BIOS/UEFI واللوحة ومدخلات الإقلاع وSecure Boot. "
            "الفحص للقراءة فقط. الانتقال إلى إعدادات UEFI يعيد تشغيل الجهاز بعد تأكيدك."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("جارٍ جمع المعلومات...")
        layout.addWidget(self.report, 1)
        row = QHBoxLayout()
        self.status = QLabel("جارٍ جمع معلومات الجهاز...")
        row.addWidget(self.status)
        row.addStretch()
        self.copy_btn = QPushButton("نسخ التقرير")
        self.copy_btn.clicked.connect(self._copy_report)
        self.copy_btn.setEnabled(False)
        row.addWidget(self.copy_btn)
        self.save_btn = QPushButton("حفظ التقرير")
        self.save_btn.clicked.connect(self._save_report)
        self.save_btn.setEnabled(False)
        row.addWidget(self.save_btn)
        self.firmware_btn = QPushButton("إعادة التشغيل إلى إعدادات UEFI")
        self.firmware_btn.setToolTip("يرسل طلباً إلى النظام للدخول إلى إعدادات Firmware ثم يعيد تشغيل الجهاز.")
        self.firmware_btn.setEnabled(
            Path("/sys/firmware/efi").is_dir() and shutil.which("systemctl") is not None
        )
        self.firmware_btn.clicked.connect(self._reboot_to_firmware)
        row.addWidget(self.firmware_btn)
        close = QPushButton("إغلاق")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self._start_scan()

    def _start_scan(self):
        self._worker = FunctionWorker(collect_firmware_report, parent=self)
        self._worker.finished_ok.connect(self._show_report)
        self._worker.failed.connect(self._show_error)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _worker_finished(self):
        self.copy_btn.setEnabled(bool(self.report.toPlainText()))
        self.save_btn.setEnabled(bool(self.report.toPlainText()))

    def _show_report(self, data):
        self.report.setPlainText(str(data["report"]))
        mode = "UEFI" if data["is_uefi"] else "Legacy/غير معروف"
        self.status.setText(f"اكتمل جمع التقرير — {mode}")

    def _show_error(self, error):
        self.status.setText("فشل جمع معلومات Firmware.")
        self.report.setPlainText(error)

    def _copy_report(self):
        QApplication.clipboard().setText(self.report.toPlainText())
        self.status.setText("تم نسخ التقرير إلى الحافظة.")

    def _save_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "حفظ تقرير Firmware", "firmware-report.txt", "Text files (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self.report.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "تعذر حفظ التقرير", str(exc))
            return
        self.status.setText(f"تم حفظ التقرير: {path}")

    def _reboot_to_firmware(self):
        answer = QMessageBox.warning(
            self,
            "تأكيد إعادة التشغيل",
            "سيُعاد تشغيل الجهاز الآن لمحاولة فتح إعدادات BIOS/UEFI. "
            "احفظ جميع أعمالك وأغلق البرامج قبل المتابعة.\n\n"
            "لن يغيّر Manjaro Care ترتيب الإقلاع أو إعدادات GRUB أو متغيرات EFI؛ "
            "إنما يرسل طلباً إلى systemd لفتح إعدادات Firmware.\n\nهل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            launched = QProcess.startDetached("systemctl", ["reboot", "--firmware-setup"])
            success = launched[0] if isinstance(launched, tuple) else bool(launched)
        except Exception:
            success = False
        if not success:
            QMessageBox.warning(
                self, "تعذر إرسال الطلب",
                "لم يتمكن التطبيق من إرسال طلب إعادة التشغيل إلى إعدادات Firmware. "
                "لم يُجرِ أي تعديل على إعدادات الإقلاع.",
            )
