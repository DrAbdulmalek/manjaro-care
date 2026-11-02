from unittest.mock import patch

from core.module_base import Severity
from core.privilege import CommandResult
from modules.thermal_power import ThermalPowerModule, parse_fan_speeds, parse_process_cpu, parse_temperatures


def test_parsers_handle_temperature_fan_and_process_output():
    assert parse_temperatures("Package id 0: +88.0°C\nCore 0: +80.0°C\n") == [("Package id 0", 88.0), ("Core 0", 80.0)]
    assert parse_fan_speeds("fan1: 2100 RPM\npwm1: N/A\n") == [("fan1", 2100)]
    assert parse_process_cpu("22.4 firefox\n5.1 kwin\ninvalid\n") == [(22.4, "firefox"), (5.1, "kwin")]


def test_scan_flags_high_temperature_and_keeps_it_read_only():
    def fake(args, timeout=30):
        if args[0] == "sensors":
            return CommandResult(0, "Package id 0: +88.0°C\n", "")
        if args[0] == "ps":
            return CommandResult(0, "30.0 firefox\n", "")
        if args[:3] == ["systemctl", "is-active", "tlp.service"]:
            return CommandResult(0, "active\n", "")
        if args[:3] == ["systemctl", "is-active", "power-profiles-daemon.service"]:
            return CommandResult(3, "inactive\n", "")
        return CommandResult(1, "", "unavailable")
    with patch("modules.thermal_power.run_unprivileged", side_effect=fake), patch("modules.thermal_power.shutil.which", return_value=None), patch("modules.thermal_power._read", return_value=""):
        result = ThermalPowerModule().scan()
    assert any(f.severity == Severity.WARNING and "88.0" in f.title for f in result.findings)
    assert ThermalPowerModule().apply().success
