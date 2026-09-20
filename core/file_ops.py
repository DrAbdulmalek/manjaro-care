#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/file_ops.py
================
عمليات كتابة/نسخ احتياطي/استعادة آمنة للملفات النظامية التي تعدّلها
الوحدات (/etc/default/grub مثلاً) — منطق مشترك واحد بدل تكراره.

لماذا ملف جديد في core/ (قاعدة: لا نلمس core/ إلا للضرورة)؟
  ثغرة حقيقية وجُدت أثناء المراجعة: modules/boot_sanity.py كان يكتب
  نسخته المعدَّلة في مسار ثابت متوقع (/tmp/grub_default_modified) ثم
  ينسخها بصلاحيات root عبر pkexec — مستخدم محلي خبيث يمكنه إنشاء
  symlink بنفس المسار قبلاً ليوجَّه cp الجذري إلى أي ملف هدف.
  الإصلاح (ملف مؤقت عشوائي + install -m) احتاج أن يكون مشتركاً بين
  boot_sanity وboot_manager وboot_guard القادمة، فوضع هنا منطق واحد
  مُختبَر بدل ثلاث نسخ متفرقة.

ضمانات الأمان هنا:
  - النسخة الجديدة تُكتب في ملف مؤقت عشوائي (tempfile.mkstemp) وليس
    مساراً ثابتاً — يمنع هجمات symlink من مستخدم محلي.
  - الكتابة الفعلية عبر pkexec + install -m <mode> (argv صريح بلا
    shell) فتحافظ على ملكية root وصلاحيات الملف الأصلية.
  - النسخة الاحتياطية تحمل طابعاً زمنياً ولا تُكتب فوق نسخة قديمة
    أبداً، والاستعادة أمر صريح منفصل.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

from core.logger import get_logger
from core.privilege import run_privileged

log = get_logger("file_ops")


def backup_root_file(path: str) -> str | None:
    """ينشئ نسخة احتياطية بطابع زمني للملف عبر pkexec.

    يُرجع مسار النسخة الاحتياطية عند النجاح، أو None عند الفشل أو
    إن كان الملف أصلاً غير موجود (لا شيء يُنسخ احتياطياً).
    """
    if not os.path.isfile(path):
        log.warning("لا نسخة احتياطية: الملف غير موجود %s", path)
        return None
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-manjaro-care-{stamp}"
    result = run_privileged(["cp", "-a", "--", path, backup_path])
    if not result.ok:
        log.error("فشل إنشاء النسخة الاحتياطية لـ %s: %s", path, result.stderr)
        return None
    log.info("نسخة احتياطية: %s -> %s", path, backup_path)
    return backup_path


def restore_root_file(backup_path: str, target: str) -> tuple[bool, str]:
    """يستعيد نسخة احتياطية فوق الملف الأصلي عبر pkexec.

    يُرجع (نجاح, رسالة خطأ إن وُجدت).
    """
    if not os.path.isfile(backup_path):
        return False, f"النسخة الاحتياطية غير موجودة: {backup_path}"
    result = run_privileged(["cp", "-a", "--", backup_path, target])
    if not result.ok:
        return False, result.stderr or f"فشلت الاستعادة (كود {result.returncode})"
    log.info("استعادة: %s -> %s", backup_path, target)
    return True, ""


def write_root_file(path: str, content: str, mode: int = 0o644) -> tuple[bool, str]:
    """يكتب content إلى ملف مملوك للجذر بأمان.

    آلية العمل: ملف مؤقت عشوائي (بمستخدم التطبيق) ثم
    pkexec install -m <mode> (يُنشئ الملف الهدف بملكية root والصلاحية
    المطلوبة) ثم حذف المؤقت في كل الأحوال.

    يُرجع (نجاح, رسالة خطأ إن وُجدت).
    """
    fd, tmp_path = tempfile.mkstemp(prefix="manjaro-care-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        result = run_privileged(["install", "-m", f"{mode:04o}", "--", tmp_path, path])
        if not result.ok:
            return False, result.stderr or f"فشلت الكتابة (كود {result.returncode})"
        log.info("كتابة آمنة: %s (%d bytes)", path, len(content))
        return True, ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
