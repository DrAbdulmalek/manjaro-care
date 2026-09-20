#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/update_check.py
=======================
وحدة إخبارية بحتة (scan فقط — لا تعدّل شيئاً إطلاقاً) تجمع مؤشرات
سلامة دورة التحديث في مانجارو/آرتش:

  1) ملفات .pacnew/.pacsave المعلّقة في /etc — تُعرض مع أمر الفرق
     الحرفي لكل ملف (العرض من النافذة المخصصة). لا حذف ولا دمج
     تلقائي أبداً — قرار دمج الإعدادات يبقى للمستخدم وحده.
  2) كشف عدم مزامنة قواعد بيانات pacman (عمر ملفات sync/*.db) مع
     تحذير صريح من التحديث الجزئي (-Sy بدون -u) الذي يكسر الأنظمة.
  3) قائمة الخدمات الفاشلة (systemctl --failed — قراءة فقط).
  4) آخر أخبار مانجارو (RSS) عند توفر الشبكة — التدهور الرشيق
     عند غيابها مضمون (مهلة 3 ثوانٍ، بلا استثناءات تصل الواجهة).

apply() لا ينفّذ إجراء تعديلي — الوحدة معلوماتية بالكامل عمداً.
"""

from __future__ import annotations

import os
import re
import time
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

from core.logger import get_logger
from core.module_base import (
    ApplyResult,
    MaintenanceModule,
    PreviewStep,
    RiskLevel,
    ScanFinding,
    ScanResult,
    Severity,
)
from core.privilege import run_unprivileged

log = get_logger("update_check")

SYNC_DIR = "/var/lib/pacman/sync"
NEWS_URL = "https://forum.manjaro.org/c/announcements.rss"
NEWS_URL_LABEL = NEWS_URL
_DB_STALE_DAYS = 7


# ---------------------------------------------------------------------------
# محللات نقيّة
# ---------------------------------------------------------------------------

def parse_pacnew_paths(output: str) -> list[str]:
    """سطور مسارات من مخرجات find (سطر لكل ملف، مع تجاهل الفواضی)."""
    return [line.strip() for line in output.splitlines() if line.strip()]


def sync_db_age_days(mtimes: dict[str, float], now: float | None = None) -> float | None:
    """أقدم عمر (بالأيام) بين ملفات قواعد بيانات sync — نقي للاختبار.
    يُرجع None إن لم توجد قواعد أصلاً."""
    now = time.time() if now is None else now
    if not mtimes:
        return None
    return (now - min(mtimes.values())) / 86400


def parse_rss_titles(xml_text: str, limit: int = 5) -> list[str]:
    """استخراج عناوين آخر أخبار من RSS — تحليل متسامح: أي فشل يعيد [].
    يُعالج كل من النص العادي و<![CDATA[...]]>."""
    titles: list[str] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    for item in root.iter():
        if not item.tag.rsplit("}", 1)[-1].lower().endswith("item"):
            continue
        for child in item:
            if child.tag.rsplit("}", 1)[-1].lower() == "title" and (child.text or "").strip():
                text = (child.text or "").strip()
                cdata = re.match(r"^<!\[CDATA\[(.*)\]\]>$", text, re.S)
                titles.append(cdata.group(1).strip() if cdata else text)
                break
        if len(titles) >= limit:
            break
    return titles


def fetch_news_titles(limit: int = 5) -> tuple[list[str], str | None]:
    """جلب أخبار مانجارو — تدهور رشيق كامل: (عناوين, None) عند النجاح
    أو ([], سبب) عند غياب الشبكة/أي خطأ. لا استثناء تصل المتصل."""
    try:
        request = urllib.request.Request(
            NEWS_URL, headers={"User-Agent": "manjaro-care/1.2 (info module)"}
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            data = response.read(64 * 1024)
        return parse_rss_titles(data.decode("utf-8", errors="ignore"), limit), None
    except Exception as exc:  # noqa: BLE001 — أي عطل شبكة = ميزة تختفي بصمت
        log.info("تعذر جلب الأخبار: %s", exc)
        return [], str(exc)


# ---------------------------------------------------------------------------
# فحوص القراءة
# ---------------------------------------------------------------------------

def _find_pacnew_files() -> list[str]:
    """مخرجات find القرائية على /etc — قائمة argv بلا shell."""
    result = run_unprivileged(
        ["find", "/etc", "-type", "f", "(", "-name", "*.pacnew", "-o",
         "-name", "*.pacsave", ")"]
    )
    return parse_pacnew_paths(result.stdout) if result.ok else []


def _get_failed_units() -> list[str]:
    """نسخة محلية (قراءة فقط) — منسوخة عن failed_services لتجنب اقتران
    وحدات (3 أسطر)، والنسخة الأصلية تبقى مصدر إعادة التشغيل."""
    result = run_unprivileged(["systemctl", "--failed", "--no-legend", "--plain"])
    units = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            units.append(parts[0])
    return units


def _sync_db_mtimes() -> dict[str, float]:
    mtimes: dict[str, float] = {}
    try:
        for name in os.listdir(SYNC_DIR):
            if name.endswith(".db"):
                mtimes[name] = os.path.getmtime(os.path.join(SYNC_DIR, name))
    except OSError:
        pass
    return mtimes


# ---------------------------------------------------------------------------
# الوحدة
# ---------------------------------------------------------------------------

class UpdateCheckModule(MaintenanceModule):
    name = "مؤشرات دورة التحديث"
    slug = "update_check"
    description = (
        "فحص إخباري: ملفات .pacnew المعلقة (مع الفروق)، عدم مزامنة قواعد "
        "البيانات وتحذير التحديث الجزئي، الخدمات الفاشلة، أخبار مانجارو"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "software-updates-available"
    has_custom_ui = True  # أزرار عرض الفرق لكل .pacnew + الأخبار

    # ------------------------------------------------------------------
    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        # 1) ملفات .pacnew/.pacsave
        pacnew = _find_pacnew_files()
        if pacnew:
            findings.append(ScanFinding(
                title=f"{len(pacnew)} ملف إعدادات معلق (.pacnew/.pacsave)",
                detail=(
                    "احتياج دمج يدوي محتمل — استخدم «إدارة فردية» لعرض كل فرق.\n"
                    + "\n".join(f"  • {p}" for p in pacnew[:8])
                    + ("\n  ..." if len(pacnew) > 8 else "")
                ),
                severity=Severity.WARNING,
                actionable=False,  # الإجراء (عرض الفرق) من النافذة المخصصة
                raw_value=pacnew,
            ))
        else:
            findings.append(ScanFinding(
                title="لا ملفات .pacnew/.pacsave معلقة",
                detail="لا إعدادات تحتاج دمجاً بعد آخر تحديث.",
                severity=Severity.OK, actionable=False,
            ))

        # 2) عمر قواعد البيانات + تحذير التحديث الجزئي
        age = sync_db_age_days(_sync_db_mtimes())
        if age is None:
            findings.append(ScanFinding(
                title="قواعد بيانات pacman غير موجودة",
                detail=f"{SYNC_DIR} فارغ أو غير مقروء.",
                severity=Severity.INFO, actionable=False,
            ))
        elif age > _DB_STALE_DAYS:
            findings.append(ScanFinding(
                title=f"قواعد البيانات غير متزامنة منذ {age:.0f} يوماً",
                detail=(
                    "⚠ قاعدة ذهبية: لا تستخدم pacman -Sy بدون -u أبداً — "
                    "التثبيت على قواعد قديمة = تحديث جزئي يكسر الاعتماديات. "
                    "استخدم pacman -Syu دائماً."
                ),
                severity=Severity.WARNING, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title=f"قواعد البيانات متزامنة حديثاً ({age:.1f} يوم)",
                severity=Severity.OK, actionable=False,
                detail="لا مؤشر على تحديث جزئي محتمل.",
            ))

        # 3) الخدمات الفاشلة
        units = _get_failed_units()
        if units:
            findings.append(ScanFinding(
                title=f"{len(units)} خدمة فاشلة (systemctl --failed)",
                detail="\n".join(f"  • {u}" for u in units[:8]),
                severity=Severity.WARNING if len(units) <= 2 else Severity.CRITICAL,
                actionable=False,  # إعادة التشغيل من وحدة failed_services المخصصة
                raw_value=units,
            ))
        else:
            findings.append(ScanFinding(
                title="لا خدمات فاشلة",
                severity=Severity.OK, actionable=False,
                detail="systemctl --failed نظيف.",
            ))

        # 4) أخبار مانجارو (تدهور رشيق بلا شبكة)
        titles, error = fetch_news_titles()
        if titles:
            findings.append(ScanFinding(
                title="آخر أخبار مانجارو (الإعلانات)",
                detail="\n".join(f"  • {t}" for t in titles),
                severity=Severity.INFO, actionable=False,
                raw_value=titles,
            ))
        else:
            findings.append(ScanFinding(
                title="أخبار مانجارو غير متاحة الآن",
                detail=f"({error or 'لا أخبار'}) — الرابط الدائم: {NEWS_URL_LABEL}",
                severity=Severity.INFO, actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    # ------------------------------------------------------------------
    def preview(self) -> list[PreviewStep]:
        steps = [PreviewStep(
            description="وحدة إخبارية — لا يوجد إجراء تعديلي. "
                        "أوامر عرض الفروق (قراءة فقط):",
        )]
        for path in _find_pacnew_files()[:10]:
            if path.endswith(".pacnew"):
                base = path[: -len(".pacnew")]
                steps.append(PreviewStep(
                    description=f"فرق {path}",
                    command=f"diff -u {base} {path}",
                ))
            else:
                steps.append(PreviewStep(
                    description=f"الملف {path} نسخة محفوظة (.pacsave) — لا ملف أصلي يقارن به.",
                ))
        return steps

    # ------------------------------------------------------------------
    def apply(self) -> ApplyResult:
        # وحدة إخبارية عمداً: لا حذف ولا دمج .pacnew تلقائياً أبداً
        return ApplyResult(
            success=True,
            message="لا إجراء تلقائي — هذه الوحدة معلوماتية. "
                    "استخدم «إدارة فردية» لعرض فروق .pacnew، وراجعها يدوياً.",
        )
