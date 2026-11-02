from unittest.mock import patch
from core.privilege import CommandResult
from modules.service_audit import ServiceAuditModule


def test_retired_service_is_reported_without_touching_script():
    with patch("modules.service_audit.run_unprivileged", return_value=CommandResult(0, "LoadState=not-found\nActiveState=inactive\nFragmentPath=\n", "")), patch("modules.service_audit.Path.resolve", side_effect=OSError), patch("modules.service_audit.Path.is_file", return_value=False):
        result = ServiceAuditModule().scan()
    assert "متقاعدة" in result.findings[0].title
    assert not result.findings[0].actionable


def test_systemctl_failure_is_unknown_not_clean():
    with patch("modules.service_audit.run_unprivileged", return_value=CommandResult(1, "", "systemctl unavailable")):
        result = ServiceAuditModule().scan()
    assert result.findings[0].severity.name == "INFO"
    assert "تعذر" in result.findings[0].title
