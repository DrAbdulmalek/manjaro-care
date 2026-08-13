#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/boot_sanity_dialog.py
==========================
نافذة تشخيص تفصيلية لفحص سلامة الإقلاع — تعرض كل خطوات التشخيص
كما هي موثّقة في manjaro-doctor/issues/grub-btrfs-snapshot-boot.md،
مع الأوامر الجاهزة للنسخ والتشغيل.

يُضاف إليها زر "اقرأ التشخيص الكامل" يفتح صفحة التوثيق على GitHub.

المرجع: https://github.com/DrAbdulmalek/manjaro-doctor
"""

from __future__ import annotations
import webbrowser

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from modules.boot_sanity import (
    DOC_URL, _script_exists, _run_script_json,
    _get_root_source, _is_booted_from_snapshot, _is_rootflags_enabled,
    _get_grub_linux_line, _grub_points_to_snapshot, _is_btrfs_system,
    _kernel_from_grub, _kernel_exists,
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

        doc_btn = QPushButton("اقرأ التشخيص الكامل")
        doc_btn.setStyleSheet("background-color: #6a1b9a;")
        doc_btn.clicked.connect(self._open_documentation)
        btn_row.addWidget(doc_btn)

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
        # إن وُجد السكربت الخارجي مع --json، نستخدمه مباشرة
        if _script_exists():
            self._run_diagnostics_from_script()
        else:
            self._run_diagnostics_fallback()

    def _run_diagnostics_from_script(self) -> None:
        """يستدعي السكربت الخارجي مع --json ويعرض النتائج المنظمة."""
        data, error = _run_script_json(fix=False)
        lines = []
        problems = 0

        lines.append("═══ مصدر الفحص: boot-sanity-check.sh --json ═══")
        lines.append("✅ السكربت الخارجي (manjaro-doctor) مُثبّت ومُستخدَم")
        lines.append("")

        if error:
            lines.append(f"⚠️ فشل استدعاء السكربت: {error}")
            lines.append("يُستخدم المنطق الداخلي كـ fallback...")
            self._run_diagnostics_fallback()
            return

        lines.append(f"مصدر الجذر: {data.get('root_source', 'غير معروف')}")
        lines.append("")

        # عرض كل مشكلة
        for p in data.get("problems", []):
            problems += 1
            icon = "❌" if p.get("severity") == "critical" else "⚠️"
            lines.append(f"{icon} [{p.get('severity', '?').upper()}] {p.get('message', '')}")
            if p.get("detail"):
                lines.append(f"   {p['detail']}")

        if problems == 0:
            lines.append("✅ لا مشاكل — نظام الإقلاع سليم.")

        lines.append("")
        lines.append(f"rootflags=subvol=@ مُفعّل: {'نعم' if data.get('preventive_fix_enabled') else 'لا'}")
        lines.append(f"يمكن الإصلاح تلقائياً: {'نعم' if data.get('can_auto_fix') else 'لا (يحتاج chroot)'}")

        self._render_result(lines, problems)

    def _run_diagnostics_fallback(self) -> None:
        """يشغّل الفحوصات باستخدام المنطق Python الداخلي (fallback)."""
        lines: list[str] = []
        problems_found = 0

        lines.append("══️ مصدر الفحص: منطق Python داخلي (fallback) ═══")
        lines.append("ℹ️ السكربت الخارجي غير مُثبّت — ثبّت manjaro-doctor للاستفادة من --json")
        lines.append("")

        is_btrfs = _is_btrfs_system()
        lines.append("═══ نوع نظام الملفات ═══")
        if is_btrfs:
            lines.append("✅ الجذر btrfs — الفحص ينطبق")
        else:
            lines.append("ℹ️ الجذر ليس btrfs — هذا الفحص لا ينطبق على نظامك")
            self._render_result(lines, 0)
            return

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

        lines.append("")
        lines.append("═══ فحص 2: الإدخال الرئيسي في grub.cfg ═══")
        linux_line = _get_grub_linux_line()
        if linux_line:
            lines.append(f"سطر linux في الإدخال الرئيسي:")
            display_line = linux_line if len(linux_line) <= 150 else linux_line[:150] + "..."
            lines.append(f"  {display_line}")

            if _grub_points_to_snapshot(linux_line):
                problems_found += 1
                lines.append("")
                lines.append("❌ مشكلة: الإدخال الرئيسي يشير إلى لقطة timeshift!")
                lines.append("   بعد التحديث، سيبحث GRUB عن النواة في اللقطة الق&oldmc; القديمة ولن يجدها.")
            else:
                lines.append("✅ الإدخال الرئيسي يشير لمسار طبيعي (ليس لقطة)")

            kernel_name = _kernel_from_grub(linux_line)
            if kernel_name:
                lines.append(f"ملف النواة المُشار إليه: /boot/{kernel_name}")
                if _kernel_exists(kernel_name):
                    lines.append(f"✅ الملف موجود")
                else:
                    problems_found += 1
                    lines.append(f"❌ الملف غير موجود! — سيفشل الإقلاع")
        else:
            lines.append("⚠️ تعذر قراءة إدخال grub الرئيسي")

        lines.append("")
        lines.append("═══ فحص 3: الحل الوقائي الدائم (rootflags=subvol=@) ═══")
        if _is_rootflags_enabled():
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

    def _open_documentation(self) -> None:
        """يفتح صفحة التوثيق الكامل على GitHub."""
        webbrowser.open(DOC_URL)

    def _copy_report(self) -> None:
        """ينسخ التقرير للحافظة."""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.detail_box.toPlainText())

    def _show_fix_instructions(self) -> None:
        """يعرض تعليمات الإصلاح التفصيلية."""
        instructions = """═══════════════════════════════════════════════════════
 تعليمات الإصلاح — حسب حالة النظام
