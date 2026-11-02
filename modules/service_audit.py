#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تدقيق سلامة التحديثات والإغلاق وبقايا Update on Shutdown — قراءة فقط."""
from __future__ import annotations

import re
from pathlib import Path

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

_UNIT_NAMES = ("update_shutdown.service", "update_startup.service")
_UNIT_PATHS = (
    Path("/etc/systemd/system"),
    Path("/usr/lib/systemd/system"),
    Path("/lib/systemd/system"),
)
_SCRIPT_PATHS = (
    Path("/usr/local/bin/update_shutdown"),
    Path("/usr/local/bin/update_startup"),
)
_LOG_DIR = Path("/var/log/manjaro-automatic-update")

_PATTERNS = {
    "dns": re.compile(
        r"Could not resolve host|Temporary failure in name resolution|"
        r"Name or service not known|failed to retrieve some files",
        re.IGNORECASE,
    ),
    "network_stop": re.compile(
        r"Stopping (NetworkManager|systemd-resolved)|"
        r"Stopped (NetworkManager|systemd-resolved)|"
        r"NetworkManager.*(deactivated|stopped)",
        re.IGNORECASE,
    ),
    "cache_unmount": re.compile(
        r"Failed unmounting /var/cache|var-cache\.mount.*"
        r"(failed|status=32|exit(ed)?)",
        re.IGNORECASE,
    ),
    "unsafe_update": re.compile(
        r"pamac update|pamac remove -o|flatpak update|"
        r"Update startet|Starting Pamac update",
        re.IGNORECASE,
    ),
}


def _unit_state(unit: str) -> dict[str, str] | None:
    result = run_unprivileged([
        "systemctl", "show", unit, "--no-pager",
        "--property=LoadState", "--property=ActiveState",
        "--property=UnitFileState", "--property=FragmentPath",
        "--property=ExecStart", "--property=ExecStop",
        "--property=TimeoutStopUSec",
    ])
    if not result.ok:
        return None
    state = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            state[key] = value
    return state


def _existing_unit_files() -> list[str]:
    found = []
    for unit in _UNIT_NAMES:
        for directory in _UNIT_PATHS:
            path = directory / unit
            try:
                if path.is_file():
                    found.append(str(path))
            except OSError:
                continue
        dropin_dirs = (
            Path("/etc/systemd/system") / f"{unit}.d",
            Path("/usr/lib/systemd/system") / f"{unit}.d",
        )
        for directory in dropin_dirs:
            try:
                if directory.is_dir() and any(directory.iterdir()):
                    found.append(str(directory))
            except OSError:
                continue
    return found


