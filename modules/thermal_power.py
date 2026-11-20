#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تشخيص حراري/طاقي للقراءة فقط: CPU، درجات الحرارة، TLP، والمنصات."""
from __future__ import annotations

import re
import shutil
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


def parse_temperatures(text: str) -> list[tuple[str, float]]:
    """استخراج درجات CPU من مخرجات sensors دون افتراض أسماء شريحة بعينها."""
    rows = []
    pattern = re.compile(
        r"^\s*((?:Package id\s*\d+)|(?:Core\s*\d+)|(?:CPU(?: Package)?)|"
        r"(?:Tctl)|(?:Tdie))\s*:\s*\+?(\d+(?:\.\d+)?)\s*°?C",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            rows.append((match.group(1).strip(), float(match.group(2))))
    return rows


def parse_fan_speeds(text: str) -> list[tuple[str, int]]:
    """استخراج سرعات المراوح من sensors؛ لا يعتبر PWM=N/A سرعة صفراً."""
    rows = []
    pattern = re.compile(r"^\s*(fan\d+)\s*:\s*(\d+)\s*RPM", re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            rows.append((match.group(1), int(match.group(2))))
    return rows


def parse_process_cpu(text: str, limit: int = 5) -> list[tuple[float, str]]:
    """تحليل ps -eo pcpu=,comm= مع رفض الأسطر غير القابلة للتحليل."""
    rows = []
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
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
    description = (
        "تشخيص درجات حرارة CPU، أحمال العمليات، تردد/حوكمة المعالج، "
        "TLP وملف المنصة ومؤشرات تعارض إدارة الطاقة — قراءة فقط"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "temperature"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        sensors = run_unprivileged(["sensors"])
        temperatures = parse_temperatures(sensors.stdout) if sensors.ok else []
        if temperatures:
            hottest = max(value for _, value in temperatures)
            severity = Severity.CRITICAL if hottest >= 95 else (
                Severity.WARNING if hottest >= 85 else Severity.OK
            )
            findings.append(ScanFinding(
                title=f"أعلى حرارة CPU مسجلة: {hottest:.1f}°C",
                detail="\n".join(f"{name}: {value:.1f}°C" for name, value in temperatures),
                severity=severity, actionable=False, raw_value=hottest,
            ))
        else:
            findings.append(ScanFinding(
                title="قراءة حرارة CPU غير متاحة",
                detail="لم تُستخرج قراءة CPU من sensors. تحقق من lm_sensors أو مناطق thermal sysfs.",
                severity=Severity.INFO, actionable=False,
            ))

        zones = []
        for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/")):
            zone_type = _read(str(path / "type")) or path.name
            raw = _read(str(path / "temp"))
            try:
                value = int(raw) / 1000.0
            except ValueError:
                continue
            if -20 <= value <= 150:
                zones.append((zone_type, value))
        if zones:
            detail = "\n".join(f"{name}: {value:.1f}°C" for name, value in zones[:12])
            findings.append(ScanFinding(
                title=f"مناطق الحرارة: {len(zones)} قراءة",
                detail=detail, severity=Severity.INFO, actionable=False,
            ))

        fans = parse_fan_speeds(sensors.stdout) if sensors.ok else []
        if fans:
            findings.append(ScanFinding(
                title="سرعات المراوح المقروءة",
                detail="\n".join(f"{name}: {rpm} RPM" for name, rpm in fans),
                severity=Severity.INFO, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="سرعة المروحة غير متاحة عبر sensors",
                detail="قد لا يعرّض BIOS/EC سرعة المروحة للنظام؛ لا يعني ذلك وجود عطل بالمروحة.",
                severity=Severity.INFO, actionable=False,
            ))

        ps = run_unprivileged(["ps", "-eo", "pcpu=,comm=", "--sort=-pcpu"])
        processes = parse_process_cpu(ps.stdout) if ps.ok else []
        if processes:
            findings.append(ScanFinding(
                title="أعلى العمليات استهلاكاً للمعالج",
                detail="\n".join(f"{cpu:.1f}%  {name}" for cpu, name in processes),
                severity=Severity.INFO, actionable=False, raw_value=processes,
            ))

        governor = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        epp = _read("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
        driver = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver")
        turbo = _read("/sys/devices/system/cpu/intel_pstate/no_turbo")
        current_khz = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
        maximum_khz = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
        cpu_lines = []
        if driver:
            cpu_lines.append(f"Driver: {driver}")
        if governor:
            cpu_lines.append(f"Governor: {governor}")
        if epp:
            cpu_lines.append(f"EPP: {epp}")
        if turbo in {"0", "1"}:
            cpu_lines.append(f"Intel Turbo: {'مسموح' if turbo == '0' else 'معطّل'}")
        for label, value in (("التردد الحالي", current_khz), ("الحد الأعلى", maximum_khz)):
            try:
                cpu_lines.append(f"{label}: {int(value) / 1000:.0f} MHz")
            except ValueError:
                pass
        if cpu_lines:
            findings.append(ScanFinding(
                title="سياسة المعالج الحالية",
                detail="\n".join(cpu_lines), severity=Severity.INFO, actionable=False,
            ))

        platform_profile = _read("/sys/firmware/acpi/platform_profile")
        profile_choices = _read("/sys/firmware/acpi/platform_profile_choices")
        if platform_profile or profile_choices:
            findings.append(ScanFinding(
                title=f"ملف طاقة العتاد: {platform_profile or 'غير مقروء'}",
                detail=f"الخيارات المدعومة: {profile_choices or 'غير معروفة'}",
                severity=Severity.INFO, actionable=False,
            ))

        tlp_active = run_unprivileged(["systemctl", "is-active", "tlp.service"])
        ppd_active = run_unprivileged(["systemctl", "is-active", "power-profiles-daemon.service"])
        def service_state(result):
            if result.returncode == 0 and result.stdout.strip() == "active":
                return "active"
            if result.returncode in {3, 4} and result.stdout.strip() in {"inactive", "failed", "unknown"}:
                return result.stdout.strip()
            return "unknown"

        tlp_state = service_state(tlp_active)
        ppd_state = service_state(ppd_active)
        if tlp_state == "active" and ppd_state == "active":
            findings.append(ScanFinding(
                title="احتمال تعارض: TLP و power-profiles-daemon يعملان معاً",
                detail="لا توقف أياً منهما تلقائياً. راجع إعدادات التوزيعة وحدد مدير طاقة واحداً بعد التحقق.",
                severity=Severity.WARNING, actionable=False,
            ))
        else:
            label = {"active": "نشط", "inactive": "غير نشط", "failed": "فاشل", "unknown": "غير معروف"}
            findings.append(ScanFinding(
                title=f"TLP: {label[tlp_state]} | power-profiles-daemon: {label[ppd_state]}",
                detail="هذه حالة الخدمات فقط؛ لا تعني وحدها وجود خلل.",
                severity=Severity.INFO, actionable=False,
            ))

        if shutil.which("tlp-stat"):
            status = run_unprivileged(["tlp-stat", "-s"])
            processor = run_unprivileged(["tlp-stat", "-p"])
            chunks = []
            if status.stdout.strip():
                chunks.append("TLP status:\n" + status.stdout.strip()[:1800])
            if processor.stdout.strip():
                chunks.append("TLP processor:\n" + processor.stdout.strip()[:2600])
            if chunks:
                findings.append(ScanFinding(
                    title="تفاصيل TLP",
                    detail="\n\n".join(chunks), severity=Severity.INFO, actionable=False,
                ))
        else:
            findings.append(ScanFinding(
                title="TLP غير مثبت أو tlp-stat غير متاح",
                detail="لم يُنفّذ أي تثبيت تلقائي.", severity=Severity.INFO, actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="وحدة تشخيصية للقراءة فقط؛ لا تغيّر TLP أو governor أو Turbo أو BIOS أو منحنى المروحة."
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="هذه الوحدة تشخيصية فقط. لا تُطبّق تغييرات حرارية أو طاقية تلقائياً.",
        )
