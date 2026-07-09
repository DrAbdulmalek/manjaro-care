#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/pkg_cleanup.py
=======================
تنظيف الحزم اليتيمة (orphans) وكاش pacman القديم.

الفحص (scan) للقراءة فقط:
  - pacman -Qtdq             → قائمة الحزم اليتيمة (لا تعتمد عليها أي حزمة أخرى)
  - حساب حجم /var/cache/pacman/pkg

التطبيق (apply) يحتاج جذر لأنه يعدّل قاعدة بيانات الحزم والكاش:
  - pacman -Rns <الحزم اليتيمة>   (بعد موافقة صريحة، مع قائمة الأسماء)
  - paccache -r                   (يبقي آخر 3 نسخ فقط من كل حزمة، النمط الافتراضي الآمن)
"""

from __future__ import annotations

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("pkg_cleanup")


def _get_orphans() -> list[str]:
    result = run_unprivileged(["pacman", "-Qtdq"])
    if not result.ok:
        # pacman -Qtdq يُرجع كود خروج غير صفري إن لم توجد حزم يتيمة — هذا طبيعي، ليس خطأ
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_cache_size_mb() -> float:
    result = run_unprivileged(["du", "-sm", "/var/cache/pacman/pkg"])
    if not result.ok or not result.stdout.strip():
        return 0.0
    try:
        return float(result.stdout.split()[0])
    except (ValueError, IndexError):
        return 0.0


class PackageCleanupModule(MaintenanceModule):
    name = "تنظيف الحزم"
    slug = "pkg_cleanup"
    description = "إزالة الحزم اليتيمة وتقليص كاش pacman القديم"
    needs_root = True
    risk_level = RiskLevel.MODERATE  # حذف حزم — قابل للتراجع بإعادة التثبيت، لكن ليس فورياً
    icon = "package-x-generic"

    def scan(self) -> ScanResult:
        orphans = _get_orphans()
        cache_mb = _get_cache_size_mb()
        findings: list[ScanFinding] = []

        if orphans:
            findings.append(ScanFinding(
                title=f"{len(orphans)} حزمة يتيمة غير مستخدمة",
                detail="حزم مثبَّتة كاعتماديات لبرامج لم تعد موجودة:\n" + "\n".join(orphans),
                severity=Severity.WARNING if len(orphans) > 5 else Severity.INFO,
                raw_value=orphans,
            ))
        else:
            findings.append(ScanFinding(
                title="لا توجد حزم يتيمة",
                detail="النظام نظيف من الاعتماديات المهجورة.",
                severity=Severity.OK,
                actionable=False,
            ))

        if cache_mb > 2048:
            findings.append(ScanFinding(
                title=f"كاش pacman كبير: {cache_mb:.0f} MB",
                detail="يمكن تقليصه للاحتفاظ بآخر 3 نسخ فقط من كل حزمة (paccache -r).",
                severity=Severity.WARNING,
                raw_value=cache_mb,
            ))
        elif cache_mb > 512:
            findings.append(ScanFinding(
                title=f"حجم كاش pacman: {cache_mb:.0f} MB",
                detail="حجم معقول، لكن يمكن تقليصه إن أردت مساحة إضافية.",
                severity=Severity.INFO,
                raw_value=cache_mb,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    def preview(self) -> list[PreviewStep]:
        orphans = _get_orphans()
        steps: list[PreviewStep] = []
        if orphans:
            steps.append(PreviewStep(
                description=f"إزالة {len(orphans)} حزمة يتيمة: {', '.join(orphans)}",
                command="pacman -Rns " + " ".join(orphans),
            ))
        steps.append(PreviewStep(
            description="تقليص كاش pacman (الإبقاء على آخر 3 نسخ من كل حزمة)",
            command="paccache -r",
        ))
        return steps

    def apply(self) -> ApplyResult:
        orphans = _get_orphans()
        logs = []

        if orphans:
            result = run_privileged(["pacman", "-Rns", "--noconfirm", *orphans])
            logs.append(result.stdout + result.stderr)
            if not result.ok:
                return ApplyResult(
                    success=False,
                    message=f"فشل حذف الحزم اليتيمة (كود {result.returncode})",
                    log_output="\n".join(logs),
                )

        cache_result = run_privileged(["paccache", "-r"])
        logs.append(cache_result.stdout + cache_result.stderr)
        if not cache_result.ok:
            return ApplyResult(
                success=False,
                message="نجحت إزالة الحزم اليتيمة، لكن فشل تقليص الكاش (paccache قد يكون غير مثبت)",
                log_output="\n".join(logs),
            )

        return ApplyResult(
            success=True,
            message=f"تم: إزالة {len(orphans)} حزمة يتيمة وتقليص الكاش",
            log_output="\n".join(logs),
        )