def _read_relevant_lines(path: Path, limit: int = 20) -> tuple[list[str], str | None]:
    """Read bounded log content and return only narrowly matched diagnostic lines."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 256 * 1024))
            chunk = stream.read().decode("utf-8", errors="replace")
            lines = chunk.splitlines()[-120:]
    except OSError as exc:
        return [], str(exc)
    matches = []
    for line in lines:
        if any(pattern.search(line) for pattern in _PATTERNS.values()):
            matches.append(line.strip()[:500])
    return matches[-limit:], None


def _collect_update_log_evidence() -> tuple[list[str], list[str]]:
    matches = []
    notes = []
    try:
        candidates = []
        for path in _LOG_DIR.iterdir():
            try:
                if path.is_file():
                    candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        candidates = [path for _, path in sorted(candidates, reverse=True)[:3]]
    except FileNotFoundError:
        return [], [f"مجلد السجلات غير موجود: {_LOG_DIR}"]
    except OSError as exc:
        return [], [f"تعذرت قراءة مجلد سجلات التحديث: {exc}"]

    for path in candidates:
        lines, error = _read_relevant_lines(path)
        if error:
            notes.append(f"تعذرت قراءة {path.name}: {error}")
        matches.extend(f"{path.name}: {line}" for line in lines)
    return matches[-30:], notes


def _collect_previous_boot_evidence() -> tuple[list[str], str | None]:
    result = run_unprivileged([
        "journalctl", "--boot=-1", "--no-pager",
        "--output=short-iso", "--lines=300",
    ], timeout=15)
    if not result.ok:
        return [], result.stderr.strip() or "تعذر قراءة سجل الإقلاع السابق."
    matches = []
    for line in result.stdout.splitlines():
        if any(pattern.search(line) for pattern in _PATTERNS.values()):
            matches.append(line.strip()[:500])
    return matches[-30:], None


class ServiceAuditModule(MaintenanceModule):
    name = "تدقيق سلامة التحديثات والإغلاق"
    slug = "service_audit"
    description = (
        "يفحص بقايا Update on Shutdown وسجلات Pamac وDNS وإيقاف الشبكة "
        "وفشل فك /var/cache؛ قراءة فقط بلا تعطيل أو حذف"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "applications-system"
    doc_url = (
        "https://github.com/DrAbdulmalek/manjaro-care/"
        "blob/feat/update-shutdown-safety-audit/docs/UPDATE_SHUTDOWN_RETIREMENT.md"
    )

    def scan(self) -> ScanResult:
        findings = []
        unit_states = {unit: _unit_state(unit) for unit in _UNIT_NAMES}
        unit_files = _existing_unit_files()
        scripts = [str(path) for path in _SCRIPT_PATHS if path.is_file()]

        if any(state and (
            state.get("LoadState") == "loaded"
            or state.get("ActiveState") == "active"
            or state.get("UnitFileState") in {"enabled", "enabled-runtime"}
        ) for state in unit_states.values()) or unit_files:
            details = []
            for unit, state in unit_states.items():
                if state is None:
                    details.append(f"{unit}: تعذرت قراءة الحالة")
                else:
                    details.append(
                        f"{unit}: LoadState={state.get('LoadState', 'unknown')}, "
                        f"ActiveState={state.get('ActiveState', 'unknown')}, "
                        f"UnitFileState={state.get('UnitFileState', 'unknown')}, "
                        f"FragmentPath={state.get('FragmentPath', '') or 'غير معروف'}"
                    )
            details.extend(unit_files)
            findings.append(ScanFinding(
                title="عُثر على وحدة تحديث أثناء الإغلاق أو بقايا unit",
                detail="\n".join(details) + "\nلم يُجرَ تعطيل أو حذف تلقائي.",
                severity=Severity.WARNING,
                actionable=False,
            ))
        elif all(state is not None and state.get("LoadState") == "not-found"
                 for state in unit_states.values()):
            detail = "update_shutdown.service وupdate_startup.service غير محمّلتين."
            if scripts:
                detail += "\nبقيت سكربتات محفوظة: " + ", ".join(scripts)
                detail += "\nوجود السكربت وحده لا يعني أن systemd يشغّله."
            findings.append(ScanFinding(
                title="وحدات Update on Shutdown/Startup غير محمّلة",
                detail=detail,
                severity=Severity.INFO,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="حالة وحدات التحديث القديمة غير محسومة بالكامل",
                detail=(
                    "تعذر الحصول على حالة موثوقة لكل الوحدات؛ لا تُفسّر "
                    "غياب المخرجات على أنه إثبات للإزالة."
                ),
                severity=Severity.INFO,
                actionable=False,
            ))

        log_matches, log_notes = _collect_update_log_evidence()
        journal_matches, journal_error = _collect_previous_boot_evidence()
        evidence = log_matches + [f"journal: {line}" for line in journal_matches]
        dns_lines = [line for line in evidence if _PATTERNS["dns"].search(line)]
        network_lines = [line for line in evidence if _PATTERNS["network_stop"].search(line)]
        cache_lines = [line for line in evidence if _PATTERNS["cache_unmount"].search(line)]
        update_lines = [line for line in evidence if _PATTERNS["unsafe_update"].search(line)]

        if dns_lines:
            findings.append(ScanFinding(
                title="أخطاء DNS/جلب قواعد المرايا في سجلات التحديث",
                detail=(
                    "عُثر على أخطاء حل أسماء أو فشل جلب ملفات قواعد الحزم. "
                    "هذا يثبت فشل الوصول إلى بعض المرايا في تلك اللحظة، لكنه "
                    "لا يحدد وحده هل السبب DNS أم انقطاع الشبكة أو إعداد المرآة.\n"
                    + "\n".join(dns_lines[-12:])
                ),
                severity=Severity.WARNING,
                actionable=False,
            ))

        if network_lines and update_lines:
            findings.append(ScanFinding(
                title="تداخل زمني محتمل بين التحديث وإيقاف خدمات الشبكة",
                detail=(
                    "توجد آثار لبدء/تنفيذ تحديث، وكذلك إيقاف NetworkManager أو "
                    "systemd-resolved في سجل الإقلاع السابق. هذا يدعم وجود سباق "
                    "زمني محتمل أثناء الإغلاق، لكنه لا يثبت وحده أن خدمة التحديث "
                    "هي السبب المباشر.\n" + "\n".join((update_lines + network_lines)[-12:])
                ),
                severity=Severity.WARNING,
                actionable=False,
            ))

        if cache_lines:
            findings.append(ScanFinding(
                title="سُجل فشل فك ربط /var/cache أثناء الإغلاق",
                detail=(
                    "السجل يثبت فشل عملية unmount، لكنه لا يثبت أن Update on Shutdown "
                    "هو السبب المباشر. يلزم ربط التوقيت مع العمليات التي كانت تستخدم "
                    "نظام الملفات ومع تفاصيل mount في ذلك الإقلاع.\n"
                    + "\n".join(cache_lines[-8:])
                ),
                severity=Severity.WARNING,
                actionable=False,
            ))

        if log_notes or journal_error:
            notes = log_notes[:]
            if journal_error:
                notes.append("journal: " + journal_error)
            findings.append(ScanFinding(
                title="بعض مصادر سجل التحديث/الإقلاع غير متاحة",
                detail="\n".join(notes),
                severity=Severity.INFO,
                actionable=False,
            ))

        if not dns_lines and not network_lines and not cache_lines and not log_matches and not journal_matches:
            findings.append(ScanFinding(
                title="لا توجد أدلة مطابقة في السجلات المقروءة",
                detail=(
                    "هذه النتيجة لا تثبت سلامة كل عمليات التحديث السابقة؛ "
                    "قد تكون السجلات غير موجودة أو غير مقروءة أو أقدم من نافذة الفحص."
                ),
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [
            PreviewStep(
                description="قراءة حالة وحدات systemd وملفاتها وسجلات التحديث والإقلاع السابق فقط."
            ),
            PreviewStep(
                description="لا يوجد أي إجراء إصلاح تلقائي؛ لا تعطيل ولا حذف ولا تحديث ولا إعادة تشغيل خدمات."
            ),
        ]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message=(
                "هذه الوحدة تشخيصية فقط. لم تُعطّل وحدات systemd، ولم تُحذف سكربتات "
                "أو سجلات، ولم تُنفّذ تحديثات أو تغييرات شبكة."
            ),
        )
