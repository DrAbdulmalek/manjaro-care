#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest.mock import patch

from core.privilege import CommandResult
from modules.service_audit import ServiceAuditModule


def test_reports_retired_units_and_keeps_script_as_non_active_residue():
    state = CommandResult(
        0,
        "LoadState=not-found\nActiveState=inactive\n"
        "UnitFileState=\nFragmentPath=\n",
        "",
    )
    with patch("modules.service_audit.run_unprivileged", return_value=state), \
         patch("modules.service_audit.Path.is_file", return_value=True), \
         patch("modules.service_audit.Path.iterdir", side_effect=FileNotFoundError), \
         patch("modules.service_audit.Path.open", side_effect=FileNotFoundError):
        result = ServiceAuditModule().scan()

    titles = [finding.title for finding in result.findings]
    assert any("غير محمّلة" in title for title in titles)
    assert all(finding.actionable is False for finding in result.findings)


def test_unknown_systemctl_result_is_not_reported_as_retired():
    with patch(
        "modules.service_audit.run_unprivileged",
        return_value=CommandResult(1, "", "systemctl unavailable"),
    ), patch("modules.service_audit.Path.iterdir", side_effect=FileNotFoundError):
        result = ServiceAuditModule().scan()

    assert any("غير محسومة" in finding.title for finding in result.findings)
    assert all(finding.actionable is False for finding in result.findings)


def test_detects_dns_failure_and_cache_unmount_without_claiming_root_cause():
    def command(args, timeout=30):
        if args[0] == "systemctl":
            return CommandResult(
                0,
                "LoadState=not-found\nActiveState=inactive\nUnitFileState=\nFragmentPath=\n",
                "",
            )
        if args[0] == "journalctl":
            return CommandResult(
                0,
                "Could not resolve host: mirror.example\n"
                "Failed unmounting /var/cache.\n",
                "",
            )
        return CommandResult(0, "", "")

    with patch("modules.service_audit.run_unprivileged", side_effect=command), \
         patch("modules.service_audit.Path.iterdir", side_effect=FileNotFoundError), \
         patch("modules.service_audit.Path.is_file", return_value=False):
        result = ServiceAuditModule().scan()

    titles = [finding.title for finding in result.findings]
    assert any("DNS" in title for title in titles)
    assert any("/var/cache" in title for title in titles)
    assert all(finding.actionable is False for finding in result.findings)


def test_apply_never_deletes_disables_or_updates():
    result = ServiceAuditModule().apply()
    assert result.success
    assert "لم تُعطّل" in result.message
    assert "لم تُنفّذ تحديثات" in result.message


def test_preview_is_explicitly_read_only():
    steps = ServiceAuditModule().preview()
    assert all("لا يوجد أي إجراء" in step.description or "قراءة" in step.description
               for step in steps)
