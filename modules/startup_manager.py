#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/startup_manager.py
=============================
يسرد برامج بدء التشغيل (autostart) من:
  - ~/.config/autostart/           (خاصة بالمستخدم الحالي، لها الأولوية)
  - /etc/xdg/autostart/            (عامة لكل المستخدمين)

يدعم تفعيل/تعطيل كل برنامج على حدة، باتّباع معيار freedesktop.org
Desktop Application Autostart Specification:

  - لتعديل ملف مستخدم (~/.config/autostart/x.desktop): نُعدّل مفتاح
    Hidden فيه مباشرة.
  - لتعطيل ملف نظام (/etc/xdg/autostart/x.desktop) دون صلاحيات جذر:
    نُنشئ ملف "تجاوز" (override) بنفس الاسم في ~/.config/autostart/
    يحتوي Hidden=true — وهذا هو التصرف القياسي المعرَّف في المواصفة
    نفسها (ملف المستخدم يُقدَّم دائماً على ملف النظام بنفس الاسم).
  - لإعادة تفعيل ملف نظام تم تعطيله: نحذف ملف التجاوز، فيعود الاعتماد
    على ملف النظام الأصلي (المفعَّل افتراضياً).

لا حاجة لـ pkexec هنا إطلاقاً — كل التعديلات تتم في مجلد المستخدم
فقط، تماماً كما تفعل بيئات سطح المكتب نفسها (GNOME Tweaks, KDE
الإعدادات) دون طلب كلمة مرور.
"""

from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import configparser
import shutil

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.logger import get_logger

log = get_logger("startup_manager")

_USER_AUTOSTART = Path.home() / ".config" / "autostart"
_SYSTEM_AUTOSTART = Path("/etc/xdg/autostart")


@dataclass(frozen=True)
class AutostartEntry:
    """تمثيل موحّد لبرنامج بدء تشغيل واحد، بغض النظر عن مصدره."""
    basename: str          # اسم الملف (مثل 'telegram.desktop') — المعرّف الفريد
    display_name: str      # الاسم المعروض للمستخدم (من مفتاح Name)
    enabled: bool
    is_system: bool        # True إن كان المصدر الفعّال حالياً ملف نظام (لا يوجد تجاوز مستخدم)
    comment: str = ""


def _read_desktop_entry(path: Path) -> tuple[str, bool, str] | None:
    """يُرجع (الاسم المعروض, مفعّل؟, تعليق) أو None إن تعذّرت القراءة."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return None
    if "Desktop Entry" not in parser:
        return None
    section = parser["Desktop Entry"]
    name = section.get("Name", path.stem)
    comment = section.get("Comment", "")
    hidden = section.getboolean("Hidden", fallback=False)
    no_display = section.getboolean("NoDisplay", fallback=False)
    return name, not (hidden or no_display), comment


def list_entries() -> list[AutostartEntry]:
    """
    يجمع كل برامج بدء التشغيل الفعّالة، بحيث ملف المستخدم يُقدَّم دائماً
    على ملف نظام بنفس الاسم (نفس منطق freedesktop.org).
    """
    by_basename: dict[str, AutostartEntry] = {}

    if _SYSTEM_AUTOSTART.is_dir():
        for file in sorted(_SYSTEM_AUTOSTART.glob("*.desktop")):
            parsed = _read_desktop_entry(file)
            if parsed:
                name, enabled, comment = parsed
                by_basename[file.name] = AutostartEntry(
                    basename=file.name, display_name=name,
                    enabled=enabled, is_system=True, comment=comment,
                )

    if _USER_AUTOSTART.is_dir():
        for file in sorted(_USER_AUTOSTART.glob("*.desktop")):
            parsed = _read_desktop_entry(file)
            if parsed:
                name, enabled, comment = parsed
                # ملف المستخدم يُلغي (يُقدَّم على) أي ملف نظام بنفس الاسم
                by_basename[file.name] = AutostartEntry(
                    basename=file.name, display_name=name,
                    enabled=enabled, is_system=False, comment=comment,
                )

    return sorted(by_basename.values(), key=lambda e: e.display_name.lower())


