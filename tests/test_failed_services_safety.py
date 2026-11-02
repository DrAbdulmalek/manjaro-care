#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest.mock import patch

from core.privilege import CommandResult
from modules.failed_services import FailedServicesModule


def test_scan_never_restarts_failed_units():
    with patch("modules.failed_services.run_unprivileged",
               return_value=CommandResult(0, "tlp.service loaded failed failed TLP\n", "")) as command:
        result = FailedServicesModule().scan()
        assert result.findings[0].actionable is False
        assert "journalctl -u tlp.service" in result.findings[0].detail
        command.assert_called_once()


def test_preview_is_read_only():
    with patch("modules.failed_services.run_unprivileged",
               return_value=CommandResult(0, "tlp.service loaded failed failed TLP\n", "")):
        steps = FailedServicesModule().preview()
    assert "journalctl" in steps[0].command
    assert "restart" not in steps[0].command


def test_apply_does_not_restart_any_service():
    result = FailedServicesModule().apply()
    assert result.success
    assert "لم تُعَد تشغيل" in result.message


def test_module_source_has_no_privileged_or_restart_path():
    """حرس هيكلي ضد انتكاسة سلوك إعادة التشغيل الجماعي المحذوف.

    الوحدة لا تستورد run_privileged أصلاً (قصد)؛ إن أُعيد إدخال أي مسار
    إعادة تشغيل أو تنفيذ مرتفع الصلاحيات مستقبلاً فسيفشل هذا الاختبار.
    """
    import inspect

    from modules import failed_services

    source = inspect.getsource(failed_services)
    assert "run_privileged" not in source
    assert "restart" not in source
    assert "reset-failed" not in source
    assert "try-restart" not in source
