#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/boot_sanity_dialog.py
==========================
نافذة تشخيص تفصيلية لفحص سلامة الإقلاع — تعرض كل خطوات التشخيص
كما هي موثّقة في manjaro-doctor/issues/grub-btrfs-snapshot-boot.md،
مع الأوامر الجاهزة للنسخ والتشغيل.

هذه النافذة تُسجَّل في gui/custom_dialogs.py وتُفتح بزر "تشخيص تفصيلي"
على بطاقة boot_sanity في الواجهة الرئيسية.

المرجع: https://github.com/DrAbdulmalek/manjaro-doctor
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QClipboard, QApplication

from modules.boot_sanity import (
    _get_root_source, _is_booted_from_snapshot,
    _is_rootflags_protection_enabled, _get_main_grub_entry_linux_line,
    _grub_entry_points_to_snapshot, _is_btrfs_system,
    _get_kernel_from_grub_entry, _kernel_file_exists,
)


class BootSanityDialog(QDialog):
    """نافذة تشخيص تفصيلي لسلامة الإقلاع."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تشخيص سلامة الإقلاع — التفاصيل الكاملة")
        self.resize(720, 600)
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self._run_diagnostics()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── العنوان ──
        title = QLabel("تشخيص سلامة الإقلاع (btrfs + GRUB)")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        # ── ملخص سريع ──
        self.summary_group = QGroupBox("الملخص")
        self.summary_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #4a4a4a; "
            "border-radius: 8px; margin-top: 10px; padding-top: 18px; }"
        )
        summary_layout = QVBoxLayout()
        self.summary_label = QLabel("جارٍ الفحص...")
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        self.summary_group.setLayout(summary_layout)
        root.addWidget(self.summary_group)

        # ── تفاصيل التشخيص ──
        self.detail_box = QTextEdit()
        self.detail_box.setReadOnly(True)
        self.detail_box.setStyleSheet(
            "background-color: #1a1a1a; color: #d4d4d4; "
            "font-family: 'Noto Sans Arabic', 'Noto Sans', monospace; font-size: 10pt; "
            "border: 1px solid #3d3d3d; border-radius: 8px; padding: 10px;"
        )
        self.detail_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.detail_box, stretch=1)

        # ── أزرار ──
        btn_row = QHBoxLayout()

        copy_btn = QPushButton("نسخ التقرير")
        copy_btn.setStyleSheet("background-color: #1565c0;")
        copy_btn.clicked.connect(self._copy_report)
        btn_row.addWidget(copy_btn)

        fix_btn = QPushButton("تعليمات الإصلاح")
        fix_btn.setStyleSheet("background-color: #2e7d32;")
        fix_btn.clicked.connect(self._show_fix_instructions)
        btn_row.addWidget(fix_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    def _run_diagnostics(self) -> None:
        """يشغّل كل الفحوصات ويعرض النتائج."""
        lines: list[str] = []
        problems_found = 0

        # ── هل النظام btrfs؟ ──
        is_btrfs = _is_btrfs_system()
        lines.append("═══ نوع نظام الملفات ═══")
        if is_btrfs:
            lines.append("✅ الجذر btrfs — الفحص ينطبق")
        else:
            lines.append("ℹ️ الجذر ليس btrfs — هذا الفحص لا ينطبق على نظامك")
            self._render_result(lines, 0)
            return

        # ── فحص 1: مصدر الجذر ──
        lines.append("")
        lines.append("═══ فحص 1: مصدر الجذر الحالي ═══")
        root_source = _get_root_source()
        lines.append(f"الأمر: findmnt -no SOURCE /")
        lines.append(f"النتيجة: {root_source}")

        booted_from_snapshot = _is_booted_from_snapshot(root_source)
        if booted_from_snapshot:
            problems_found += 1
            lines.append("")
            lines.append("❌ مشكلة حرجة: النظام يعمل من داخل لقطة timeshift!")
            lines.append("   هذا يعني أن كل تحديثات pacman تُكتب داخل اللقطة وليس في @.")
            lines.append("   يجب الإصلاح عبر arch-chroot إلى @ الحقيقي.")
        else:
            lines.append("✅ الجذر يعمل من subvolume حقيقي (ليس لقطة)")

        # ── فحص 2: إدخال grub الرئيسي ──
        lines.append("")
        lines.append("═══ فحص 2: الإدخال الرئيسي في grub.cfg ═══")
        linux_line = _get_main_grub_entry_linux_line()
        if linux_line:
            lines.append(f"سطر linux في الإدخال الرئيسي:")
            # نعرض أول 150 حرف فقط لمنع السطر الطويل جداً
            display_line = linux_line if len(linux_line) <= 150 else linux_line[:150] + "..."
            lines.append(f"  {display_line}")

            if _grub_entry_points_to_snapshot(linux_line):
                problems_found += 1
                lines.append("")
                lines.append("❌ مشكلة: الإدخال الرئيسي يشير إلى لقطة timeshift!")
                lines.append("   بعد التحديث، سيبحث GRUB عن النواة في اللقطة القديمة ولن يجدها.")
            else:
                lines.append("✅ الإدخال الرئيسي يشير لمسار طبيعي (ليس لقطة)")

            # فحص ملف النواة
            kernel_name = _get_kernel_from_grub_entry(linux_line)
            if kernel_name:
                lines.append(f"ملف النواة المُشار إليه: /boot/{kernel_name}")
                if _kernel_file_exists(kernel_name):
                    lines.append(f"✅ الملف موجود")
                else:
                    problems_found += 1
                    lines.append(f"❌ الملف غير موجود! — سيفشل الإقلاع")
        else:
            lines.append("⚠️ تعذر قراءة إدخال grub الرئيسي")

        # ── فحص 3: الحل الوقائي الدائم ──
        lines.append("")
        lines.append("═══ فحص 3: الحل الوقائي الدائم (rootflags=subvol=@) ═══")
        if _is_rootflags_protection_enabled():
            lines.append("✅ rootflags=subvol=@ مُفعّل في GRUB_CMDLINE_LINUX_DEFAULT")
            lines.append("   هذا يمنع تكرار المشكلة حتى لو أخطأت grub-mkconfig مستقبلاً.")
        else:
            problems_found += 1
            lines.append("⚠️ rootflags=subvol=@ غير مُفعّل بعد")
            lines.append("   أضفه إلى GRUB_CMDLINE_LINUX_DEFAULT في /etc/default/grub:")
            lines.append("   GRUB_CMDLINE_LINUX_DEFAULT='quiet splash udev.log_priority=3 rootflags=subvol=@'")
            lines.append("   ثم: sudo grub-mkconfig -o /boot/grub/grub.cfg")

        self._render_result(lines, problems_found)

    def _render_result(self, lines: list[str], problems: int) -> None:
        """يعرض النتائج في النافذة."""
        self.detail_box.setPlainText("\n".join(lines))

        if problems == 0:
            self.summary_label.setText("✅ لا مشاكل — نظام الإقلاع سليم.")
            self.summary_label.setStyleSheet("color: #66bb6a; font-weight: bold;")
            self.summary_group.setStyleSheet(
                self.summary_group.styleSheet() + "QGroupBox { border-color: #2e7d32; }"
            )
        else:
            self.summary_label.setText(
                f"❌ {problems} مشكلة موجودة — راجع التفاصيل أدناه واستخدم 'تعليمات الإصلاح'."
            )
            self.summary_label.setStyleSheet("color: #ef5350; font-weight: bold;")
            self.summary_group.setStyleSheet(
                self.summary_group.styleSheet() + "QGroupBox { border-color: #c62828; }"
            )

    def _copy_report(self) -> None:
        """ينسخ التقرير للحافظة."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.detail_box.toPlainText())

    def _show_fix_instructions(self) -> None:
        """يعرض تعليمات الإصلاح التفصيلية (من manjaro-doctor)."""
        instructions = """═══════════════════════════════════════════════════════
 تعليمات الإصلاح — حسب حالة النظام
═══════════════════════════════════════════════════════

الحالة 1: النظام يعمل من داخل لقطة (findmnt / يُظهر timeshift-btrfs/snapshots)
─────────────────────────────────────────────────────────
هذه الحالة لا يمكن إصلاحها تلقائياً من الجلسة الحالية.
يجب الإصلاح عبر arch-chroot إلى @ الحقيقي:

  # 1. ركّب subvolumes الضرورية
  sudo mount -o subvol=@ /dev/sdXN /mnt/realroot
  sudo mount -o subvol=@home /dev/sdXN /mnt/realroot/home
  sudo mount -o subvol=@cache /dev/sdXN /mnt/realroot/var/cache
  sudo mount -o subvol=@log /dev/sdXN /mnt/realroot/var/log
  sudo mount /dev/sdXN1 /mnt/realroot/boot/efi

  # 2. ادخل chroot
  sudo arch-chroot /mnt/realroot

  # 3. أعد تثبيت النواة بالقوة
  pacman -S linuxXXX --overwrite '*'    # غيّر XXX حسب نواتك (مثلاً linux618)

  # 4. أعد بناء initramfs و grub
  mkinitcpio -P
  grub-mkconfig -o /boot/grub/grub.cfg
  exit

  # 5. أعد التشغيل
  sudo umount -R /mnt/realroot
  sudo reboot


الحالة 2: النظام على @ الحقيقي لكن grub.cfg يشير للقطة
─────────────────────────────────────────────────────────
هذه يمكن إصلاحها بزر "تطبيق" في البطاقة الرئيسية:
  - يُفعّل rootflags=subvol=@ في /etc/default/grub
  - يُعيد توليد grub.cfg
  - أعد التشغيل وتحقق بـ: findmnt /


الحل النهائي الدائم (يمنع تكرار المشكلة نهائياً):
─────────────────────────────────────────────────────
أضف rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT:

  sudo nano /etc/default/grub
  # غيّر السطر إلى:
  GRUB_CMDLINE_LINUX_DEFAULT='quiet splash udev.log_priority=3 rootflags=subvol=@'

  sudo grub-mkconfig -o /boot/grub/grub.cfg
  sudo reboot

التحقق: findmnt / يجب أن يُظهر /dev/sdXN[/@] دائماً.

═══════════════════════════════════════════════════════
 المرجع: github.com/DrAbdulmalek/manjaro-doctor
═══════════════════════════════════════════════════════"""
        self.detail_box.setPlainText(instructions)
