#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest.mock import patch

from core.module_base import Severity
from core.privilege import CommandResult
from modules.thermal_power import ThermalPowerModule, parse_fan_speeds, parse_process_cpu, parse_temperatures


def test_parse_temperatures():
    parsed = parse_temperatures("Package id 0: +82.0°C\nCore 0: +79.0°C\nfan1: 2200 RPM\n")
    assert parsed == [("Package id 0", 82.0), ("Core 0", 79.0)]


def test_parse_fan_speeds_ignores_unavailable_pwm():
    assert parse_fan_speeds("fan1: 2200 RPM\\npwm1: N/A\\n") == [("fan1", 2200)]


def test_parse_process_cpu():
    parsed = parse_process_cpu("24.2 firefox\n5.1 kwin_wayland\ninvalid row\n")
    assert parsed == [(24.2, "firefox"), (5.1, "kwin_wayland")]


def test_scan_reports_hot_cpu_and_power_conflict():
    def fake(args, timeout=30):
        command = " ".join(args)
        if command in {"sensors -u", "sensors"}:
            return CommandResult(0, "Package id 0: +88.0°C\nCore 0: +84.0°C\n", "")
        if args[0] == "ps":
            return CommandResult(0, "33.9 firefox\n23.5 Isolated Web Content\n", "")
        if args[:3] == ["systemctl", "is-active", "tlp.service"]:
            return CommandResult(0, "active\n", "")
        if args[:3] == ["systemctl", "is-active", "power-profiles-daemon.service"]:
            return CommandResult(3, "inactive\n", "")
        if args[:2] == ["tlp-stat", "-s"]:
            return CommandResult(0, "TLP status sample", "")
        if args[:2] == ["tlp-stat", "-p"]:
            return CommandResult(0, "CPU sample", "")
        return CommandResult(1, "", "not found")

    with patch("modules.thermal_power.run_unprivileged", side_effect=fake), \
         patch("modules.thermal_power.shutil.which", return_value="/usr/bin/tlp-stat"), \
         patch("modules.thermal_power._read", side_effect=lambda p: {
             "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor": "powersave",
             "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference": "balance_performance",
             "/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver": "intel_pstate",
             "/sys/devices/system/cpu/intel_pstate/no_turbo": "0",
             "/sys/firmware/acpi/platform_profile": "performance",
             "/sys/firmware/acpi/platform_profile_choices": "low-power balanced performance",
         }.get(p, "")):
        result = ThermalPowerModule().scan()

    assert any("88.0°C" in f.title and f.severity == Severity.WARNING for f in result.findings)
    assert any("Firefox" in f.detail or "firefox" in f.detail for f in result.findings)
    assert any("TLP" in f.title for f in result.findings)


def test_apply_is_strictly_read_only():
    result = ThermalPowerModule().apply()
    assert result.success
    assert "تشخيصية فقط" in result.message