═══════════════════════════════════════════════════════

الحالة 1: النظام يعمل من داخل لقطة (findmnt / يُظهر timeshift-btrfs/snapshots)
─────────────────────────────────────────────────────────
لا يمكن إصلاحها تلقائياً من الجلسة الحالية.
يجب الإصلاح عبر arch-chroot إلى @ الحقيقي:

  sudo mount -o subvol=@ /dev/sdXN /mnt/realroot
  sudo mount -o subvol=@home /dev/sdXN /mnt/realroot/home
  sudo mount -o subvol=@cache /dev/sdXN /mnt/realroot/var/cache
  sudo mount -o subvol=@log /dev/sdXN /mnt/realroot/var/log
  sudo mount /dev/sdXN1 /mnt/realroot/boot/efi
  sudo arch-chroot /mnt/realroot
  pacman -S linuxXXX --overwrite '*'
  mkinitcpio -P
  grub-mkconfig -o /boot/grub/grub.cfg
  exit
  sudo umount -R /mnt/realroot
  sudo reboot


الحالة 2: النظام على @ الحقيقي لكن grub.cfg يشير للقطة
─────────────────────────────────────────────────────────
يمكن إصلاحها بزر "تطبيق" في البطاقة الرئيسية:
  - يُفعّل rootflags=subvol=@ في /etc/default/grub
  - يُعيد توليد grub.cfg
  - أعد التشغيل وتحقق بـ: findmnt /


الحل النهائي الدائم:
─────────────────────
أضف rootflags=subvol=@ إلى GRUB_CMDLINE_LINUX_DEFAULT:
  GRUB_CMDLINE_LINUX_DEFAULT='quiet splash udev.log_priority=3 rootflags=subvol=@'
  sudo grub-mkconfig -o /boot/grub/grub.cfg
  sudo reboot

التحقق: findmnt / يجب أن يُظهر /dev/sdXN[/@] دائماً.

═══════════════════════════════════════════════════════
 التوثيق الكامل: github.com/DrAbdulmalek/manjaro-doctor
═══════════════════════════════════════════════════════"""
        self.detail_box.setPlainText(instructions)
