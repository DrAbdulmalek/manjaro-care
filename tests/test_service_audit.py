#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest.mock import patch

from core.privilege import CommandResult
from modules.service_audit import ServiceAuditModule


def test_reports_retired_update_shutdown_without_removing_script():
    with patch(
        "modules.service_audit.run_unprivileged",
        return_value=CommandResult(
            0, "LoadState=not-found\nActiveState=inactive\nFragmentPath=\n", ""
        ),
    ), patch("modules.service_audit.Path.resolve", side_effect=OSError), \
         patch("modules.service_audit.Path.is_file", return_value=False):
        result = ServiceAuditModule().scan()

    assert len(result.findings) == 1
    assert "متقاعدة" in result.findings[0].title
    assert result.findings[0].actionable is False


def test_unknown_systemctl_result_is_not_reported_as_retired():
    with patch(
        "modules.service_audit.run_unprivileged",
        return_value=CommandResult(1, "", "systemctl unavailable"),
    ):
        result = ServiceAuditModule().scan()

    assert "تعذر" in result.findings[0].title
    assert result.findings[0].severity.name == "INFO"


def test_apply_never_deletes_or_disables_anything():
    result = ServiceAuditModule().apply()
    assert result.success
    assert "لم تُعطّل" in result.message