def toggle_entry(entry: AutostartEntry) -> AutostartEntry:
    """
    يقلب حالة عنصر واحد ويُرجع نسخة محدَّثة منه. لا يحتاج صلاحيات جذر
    أبداً — كل التعديل يتم داخل ~/.config/autostart/ فقط.

    يعتمد على فحص فعلي لنظام الملفات (لا على entry.is_system المحفوظة)
    لتفادي حالة تراكم ملفات تجاوز زائدة بعد عدة عمليات تبديل متتالية.
    """
    system_file = _SYSTEM_AUTOSTART / entry.basename
    user_file = _USER_AUTOSTART / entry.basename
    new_enabled = not entry.enabled
    has_system = system_file.exists()
    has_user_override = user_file.exists()

    if not has_system:
        # عنصر مستخدم بحت، لا نسخة نظام موازية له — نعدّله مباشرة
        _write_hidden_flag(user_file, hidden=not new_enabled)
        log.info("تم %s عنصر مستخدم: %s", "تفعيل" if new_enabled else "تعطيل", entry.basename)
        return replace(entry, enabled=new_enabled, is_system=False)

    if not has_user_override:
        # أول تعديل على عنصر نظام — ننشئ نسخة تجاوز في مجلد المستخدم
        _USER_AUTOSTART.mkdir(parents=True, exist_ok=True)
        shutil.copy2(system_file, user_file)
        _write_hidden_flag(user_file, hidden=not new_enabled)
        log.info("تم إنشاء تجاوز لعنصر نظام: %s", entry.basename)
        return replace(entry, enabled=new_enabled, is_system=False)

    # يوجد تجاوز مسبق — نعدّله، ثم ننظّفه إن أصبح مطابقاً لإعداد النظام
    # الافتراضي (حتى لا تتراكم ملفات تجاوز لا داعي لها بمرور الوقت)
    _write_hidden_flag(user_file, hidden=not new_enabled)
    system_parsed = _read_desktop_entry(system_file)
    if system_parsed is not None:
        _, system_default_enabled, _ = system_parsed
        if new_enabled == system_default_enabled:
            user_file.unlink()
            log.info("التجاوز أصبح غير ضروري وحُذف لعنصر: %s (يعود لإعداد النظام)", entry.basename)
            return replace(entry, enabled=new_enabled, is_system=True)

    log.info("تم تحديث تجاوز عنصر نظام: %s", entry.basename)
    return replace(entry, enabled=new_enabled, is_system=False)


def _write_hidden_flag(path: Path, hidden: bool) -> None:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read(path, encoding="utf-8") if path.exists() else None
    if "Desktop Entry" not in parser:
        parser["Desktop Entry"] = {}
    parser["Desktop Entry"]["Hidden"] = "true" if hidden else "false"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        parser.write(fh, space_around_delimiters=False)


class StartupManagerModule(MaintenanceModule):
    name = "برامج بدء التشغيل"
    slug = "startup_manager"
    description = "تفعيل/تعطيل البرامج التي تعمل تلقائياً عند تسجيل الدخول (إدارة فردية كاملة)"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "system-run"
    has_custom_ui = True  # تُدار عبر نافذة مخصصة بدل بطاقة الفحص/التطبيق العادية

    def scan(self) -> ScanResult:
        entries = list_entries()
        findings: list[ScanFinding] = []

        if not entries:
            findings.append(ScanFinding(
                title="لا توجد برامج بدء تشغيل مسجَّلة",
                detail="",
                severity=Severity.OK,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        enabled_count = sum(1 for e in entries if e.enabled)
        findings.append(ScanFinding(
            title=f"{enabled_count} من {len(entries)} برنامج بدء تشغيل مفعّل",
            detail="افتح الإدارة الفردية أدناه لتفعيل/تعطيل كل برنامج على حدة.",
            severity=Severity.INFO,
            actionable=False,  # التفعيل الفعلي يتم عبر النافذة المخصصة لا زر "تطبيق" عام
            raw_value=entries,
        ))
        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="إدارة برامج بدء التشغيل تتم عبر نافذة مخصصة (زر «إدارة فردية»)، لا عبر معاينة/تطبيق جماعي.",
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="استخدم زر «إدارة فردية» على هذه البطاقة للتحكم بكل برنامج على حدة.",
        )
