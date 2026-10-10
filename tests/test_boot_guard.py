#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_boot_guard.py — اختبارات حارس الإقلاع (المهمة 1).

تغطي الحالات الإلزامية من مواصفة المهمة:
  1) نظام غير btrfs        → حالة "غير قابل للتطبيق" لا خطأ.
  2) subvol صحيح           → scan سليم، لا إجراء مقترح.
  3) subvol خاطئ           → scan حرج، معاينة تعرض التصحيح، apply يصلح.
  4) فشل grub-mkconfig     → استعادة تلقائية للنسخة الاحتياطية.

ولا ينفَّذ أي أمر حقيقي: كل subprocess وكل قراءة ملفات نظام وهمية.
"""
from __future__ import annotations

from unittest.mock import patch

from core.module_base import Severity
from core.privilege import CommandResult
from modules import boot_guard
from modules.boot_guard import (
    BootGuardModule,
    _analyze_grub_default,
    _build_grub_default_edit,
    _parse_root_mount,
    _scan_grub_cfg_snapshot_lines,
)

PROC_MOUNTS_BTRFS = (
    "UUID=xxx / btrfs rw,relatime,ssd,subvol=/@ 0 0\n"
    "UUID=yyy /.snapshots btrfs rw,subvol=/@/.snapshots 0 0\n"
)
PROC_MOUNTS_EXT4 = "UUID=xxx / ext4 rw,relatime 0 0\n"
PROC_MOUNTS_NO_SUBVOL = "UUID=xxx / btrfs rw,relatime 0 0\n"

GRUB_OK = (
    "GRUB_TIMEOUT=5\n"
    'GRUB_DISTRIBUTOR="Manjaro"\n'
    'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash rootflags=subvol=@"\n'
    'GRUB_CMDLINE_LINUX=""\n'
)
GRUB_MISSING_FLAGS = GRUB_OK.replace(" rootflags=subvol=@", "")
GRUB_WRONG_FLAGS = GRUB_OK.replace("rootflags=subvol=@", "rootflags=subvol=/@/.snapshots/42")

GRUB_CFG_CLEAN = (
    "menuentry 'Manjaro Linux' --class manjaro {\n"
    "  linux /boot/vmlinuz-6.6 root=UUID=xxx rw rootflags=subvol=@ quiet\n"
    "}\n"
)
GRUB_CFG_SNAPSHOT = (
    "menuentry 'Manjaro Linux' --class manjaro {\n"
    "  linux /@/.snapshots/42/snapshot/boot/vmlinuz-6.6 root=UUID=xxx rw rootflags=subvol=/@/.snapshots/42\n"
    "}\n"
)


def _patch_env(module, mounts=PROC_MOUNTS_BTRFS, grub_default=GRUB_MISSING_FLAGS,
               grub_cfg=GRUB_CFG_CLEAN):
    """تجهيز بيئة وهمية متكاملة لقراءات الملفات داخل boot_guard."""
    def fake_read(path):
        if path == boot_guard.PROC_MOUNTS:
            return mounts
        if path == boot_guard.GRUB_DEFAULT:
            return grub_default
        if path == boot_guard.GRUB_CFG:
            return grub_cfg
        return None
    return patch.object(module, "_read_text", side_effect=fake_read)


# ---------------------------------------------------------------------------
# المحللات النقية
# ---------------------------------------------------------------------------

class TestParsers:
    def test_parse_root_mount_btrfs_with_subvol(self):
        fstype, subvol = _parse_root_mount(PROC_MOUNTS_BTRFS)
        assert fstype == "btrfs"
        assert subvol == "@"  # منزوعة شرطة البداية لتطابق عرف GRUB

    def test_parse_root_mount_no_subvol_option(self):
        fstype, subvol = _parse_root_mount(PROC_MOUNTS_NO_SUBVOL)
        assert fstype == "btrfs"
        assert subvol is None

    def test_parse_root_mount_empty(self):
        assert _parse_root_mount("") == (None, None)

    def test_scan_grub_cfg_finds_snapshot_lines(self):
        hits = _scan_grub_cfg_snapshot_lines(GRUB_CFG_SNAPSHOT)
        assert len(hits) == 1
        assert hits[0][0] == 2  # رقم السطر
        assert ".snapshots" in hits[0][1]

    def test_scan_grub_cfg_clean_file(self):
        assert _scan_grub_cfg_snapshot_lines(GRUB_CFG_CLEAN) == []

    def test_analyze_grub_default_ok(self):
        a = _analyze_grub_default(GRUB_OK, "@")
        assert a["default_ok"] and a["needs_edit"] is False

    def test_analyze_grub_default_wrong_subvol(self):
        a = _analyze_grub_default(GRUB_WRONG_FLAGS, "@")
        assert a["default_wrong"] and a["needs_edit"] is True

    def test_analyze_grub_default_no_vars_at_all(self):
        a = _analyze_grub_default("GRUB_TIMEOUT=5\n", "@")
        assert a["any_var"] is False
        assert a["editable"] is False  # رفض الإصلاح الآلي

    def test_build_edit_appends_inside_quotes(self):
        new = _build_grub_default_edit(GRUB_MISSING_FLAGS, "@")
        assert new is not None
        assert 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash rootflags=subvol=@"' in new
        # لم يُلمس باقي الملف
        assert "GRUB_TIMEOUT=5" in new and 'GRUB_DISTRIBUTOR="Manjaro"' in new
        # double-quote style preserved on both cmdline lines
        assert 'GRUB_CMDLINE_LINUX=""' in new

    def test_build_edit_replaces_wrong_subvol_token(self):
        new = _build_grub_default_edit(GRUB_WRONG_FLAGS, "@")
        assert "rootflags=subvol=@" in new
        assert ".snapshots" not in new

    def test_build_edit_no_change_returns_none(self):
        assert _build_grub_default_edit(GRUB_OK, "@") is None


# ---------------------------------------------------------------------------
# scan() — الحالات الإلزامية
# ---------------------------------------------------------------------------

class TestScan:
    def setup_method(self):
        self.module = BootGuardModule()

    def test_non_btrfs_is_not_applicable_not_error(self):
        with _patch_env(boot_guard, mounts=PROC_MOUNTS_EXT4):
            result = self.module.scan()
        assert result.error is None  # ليست حالة خطأ
        assert "غير قابل للتطبيق" in result.findings[0].title

    def test_correct_subvol_all_clean(self):
        with _patch_env(boot_guard, grub_default=GRUB_OK, grub_cfg=GRUB_CFG_CLEAN):
            result = self.module.scan()
        severities = {f.severity for f in result.findings}
        assert Severity.CRITICAL not in severities and Severity.WARNING not in severities
        assert any("مُفعّل" in f.title for f in result.findings)

    def test_wrong_subvol_is_critical(self):
        with _patch_env(boot_guard, grub_default=GRUB_WRONG_FLAGS, grub_cfg=GRUB_CFG_SNAPSHOT):
            result = self.module.scan()
        assert result.worst_severity == Severity.CRITICAL
        assert any(f.actionable for f in result.findings)

    def test_no_subvol_refuses(self):
        with _patch_env(boot_guard, mounts=PROC_MOUNTS_NO_SUBVOL):
            result = self.module.scan()
        assert any("subvolume غير محدد" in f.title for f in result.findings)
        assert not any(f.actionable for f in result.findings)

    def test_booted_from_snapshot_refuses(self):
        snapshot_mounts = "UUID=x / btrfs rw,subvol=/@/.snapshots/42 0 0\n"
        with _patch_env(boot_guard, mounts=snapshot_mounts):
            result = self.module.scan()
        assert result.worst_severity == Severity.CRITICAL
        assert "من داخل لقطة" in result.findings[0].title
        assert not any(f.actionable for f in result.findings)

    def test_snapshot_lines_in_grub_cfg_detected(self):
        with _patch_env(boot_guard, grub_default=GRUB_OK, grub_cfg=GRUB_CFG_SNAPSHOT):
            result = self.module.scan()
        assert result.worst_severity == Severity.CRITICAL
        assert any("grub.cfg" in f.title for f in result.findings)


# ---------------------------------------------------------------------------
# preview() / apply()
# ---------------------------------------------------------------------------

class TestPreviewAndApply:
    def setup_method(self):
        self.module = BootGuardModule()

    def test_preview_shows_diff_and_actual_commands(self):
        with _patch_env(boot_guard, grub_default=GRUB_MISSING_FLAGS):
            steps = self.module.preview()
        text = "\n".join(s.description + str(s.command) for s in steps)
        assert "rootflags=subvol=@" in text          # الفرق المقترح ظاهر
        assert "grub-mkconfig -o /boot/grub/grub.cfg" in text  # الأمر الفعلي حرفياً
        assert "نسخة احتياطية" in text

    def test_preview_no_action_when_clean(self):
        with _patch_env(boot_guard, grub_default=GRUB_OK):
            steps = self.module.preview()
        assert any("لا توجد مشكلة" in s.description for s in steps)

    def test_apply_non_btrfs_is_not_applicable(self):
        with _patch_env(boot_guard, mounts=PROC_MOUNTS_EXT4):
            result = self.module.apply()
        assert "غير قابل للتطبيق" in result.message

    def test_apply_correct_subvol_noop(self):
        with _patch_env(boot_guard, grub_default=GRUB_OK), \
             patch.object(boot_guard, "backup_root_file") as m_backup:
            result = self.module.apply()
        m_backup.assert_not_called()  # لا تعديل — لا نسخة احتياطية
        assert result.success
        assert "لم يُنفَّذ أي شيء" in result.message  # no-op صادق

    def test_apply_wrong_subvol_edits_and_verifies(self):
        captured = {}

        def fake_write(path, content, mode=0o644):
            captured["content"] = content
            return True, ""

        with _patch_env(boot_guard, grub_default=GRUB_WRONG_FLAGS), \
             patch.object(boot_guard, "backup_root_file", return_value="/etc/default/grub.bak-manjaro-care-x"), \
             patch.object(boot_guard, "write_root_file", side_effect=fake_write), \
             patch.object(boot_guard, "run_privileged",
                          return_value=CommandResult(0, "regen ok", "")):
            result = self.module.apply()

        assert result.success
        assert "rootflags=subvol=@" in captured["content"]
        assert ".snapshots" not in captured["content"]
        assert "/etc/default/grub.bak-manjaro-care-x" in result.message

    def test_apply_grub_mkconfig_failure_rolls_back(self):
        """الحالة الإلزامية: فشل grub-mkconfig ← استعادة النسخة الاحتياطية."""
        restored = {}

        def fake_restore(backup, target):
            restored["pair"] = (backup, target)
            return True, ""

        with _patch_env(boot_guard, grub_default=GRUB_MISSING_FLAGS), \
             patch.object(boot_guard, "backup_root_file", return_value="/etc/default/grub.bak-manjaro-care-x"), \
             patch.object(boot_guard, "write_root_file", return_value=(True, "")), \
             patch.object(boot_guard, "run_privileged",
                          return_value=CommandResult(1, "", "grub-mkconfig exploded")), \
             patch.object(boot_guard, "restore_root_file", side_effect=fake_restore):
            result = self.module.apply()

        assert not result.success
        assert restored["pair"] == ("/etc/default/grub.bak-manjaro-care-x", boot_guard.GRUB_DEFAULT)
        assert "استُعيدت النسخة الاحتياطية" in result.message

    def test_apply_backup_failure_refuses(self):
        """لا نسخة احتياطية = لا تعديل (شرط إلزامي)."""
        with _patch_env(boot_guard, grub_default=GRUB_MISSING_FLAGS), \
             patch.object(boot_guard, "backup_root_file", return_value=None), \
             patch.object(boot_guard, "write_root_file") as m_write:
            result = self.module.apply()
        m_write.assert_not_called()
        assert not result.success
        assert "نسخة احتياطية" in result.message

    def test_apply_dry_run_short_circuit(self):
        """وضع dry-run: رسالة صادقة دون أي أمر أو كتابة."""
        from core.runtime import set_dry_run

        set_dry_run(True)
        try:
            with _patch_env(boot_guard, grub_default=GRUB_WRONG_FLAGS), \
                 patch.object(boot_guard, "backup_root_file") as m_backup, \
                 patch.object(boot_guard, "run_privileged") as m_run:
                result = self.module.apply()
        finally:
            set_dry_run(False)
        m_backup.assert_not_called()
        m_run.assert_not_called()
        assert "[DRY-RUN]" in result.message
