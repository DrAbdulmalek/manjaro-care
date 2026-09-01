#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/file_shredder_dialog.py — نافذة الحذف الآمن (Secure File Shredder).
مستوحاة من Ashampoo WinOptimizer / Eraser.
🔐 يدعم التشفير بالكلمة السرية قبل الحذف (Password Protect).
"""
from __future__ import annotations
import os
import random
import shutil
import tempfile
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QSpinBox, QGroupBox, QFormLayout, QFileDialog, QProgressBar,
    QLineEdit, QCheckBox, QComboBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.privilege import run_privileged
from core.logger import get_logger

log = get_logger("file_shredder_dialog")


class ShredWorker(QThread):
    progress = pyqtSignal(int)
    step = pyqtSignal(str)
    finished_ok = pyqtSignal(int, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        paths: list[str],
        passes: int = 3,
        encrypt_first: bool = False,
        password: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.paths = paths
        self.passes = passes
        self.encrypt_first = encrypt_first
        self.password = password
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            total_files = 0
            total_bytes = 0
            all_files = self._collect_files()

            if not all_files:
                self.failed.emit("لا توجد ملفات صالحة للحذف.")
                return

            # إذا كان التشفير مطلوباً، نشفر كل الملفات أولاً
            if self.encrypt_first and self.password:
                encrypted_files = []
                for i, fpath in enumerate(all_files):
                    if self._cancelled:
                        self.step.emit("❌ تم الإلغاء.")
                        break
                    pct = int((i / len(all_files)) * 50)  # النصف الأول للتشفير
                    self.progress.emit(pct)
                    self.step.emit(f"🔐 تشفير: {Path(fpath).name}")
                    enc_path = self._encrypt_file(fpath)
                    if enc_path:
                        encrypted_files.append(enc_path)
                    else:
                        self.step.emit(f"❌ فشل تشفير: {Path(fpath).name}")
                all_files = encrypted_files
                self.progress.emit(50)

            # الآن الحذف الآمن
            file_count = len(all_files)
            for i, fpath in enumerate(all_files):
                if self._cancelled:
                    self.step.emit("❌ تم الإلغاء.")
                    break

                base_pct = 50 if self.encrypt_first else 0
                pct = base_pct + int((i / file_count) * (100 - base_pct))
                self.progress.emit(pct)
                self.step.emit(f"🔥 حذف: {Path(fpath).name}")

                size = Path(fpath).stat().st_size
                if self._secure_delete(fpath):
                    total_files += 1
                    total_bytes += size
                else:
                    log.warning(f"فشل حذف: {fpath}")

            self.progress.emit(100)
            mode = "مشفرة ومحذوفة" if self.encrypt_first else "محذوفة"
            self.finished_ok.emit(total_files, f"{self._human_size(total_bytes)} ({mode})")
        except Exception as exc:
            self.failed.emit(str(exc))

    def _collect_files(self) -> list[str]:
        files = []
        for p in self.paths:
            path = Path(p)
            if not path.exists():
                continue
            if path.is_file():
                files.append(str(path))
            elif path.is_dir():
                for root, _, fnames in os.walk(path):
                    for fname in fnames:
                        fpath = Path(root) / fname
                        if fpath.is_file() and not fpath.is_symlink():
                            files.append(str(fpath))
        return files

    def _encrypt_file(self, fpath: str) -> str | None:
        """يشفر الملف بـ openssl ثم يعيد مسار الملف المشفر."""
        try:
            p = Path(fpath)
            enc_path = str(p) + ".enc"
            # openssl aes-256-cbc -salt -in file -out file.enc -pass pass:PASSWORD
            cmd = [
                "openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2",
                "-in", str(p), "-out", enc_path,
                "-pass", f"pass:{self.password}",
            ]
            r = run_privileged(cmd)
            if r.ok:
                # نحذف الأصلي فوراً بعد نجاح التشفير
                p.unlink()
                return enc_path
            return None
        except Exception as exc:
            log.error(f"encrypt error: {exc}")
            return None

    def _secure_delete(self, fpath: str) -> bool:
        try:
            p = Path(fpath)
            size = p.stat().st_size

            if size == 0:
                p.unlink()
                return True

            with open(p, "r+b") as f:
                for _ in range(self.passes):
                    if self._cancelled:
                        break
                    f.seek(0)
                    chunk_size = 1024 * 1024
                    written = 0
                    while written < size:
                        to_write = min(chunk_size, size - written)
                        f.write(os.urandom(to_write))
                        written += to_write
                    f.flush()
                    os.fsync(f.fileno())

            # إعادة تسمية عشوائية
            parent = p.parent
            for _ in range(3):
                rand_name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=16))
                new_path = parent / rand_name
                try:
                    p.rename(new_path)
                    p = new_path
                except OSError:
                    break

            p.unlink()
            return True
        except Exception as exc:
            log.error(f"secure_delete error: {exc}")
            return False

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class FileShredderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الحذف الآمن 🔒")
        self.resize(720, 600)
        self.setLayoutDirection(Qt.RightToLeft)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🔒 الحذف الآمن للملفات والمجلدات")
        f = title.font()
        f.setBold(True)
        f.setPointSize(13)
        title.setFont(f)
        layout.addWidget(title)

        info = QLabel(
            "يستبدل هذا الأداة محتوى الملفات ببيانات عشوائية ثم يحذفها نهائياً.\n"
            "🔐 يمكن تشفير الملفات أولاً بكلمة سر حتى لو استعيدت تبقى مشفرة.\n"
            "⚠️ لا يمكن استعادة الملفات بعد الحذف!"
        )
        info.setStyleSheet("color: #ff9800;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # شجرة الملفات
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "الاسم", "المسار", "الحجم"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree)

        # أزرار الملفات
        top_btns = QHBoxLayout()
        add_files_btn = QPushButton("➕ إضافة ملفات")
        add_files_btn.clicked.connect(self._add_files)
        top_btns.addWidget(add_files_btn)

        add_folder_btn = QPushButton("📁 إضافة مجلد")
        add_folder_btn.clicked.connect(self._add_folder)
        top_btns.addWidget(add_folder_btn)

        remove_btn = QPushButton("❌ إزالة المحدد")
        remove_btn.clicked.connect(self._remove_selected)
        top_btns.addWidget(remove_btn)

        clear_btn = QPushButton("🗑️ تفريغ القائمة")
        clear_btn.clicked.connect(self.tree.clear)
        top_btns.addWidget(clear_btn)
        top_btns.addStretch()
        layout.addLayout(top_btns)

        # إعدادات الحذف
        settings_group = QGroupBox("إعدادات الحذف الآمن")
        settings_layout = QFormLayout(settings_group)

        self.passes_spin = QSpinBox()
        self.passes_spin.setRange(1, 35)
        self.passes_spin.setValue(3)
        self.passes_spin.setSuffix(" مرات")
        settings_layout.addRow("عدد مرات الكتابة العشوائية:", self.passes_spin)

        # 🔐 التشفير
        self.encrypt_check = QCheckBox("🔐 تشفير الملفات أولاً قبل الحذف (Password Protect)")
        self.encrypt_check.stateChanged.connect(self._toggle_encrypt)
        settings_layout.addRow(self.encrypt_check)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("أدخل كلمة سر قوية...")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setEnabled(False)
        settings_layout.addRow("كلمة السر:", self.password_edit)

        self.confirm_password = QLineEdit()
        self.confirm_password.setPlaceholderText("أكّد كلمة السر...")
        self.confirm_password.setEchoMode(QLineEdit.Password)
        self.confirm_password.setEnabled(False)
        settings_layout.addRow("تأكيد:", self.confirm_password)

        self.algo_combo = QComboBox()
        self.algo_combo.addItems(["AES-256-CBC (openssl)"])
        self.algo_combo.setEnabled(False)
        settings_layout.addRow("خوارزمية التشفير:", self.algo_combo)

        self.total_label = QLabel("0 ملفات | 0 B")
        settings_layout.addRow("إجمالي المحدد:", self.total_label)

        layout.addWidget(settings_group)

        # شريط التقدم
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self.status_label)

        # الأزرار السفلية
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.shred_btn = QPushButton("🔥 بدء الحذف الآمن")
        self.shred_btn.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold; font-size: 12pt; padding: 8px;"
        )
        self.shred_btn.clicked.connect(self._start_shred)
        btn_row.addWidget(self.shred_btn)

        self.cancel_btn = QPushButton("إلغاء")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.cancel_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        self.tree.itemChanged.connect(self._update_totals)

    def _toggle_encrypt(self, state):
        enabled = state == Qt.Checked
        self.password_edit.setEnabled(enabled)
        self.confirm_password.setEnabled(enabled)
        self.algo_combo.setEnabled(enabled)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختر ملفات للحذف الآمن", str(Path.home()), "كل الملفات (*)"
        )
        for f in files:
            self._add_tree_item(f)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "اختر مجلد", str(Path.home()))
        if folder:
            self._add_tree_item(folder, is_dir=True)

    def _add_tree_item(self, path: str, is_dir: bool = False):
        p = Path(path)
        if not p.exists():
            return
        item = QTreeWidgetItem()
        item.setText(1, p.name + ("/" if is_dir else ""))
        item.setText(2, str(p))
        item.setText(3, self._calc_size(p))
        item.setData(1, Qt.UserRole, str(p))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        self.tree.addTopLevelItem(item)
        self._update_totals()

    def _calc_size(self, path: Path) -> str:
        try:
            if path.is_file():
                return self._hs(path.stat().st_size)
            total = 0
            for root, _, files in os.walk(path):
                for f in files:
                    fp = Path(root) / f
                    if fp.is_file():
                        total += fp.stat().st_size
            return self._hs(total)
        except Exception:
            return "—"

    def _remove_selected(self):
        for item in self.tree.selectedItems():
            idx = self.tree.indexOfTopLevelItem(item)
            self.tree.takeTopLevelItem(idx)
        self._update_totals()

    def _update_totals(self):
        count = 0
        total_size = 0
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                path = Path(item.data(1, Qt.UserRole))
                count += 1
                try:
                    if path.is_file():
                        total_size += path.stat().st_size
                    else:
                        for root, _, files in os.walk(path):
                            for f in files:
                                fp = Path(root) / f
                                if fp.is_file():
                                    total_size += fp.stat().st_size
                except Exception:
                    pass
        self.total_label.setText(f"{count} ملف/مجلد | {self._hs(total_size)}")

    def _start_shred(self):
        paths = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                paths.append(item.data(1, Qt.UserRole))

        if not paths:
            QMessageBox.warning(self, "تنبيه", "اختر ملفاً أو مجلداً على الأقل.")
            return

        passes = self.passes_spin.value()
        encrypt = self.encrypt_check.isChecked()
        password = self.password_edit.text()
        confirm = self.confirm_password.text()

        if encrypt:
            if not password:
                QMessageBox.warning(self, "تنبيه", "أدخل كلمة السر للتشفير.")
                return
            if password != confirm:
                QMessageBox.warning(self, "تنبيه", "كلمتا السر غير متطابقتين!")
                return
            if len(password) < 8:
                reply = QMessageBox.question(
                    self, "تنبيه أمني",
                    "كلمة السر أقل من 8 أحرف. هل تريد المتابعة؟",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

        mode_text = "🔐 تشفير + حذف" if encrypt else "🔥 حذف مباشر"
        reply = QMessageBox.warning(
            self, "⚠️ تنبيه نهائي",
            f"الوضع: {mode_text}\n"
            f"العناصر: {len(paths)}\n"
            f"مرات الكتابة: {passes}\n\n"
            "❌ لا يمكن التراجع عن هذا الإجراء!\n\nهل أنت متأكد تماماً؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.cancel_btn.setVisible(True)
        self.shred_btn.setEnabled(False)

        self._worker = ShredWorker(paths, passes, encrypt, password, parent=self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.step.connect(self.status_label.setText)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
        self.status_label.setText("جاري الإلغاء...")

    def _on_done(self, count: int, size: str):
        self.setEnabled(True)
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.shred_btn.setEnabled(True)
        self.tree.clear()
        self._update_totals()
        QMessageBox.information(self, "تم", f"✅ تم معالجة {count} ملف.\nالحجم: {size}")

    def _on_fail(self, err: str):
        self.setEnabled(True)
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.shred_btn.setEnabled(True)
        QMessageBox.critical(self, "خطأ", err)

    @staticmethod
    def _hs(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
