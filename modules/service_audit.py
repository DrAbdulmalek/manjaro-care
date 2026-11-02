#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تدقيق وحدة update_shutdown المتقاعدة وبقاياها — قراءة فقط."""
from __future__ import annotations

from pathlib import Path

from core.module_base import (\n    ApplyResult,\n    MaintenanceModule,\n    PreviewStep,\n    RiskLevel,\n    ScanFinding,\n    ScanResult,\n    Severity,\n)
from core.privilege import run_unprivileged


class ServiceAuditModule(MaintenanceModule):
    name = "تدقيق الخدمات المخصصة المتقاعدة"
    slug = "service_audit"
    description = "يتحقق من update_shutdown.service وملفاتها وسكربتها المحفوظ؛ لا يحذف أو يعطل شيئاً"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "applications-system"

    def scan(self) -> ScanResult:
        result = run_unprivileged(["systemctl", "show", "update_shutdown.service",
            "--property=LoadState", "--property=ActiveState", "--property=FragmentPath", "--no-pager"])
        state = {}
        if result.ok:
            for line in result.stdout.splitlines():
                key, sep, value = line.partition("=")
                if sep:
                    state[key] = value
        paths = [Path("/etc/systemd/system/update_shutdown.service"),
                 Path("/usr/lib/systemd/system/update_shutdown.service"),
                 Path("/lib/systemd/system/update_shutdown.service")]
        existing, seen = [], set()
        for path in paths:
            try:
                resolved = str(path.resolve(strict=True))
            except OSError:
                continue
            if resolved not in seen:
                seen.add(resolved)
                existing.append(str(path))
        script_exists = Path("/usr/local/bin/update_shutdown").is_file()
        load_state = state.get("LoadState", "unknown")
        if not result.ok:
            finding = ScanFinding(title="تعذر التحقق من update_shutdown.service",
                detail=result.stderr.strip() or "تعذر قراءة systemctl show؛ لا يمكن الجزم بالحالة.",
                severity=Severity.INFO, actionable=False)
        elif load_state == "not-found" and not existing:
            detail = "الوحدة غير محمّلة ولا توجد ملفات unit قياسية."
            if script_exists:
                detail += " السكربت ما زال محفوظاً؛ وجوده لا يعني أن الخدمة تعمل."
            finding = ScanFinding(title="update_shutdown.service متقاعدة وغير محمّلة",
                detail=detail, severity=Severity.OK, actionable=False)
        elif load_state == "loaded" or existing:
            finding = ScanFinding(title="عُثر على وحدة أو بقايا update_shutdown",
                detail=f"LoadState={load_state}; ActiveState={state.get('ActiveState', 'unknown')}; "
                       f"FragmentPath={state.get('FragmentPath', 'غير معروف')}\n" +
                       "\n".join(existing) + ("\nيوجد السكربت /usr/local/bin/update_shutdown." if script_exists else "") +
                       "\nتدقيق فقط؛ لا تعطيل ولا حذف تلقائي.",
                severity=Severity.WARNING, actionable=False)
        else:
            finding = ScanFinding(title="حالة update_shutdown غير محسومة",
                detail=f"LoadState={load_state}; ActiveState={state.get('ActiveState', 'unknown')}",
                severity=Severity.INFO, actionable=False)
        return ScanResult(module_name=self.name, findings=[finding])

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="قراءة حالة الوحدة وملفاتها فقط؛ لا توجد أوامر تغيير.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="تدقيق للقراءة فقط؛ لم تُعطّل خدمة ولم يُحذف أي ملف أو سجل.")
