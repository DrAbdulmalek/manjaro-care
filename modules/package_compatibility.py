#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تدقيق توافق قاعدة الحزم والحزم الأجنبية ومؤشرات إعادة البناء — قراءة فقط."""
from __future__ import annotations

import shutil

from core.module_base import (
    ApplyResult,
    MaintenanceModule,
    PreviewStep,
    RiskLevel,
    ScanFinding,
    ScanResult,
    Severity,
)
from core.privilege import run_unprivileged


class PackageCompatibilityModule(MaintenanceModule):
    name = "توافق الحزم والمكتبات"
    slug = "package_compatibility"
    description = (
        "يفحص اتساق قاعدة pacman والحزم الأجنبية ومؤشرات checkrebuild "
        "بعد تغيّر المكتبات؛ لا يثبت أو يعيد بناء أي حزمة"
    )
    needs_root = False
    risk_level = RiskLevel.SAFE
    icon = "package-x-generic"

    def scan(self) -> ScanResult:
        findings: list[ScanFinding] = []

        database = run_unprivileged(["pacman", "-Dk"])
        if database.ok:
            findings.append(ScanFinding(
                title="اتساق قاعدة بيانات الحزم: سليم",
                detail=database.stdout.strip()[:1800],
                severity=Severity.OK, actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="pacman أبلغ عن مشكلة في اتساق قاعدة الحزم",
                detail=(database.stdout + "\n" + database.stderr).strip()[:2500],
                severity=Severity.WARNING, actionable=False,
            ))

        foreign = run_unprivileged(["pacman", "-Qm"])
        if foreign.ok:
            packages = [line.strip() for line in foreign.stdout.splitlines() if line.strip()]
            if packages:
                findings.append(ScanFinding(
                    title=f"{len(packages)} حزمة أجنبية/محلية خارج قواعد المستودعات المتزامنة",
                    detail=(
                        "\n".join(packages[:60])
                        + ("\n... توجد نتائج إضافية." if len(packages) > 60 else "")
                        + "\nالحزمة الأجنبية ليست معطوبة تلقائياً؛ هذه قائمة للمراجعة فقط."
                    ),
                    severity=Severity.INFO, actionable=False, raw_value=packages,
                ))
            else:
                findings.append(ScanFinding(
                    title="لا توجد حزم أجنبية مسجلة",
                    detail="", severity=Severity.OK, actionable=False,
                ))
        else:
            findings.append(ScanFinding(
                title="تعذر قراءة قائمة الحزم الأجنبية",
                detail=foreign.stderr.strip() or "فشل pacman -Qm.",
                severity=Severity.INFO, actionable=False,
            ))

        if shutil.which("checkrebuild"):
            rebuild = run_unprivileged(["checkrebuild"])
            output = (rebuild.stdout + "\n" + rebuild.stderr).strip()
            normalized = output.casefold()
            no_rebuild_needed = (
                not output
                or "no packages need to be rebuilt" in normalized
                or "no packages require rebuilding" in normalized
                or "no rebuilds needed" in normalized
            )
            if rebuild.ok and no_rebuild_needed:
                findings.append(ScanFinding(
                    title="checkrebuild لم يُرجع تحذيرات",
                    detail="لم تظهر حزم تتطلب إعادة بناء في مخرجات الأداة.",
                    severity=Severity.OK, actionable=False,
                ))
            elif rebuild.ok:
                findings.append(ScanFinding(
                    title="checkrebuild أظهر عناصر تستحق المراجعة",
                    detail=output[:3000],
                    severity=Severity.WARNING, actionable=False,
                ))
            else:
                findings.append(ScanFinding(
                    title="تعذر إكمال checkrebuild",
                    detail=output[:2000] or "فشلت الأداة؛ لا يمكن استنتاج حالة التوافق.",
                    severity=Severity.INFO, actionable=False,
                ))
        else:
            findings.append(ScanFinding(
                title="فحص إعادة بناء الحزم غير متاح",
                detail="أداة checkrebuild غير مثبتة؛ لم يُثبّت التطبيق أي أداة ولم يستنتج وجود خلل.",
                severity=Severity.INFO, actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        return [PreviewStep(
            description="فحص قراءة فقط لقاعدة pacman والحزم الأجنبية ومخرجات checkrebuild؛ لا تثبيت أو إزالة أو إعادة بناء."
        )]

    def apply(self) -> ApplyResult:
        return ApplyResult(
            success=True,
            message="هذه الوحدة تشخيصية فقط؛ لم تُحدّث الحزم أو تثبتها أو تعِد بناءها.",
        )
