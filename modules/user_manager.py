#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/user_manager.py
========================
فحص المستخدمين على النظام — عدد المستخدمين، وجود sudoers.
وحدة إخبارية بحتة (لا تعدّل مستخدمين تلقائياً).
مستوحى من Garuda Assistant → User Accounts.
"""
from __future__ import annotations

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("user_manager")


def _list_users() -> list[tuple[str, str]]:
    """يُرجع (اسم المستخدم, الاسم الكامل)."""
    r = run_unprivileged(["getent", "passwd"])
    users = []
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 5:
            uid = int(parts[2])
            if 1000 <= uid < 65534:  # مستخدمون حقيقيون (تخطي system)
                users.append((parts[0], parts[4] or parts[0]))
    return users


def _has_sudo(user: str) -> bool:
    r = run_unprivileged(["groups", user])
    return "wheel" in r.stdout or "sudo" in r.stdout


class UserManagerModule(MaintenanceModule):
    name = "حسابات المستخدمين"
    slug = "user_manager"
    description = "عرض المستخدمين وصلاحياتهم — إخباري فقط"
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "system-users"

    def scan(self) -> ScanResult:
        users = _list_users()
        findings: list[ScanFinding] = []

        if not users:
            findings.append(ScanFinding(
                title="لا يوجد مستخدمون عاديون",
                detail="",
                severity=Severity.INFO,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        lines = []
        for u, name in users:
            sudo = "sudo ✓" if _has_sudo(u) else "لا sudo"
            lines.append(f"  • {u} ({name}) — {sudo}")

        findings.append(ScanFinding(
            title=f"{len(users)} مستخدم/مستخدمين",
            detail="\n".join(lines),
            severity=Severity.INFO,
            actionable=False,
            raw_value=users,
        ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(description="وحدة إخبارية — استخدم manjaro-settings-manager أو useradd/usermod يدوياً.")]

    def apply(self) -> ApplyResult:
        return ApplyResult(success=True, message="لا إجراء تلقائي لهذه الوحدة.")
