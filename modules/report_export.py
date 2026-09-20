#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/report_export.py
========================
يجمّع خلاصة فحوص وحدات مختارة (قراءة فقط، بلا أي تعديل) في تقرير
Markdown **منقّى تلقائياً** من المعلومات الحساسة، ويعرض معاينته
قبل الحفظ (نافذة مخصصة + زر تطبيق القياسي).

التنقيح التلقائي يشمل: اسم المستخدم، اسم الجهاز، عناوين IP (v4/v6)
وMAC، أرقام التسلسل، ومسارات /home/<user>. مبدأ التنقيح: الخطأ في
التنقيح الزائد غير مؤذي؛ الخطأ في نسيان سرٍّ لا يُغتفر — لذلك
التعبيرات محافظة وقد تعمم ما ليس سراً (مثل أرقام إصدارات تبدو
كعناوين IPv4) والجانب الأماني أولوية.

قرار تصميمي: التقرير يجمع من **قائمة وحدات منسّقة آمنة وخفيفة** —
لا من كل السجل (registry): boot_sanity يستدعي سكربتاً خارجياً عبر
pkexec (نافذة مصادقة أثناء تقرير؟ لا)، وdisk_analyzer قد يمسح قرصاً
ضخماً (تقرير لا يجوز أن يستغرق ساعات). القائمة موثقة أدناه وتُعلَّق
بالتقرير نفسه.

