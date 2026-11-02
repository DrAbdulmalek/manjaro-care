#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest.mock import patch

from core.privilege import CommandResult
from modules.service_audit import ServiceAuditModule


def test_reports_retired_update_shutdown_without_removing_script():
    def fake(args, timeout=30):
        if args[:2] == ["systemctl", "--failed"]:
            return CommandResult(0, "", "")
        if args[:3] == ["systemctl", "show", "update_shutdown.service"]:
            return CommandResult(0, "LoadState=not-found\nActiveState=inactive\nFragmentPath=\n", "")
        return CommandResult(1, "", "")

    with patch("modules.service_audit.run_unprivileged", side_effect=fake), \
         patch("modules.service_audit.Path.exists", return_value=False):
        result = ServiceAuditModule().scan()
    assert any("متقاعدة" in f.title for f in result.findings)
    assert not any(f.actionable for f in result.findings)
