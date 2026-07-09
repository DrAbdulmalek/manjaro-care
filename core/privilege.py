#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/privilege.py
==================
طبقة موحّدة لتنفيذ الأوامر التي تحتاج صلاحيات جذر، عبر polkit (pkexec)
حصراً — بنفس فلسفة reset-net الأصلية: لا نعدّل /etc/sudoers.d تلقائياً،
polkit يعطي مصادقة رسومية واحدة والمستخدم يبقى مطّلعاً على كل استدعاء.

كل وحدة تستدعي run_privileged() بدل استدعاء subprocess مباشرة، حتى:
  - يكون هناك سجل مركزي لكل أمر نُفّذ بصلاحيات مرتفعة
  - يسهل لاحقاً استبدال pkexec بآلية أخرى (polkit action مخصص) دون
    تعديل كل وحدة على حدة
"""

from __future__ import annotations
import shutil
import subprocess
from dataclasses import dataclass

from core.logger import get_logger

log = get_logger("privilege")


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _pkexec_available() -> bool:
    return shutil.which("pkexec") is not None


def run_unprivileged(args: list[str], timeout: int = 30) -> CommandResult:
    """تنفيذ أمر عادي بلا صلاحيات مرتفعة (فحوصات القراءة مثلاً)."""
    log.debug("تنفيذ أمر عادي: %s", " ".join(args))
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError as e:
        log.error("الأمر غير موجود: %s", args[0])
        return CommandResult(127, "", str(e))
    except subprocess.TimeoutExpired:
        log.error("انتهت مهلة الأمر: %s", " ".join(args))
        return CommandResult(124, "", "timeout")


def run_privileged(args: list[str], timeout: int = 120) -> CommandResult:
    """
    تنفيذ أمر بصلاحيات جذر عبر pkexec. يفتح نافذة مصادقة polkit
    الرسومية (نفس ما اعتاده المستخدم من تطبيقات KDE الأخرى).
    """
    if not _pkexec_available():
        msg = "الأداة pkexec غير مثبتة — مطلوبة لتنفيذ أي إجراء بصلاحيات جذر."
        log.error(msg)
        return CommandResult(127, "", msg)

    full_cmd = ["pkexec", *args]
    log.info("تنفيذ أمر مرتفع الصلاحية: %s", " ".join(args))
    try:
        proc = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode == 0:
            log.info("نجح: %s", " ".join(args))
        else:
            log.warning(
                "فشل (%s): %s — %s", proc.returncode, " ".join(args), proc.stderr.strip()
            )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        log.error("انتهت مهلة الأمر المرتفع: %s", " ".join(args))
        return CommandResult(124, "", "timeout")