كل شيء قراءة فقط: scan() يبني النص، والمعاينة تعرضه، والحفظ يتم
فقط بعد تأكيد صريح (زر تطبيق القياسي أو زر الحفظ في النافذة).
"""

from __future__ import annotations

import datetime
import getpass
import platform
import re
import socket

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
from core.runtime import is_dry_run

log = get_logger("report_export")

REPORT_DIR_DEFAULT = None  # يُحل عند الاستدعاء: Path.home()


# ---------------------------------------------------------------------------
# التنقيح — دوال نقية تُختبر مباشرة
# ---------------------------------------------------------------------------

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# IPv6: صيغة كاملة (4+ مجموعات)، أو مضغوطة تحوي "::" مع بادئة أو
# بدونها — محافظ (الوقت "12:34:56" لا يحوي "::" فلا يُمس)
_IPV6_RE = re.compile(
    r"\b(?:[0-9A-Fa-f]{1,4}:){4,7}[0-9A-Fa-f]{1,4}\b"
    r"|\b(?:[0-9A-Fa-f]{1,4}:){1,7}:[0-9A-Fa-f:]*[0-9A-Fa-f]"
    r"|(?<![0-9A-Fa-f:])::(?:[0-9A-Fa-f]{1,4}:?)+\b"
)
_MAC_COLON_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
_MAC_DASH_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}\b")
# سطر يحمل "serial" أو "S/N" وقيمة بعد ":" أو "=" — تُقنّع القيمة
_SERIAL_LINE_RE = re.compile(
    r"(?im)^([^\n]*(?:serial[^\n:=-]*|s/n)[^\n:=-]*[:=]\s*)(\S[^\n]*)$"
)
_HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+")


def redact_ipv4(text: str) -> str:
    """يستبدل IPv4 الصالح فقط (كل مقطع ≤ 255) — لتفادي إصدارات مثل 6.6.10."""

    def _check(m: re.Match) -> str:
        octets = m.group().split(".")
        if all(o.isdigit() and int(o) <= 255 for o in octets):
            return "«عنوان-IP»"
        return m.group()

    return _IPV4_RE.sub(_check, text)


def redact_ipv6(text: str) -> str:
    return _IPV6_RE.sub("«عنوان-IP»", text)


def redact_mac(text: str) -> str:
    text = _MAC_COLON_RE.sub("«عنوان-MAC»", text)
    return _MAC_DASH_RE.sub("«عنوان-MAC»", text)


def redact_serials(text: str) -> str:
    """يقنّع قيمة أي سطر مفتاحه serial/S/N — يبقى اسم المفتاح للسياق."""
    return _SERIAL_LINE_RE.sub(r"\1«منقّح»", text)


def redact_home_paths(text: str) -> str:
    return _HOME_PATH_RE.sub("/home/«مستخدم»", text)


def redact_text(text: str, username: str, hostname: str) -> str:
    """تنقيح شامل بالترتيب الصحيح (الأطول/الأخص أولاً ثم العام)."""
    text = redact_serials(text)
    text = redact_mac(text)
    text = redact_ipv6(text)
    text = redact_ipv4(text)
    text = redact_home_paths(text)
    if hostname:
        text = re.sub(re.escape(hostname), "«اسم-الجهاز»", text)
    if username:
        text = re.sub(re.escape(username), "«مستخدم»", text)
    return text


# ---------------------------------------------------------------------------
# جمع التقرير — قائمة وحدات منسّقة (قرار تصميمي موثق أعلاه)
# ---------------------------------------------------------------------------

def _curated_modules():
    # استيراد محلي لتفادي أي دورة استيراد بين registry والوحدات
    from modules.boot_guard import BootGuardModule
    from modules.btrfs_health import BtrfsHealthModule
    from modules.failed_services import FailedServicesModule
    from modules.kernel_cleanup import KernelCleanupModule
    from modules.snapshot_before_update import SnapshotBeforeUpdateModule
    from modules.system_info import SystemInfoModule
    from modules.update_check import UpdateCheckModule

    # كلها: scan قراءة فقط، بلا pkexec منبثق، بلا مسح قرص ثقيل
    return [
        SystemInfoModule(),
        KernelCleanupModule(),
        FailedServicesModule(),
        UpdateCheckModule(),
        SnapshotBeforeUpdateModule(),
        BootGuardModule(),
        BtrfsHealthModule(),
    ]


def build_report_text() -> str:
    """يجمع التقرير الكامل منقّياً — قراءة فقط من كل الوحدات المنسّقة.
    أي وحدة تفشل تظهر في التقرير كتعذر فحص (بلا انهيار الكل)."""
    username = ""
    hostname = ""
    try:
        username = getpass.getuser()
    except Exception:  # noqa: BLE001 — بيئة بلا مستخدم (CI مثلاً)
        pass
    try:
        hostname = socket.gethostname()
    except Exception:  # noqa: BLE001
        pass

    now = datetime.datetime.now().astimezone()
    lines = [
        "# تقرير صيانة manjaro-care",
        "",
        f"- التاريخ: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- النواة: {redact_text(platform.release(), username, hostname)}",
        f"- النظام: {redact_text(' '.join(platform.uname()), username, hostname)}",
        f"- مُولَّد من: manjaro-care وحدة report_export",
        "- التنقيح: أسماء المستخدمين/الجهاز، IP/MAC، الأرقام التسلسلية، مسارات home",
        "",
    ]

    for module in _curated_modules():
        lines.append(f"## {module.name}")
        lines.append("")
        try:
            result = module.scan()
        except Exception as exc:  # noqa: BLE001 — وحدة فاشلة لا تُسقط التقرير
            lines.append(f"> تعذّر فحص هذه الوحدة: {exc}")
            lines.append("")
            continue
        if result.error:
            lines.append(f"> فشل الفحص: {result.error}")
            lines.append("")
            continue
        for finding in result.findings:
            severity_label = {
                Severity.OK: "✔", Severity.INFO: "•",
                Severity.WARNING: "⚠", Severity.CRITICAL: "✖",
            }[finding.severity]
            lines.append(f"- {severity_label} **{finding.title}**")
            if finding.detail:
                for detail_line in redact_text(
                        finding.detail, username, hostname).splitlines():
                    lines.append(f"  {detail_line}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def default_report_path() -> str:
    """مسار التقرير الافتراضي في مجلد المستخدم (بطابع زمني)."""
    import pathlib

    home = pathlib.Path.home()
    stamp = datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return str(home / f"manjaro-care-report-{stamp}.md")


# ---------------------------------------------------------------------------
# الوحدة
# ---------------------------------------------------------------------------

class ReportExportModule(MaintenanceModule):
    name = "تصدير تقرير منقّى"
    slug = "report_export"
    description = (
        "يجمع خلاصة الفحوص في تقرير Markdown منقّى تلقائياً (مستخدم، "
        "جهاز، IP/MAC، تسلسلات، مسارات) مع معاينة قبل الحفظ"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE  # قراءة + كتابة ملف واحد في مجلد المستخدم
    icon = "document-export"
    has_custom_ui = True  # معاينة النص الكامل + حفظ باسم

    # ------------------------------------------------------------------
    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        report = build_report_text()
        findings.append(ScanFinding(
            title="التقرير المنقّى جاهز للمعاينة",
            detail=(
                f"يغطي {len(_curated_modules())} وحدة فحص. استخدم «إدارة فردية» "
                "لمعاينة النص الكامل قبل الحفظ، أو «معاينة» ثم «تطبيق» للحفظ في "
                f"{default_report_path()}"
            ),
            severity=Severity.INFO,
            actionable=True,
            raw_value=report,
        ))
        return ScanResult(module_name=self.name, findings=findings)

    # ------------------------------------------------------------------
    def preview(self) -> list[PreviewStep]:
        report = build_report_text()
        return [
            PreviewStep(
                description="ستُنشأ نسخة نصية واحدة فقط في مجلد المستخدم — لا يُعدَّل أي إعداد نظام:\n"
                            + report[:1200] + ("\n...(المعاينة الكاملة عبر «إدارة فردية»)" if len(report) > 1200 else ""),
            ),
            PreviewStep(
                description="حفظ التقرير في:",
                command="cp <التقرير> " + default_report_path(),
            ),
        ]

    # ------------------------------------------------------------------
    def apply(self) -> ApplyResult:
        if is_dry_run():
            report = build_report_text()
            return ApplyResult(
                success=True,
                message=f"[DRY-RUN] لم يُكتب أي ملف — كان سيُحفظ في: {default_report_path()}",
                log_output=report[:800] + ("\n..." if len(report) > 800 else ""),
            )

        report = build_report_text()
        target = default_report_path()
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(report)
        except OSError as exc:
            return ApplyResult(success=False, message=f"فشل حفظ التقرير: {exc}")
        log.info("تم حفظ التقرير المنقّى: %s", target)
        return ApplyResult(
            success=True,
            message=f"تم حفظ التقرير المنقّى: {target}",
            log_output=f"{len(report)} حرفاً — التنقيح مطبق (مستخدم/جهاز/IP/MAC/تسلسلات/home).",
        )
