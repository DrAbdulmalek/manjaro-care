from unittest.mock import patch
from core.privilege import CommandResult
from modules.failed_services import FailedServicesModule


def test_failed_units_are_reported_without_restart():
    with patch("modules.failed_services.run_unprivileged", return_value=CommandResult(0, "tlp.service loaded failed failed TLP\n", "")) as command:
        result = FailedServicesModule().scan()
    assert "journalctl -u tlp.service" in result.findings[0].detail
    assert result.findings[0].actionable is False
    command.assert_called_once()


def test_apply_does_not_restart_services():
    assert "لم تُعَد تشغيل" in FailedServicesModule().apply().message
