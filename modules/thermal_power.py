#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تشخيص حراري/طاقي للقراءة فقط."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from core.module_base import ApplyResult, MaintenanceModule, PreviewStep, RiskLevel, ScanFinding, ScanResult, Severity
from core.privilege import run_unprivileged


def parse_temperatures(text: str) -> list[tuple[str, float]]:
    pattern = re.compile(r"^\s*((?:Package id\s*\d+)|(?:Core\s*\d+)|(?:CPU(?: Package)?)|(?:Tctl)|(?:Tdie))\s*:\s*\+?(\d+(?:\.\d+)?)\s*°?C", re.I)
    return [(m.group(1).strip(), float(m.group(2))) for line in text.splitlines() if (m := pattern.search(line))]


def parse_fan_speeds(text: str) -> list[tuple[str, int]]:
    pattern = re.compile(r"^\s*(fan\d+)\s*:\s*(\d+)\s*RPM", re.I)
    return [(m.group(1), int(m.group(2))) for line in text.splitlines() if (m := pattern.search(line))]


def parse_process_cpu(text: str, limit: int = 5) -> list[tuple[float, str]]:
    rows = []
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            try:
                rows.append((float(parts[0]), parts[1]))
            except ValueError:
                continue
    return sorted(rows, reverse=True)[:limit]


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


class ThermalPowerModule(MaintenanceModule):
    name = "الحرارة وإدارة الطاقة"
    slug = "thermal_power"
    description = "تشخيص حرارة CPU وأحمال العمليات وسياسة المعالج وTLP وملف طاقة العتاد — قراءة فقط"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "temperature"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []
        sensors = run_unprivileged(["sensors"])
        temps = parse_temperatures(sensors.stdout) if sensors.ok else []
        if temps:
            hottest = max(v for _, v in temps)
            severity = Severity.CRITICAL if hottest >= 95 else Severity.WARNING if hottest >= 85 else Severity.OK
            findings.append(ScanFinding(
                title=f"أعلى حرارة CPU مسجلة: {hottest:.1f}°C",
                detail="\n".join(f"{name}: {value:.1f}°C" for name, value in temps),
                severity=severity, actionable=False, raw_value=hottest,
            ))
        else:
            findings.append(ScanFinding(title="قراءة حرارة CPU غير متاحة",
                detail="لم تُستخرج قراءة CPU من sensors؛ عدم توفرها لا يثبت وجود عطل.",
                severity=Severity.INFO, actionable=False))

        fans = parse_fan_speeds(sensors.stdout) if sensors.ok else []
        findings.append(ScanFinding(
            title="سرعات المراوح المقروءة" if fans else "سرعة المروحة غير متاحة عبر sensors",
            detail="\n".join(f"{name}: {rpm} RPM" for name, rpm in fans) if fans else
                   "قد لا يعرّض BIOS/EC سرعة المروحة للنظام؛ لا يعني ذلك وجود عطل.",
            severity=Severity.INFO, actionable=False))

        ps = run_unprivileged(["ps", "-eo", "pcpu=,comm=", "--sort=-pcpu"])
        processes = parse_process_cpu(ps.stdout) if ps.ok else []
        if processes:
            findings.append(ScanFinding(title="أعلى العمليات استهلاكاً للمعالج",
                detail="\n".join(f"{cpu:.1f}%  {name}" for cpu, name in processes),
                severity=Severity.INFO, actionable=False, raw_value=processes))

        cpu = []
        for label, path in (
            ("Driver", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"),
            ("Governor", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
            ("EPP", "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"),
            ("Turbo no_turbo", "/sys/devices/system/cpu/intel_pstate/no_turbo"),
            ("Platform profile", "/sys/firmware/acpi/platform_profile"),
            ("Profile choices", "/sys/firmware/acpi/platform_profile_choices"),
        ):
            value = _read(path)
            if value:
                cpu.append(f"{label}: {value}")
        if cpu:
            findings.append(ScanFinding(title="سياسة المعالج وملف طاقة العتاد",
                detail="\n".join(cpu), severity=Severity.INFO, actionable=False))

        def service_state(result):
            if result.returncode == 0 and result.stdout.strip() == "active":
                return "active"
            if result.returncode in {3, 4} and result.stdout.strip() in {"inactive", "failed", "unknown"}:
                return result.stdout.strip()
            return "unknown"

        tlp = service_state(run_unprivileged(["systemctl", "is-active", "tlp.service"]))
        ppd = service_state(run_unprivileged(["systemctl", "is-active", "power-profiles-daemon.service"]))
        conflict = tlp == "active" and ppd == "active"
        findings.append(ScanFinding(
            title="احتمال تعارض مديري الطاقة: TLP و power-profiles-daemon" if conflict else
                  f"حالة مديري الطاقة: TLP={tlp} | power-profiles-daemon={ppd}",
            detail="وجودهما نشطين معاً يستحق التحقق؛ لا توقف أياً منهما تلقائياً." if conflict else
                   "الحالة لا تثبت وحدها وجود خلل أو تعارض.",
            severity=Severity.WARNING if conflict else Severity.INFO, actionable=False))

        if shutil.which("tlp-stat"):
            status = run_unprivileged(["tlp-stat", "-s"])
            processor = run_unprivileged(["tlp-stat", "-p"])
            chunks = [x for x in (status.stdout.strip(), processor.stdout.strip()) if x]
            if chunks:
                findings.append(ScanFinding(title="تفاصيل TLP", detail="\n\n".join(chunks)[:3500],
                    severity=Severity.INFO, actionable=False))
        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="فحوص قراءة فقط؛ لا تغيّر TLP أو governor أو EPP أو Turbo أو BIOS أو منحنى المروحة.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="وحدة تشخيصية فقط؛ لم تُطبّق تغييرات حرارية أو طاقية.")
