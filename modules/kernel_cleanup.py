#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/kernel_cleanup.py
============================
يكتشف نُوى Linux المثبَّتة (حزم مثل linux515, linux61...) ويقترح إزالة
القديمة منها، مع الإبقاء دائماً على:
  1) النواة التي يعمل عليها النظام حالياً (لا يمكن حذفها أبداً)
  2) أحدث نواة مثبَّتة (حتى لو لم تكن قيد التشغيل الآن)

هذه الوحدة الأكثر حساسية في المشروع — خطأ في تحديد "النواة الحالية"
قد يعطّل الإقلاع. لذلك:
  - risk_level = DESTRUCTIVE (يظهر تحذير أوضح في الواجهة)
  - apply() يرفض العمل إن تعذّر تحديد النواة الحالية بثقة، بدل التخمين
  - لا يحذف النواة الحالية تحت أي ظرف، حتى لو طلب المستخدم ذلك
"""

from __future__ import annotations
import re

from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged, run_privileged
from core.logger import get_logger

log = get_logger("kernel_cleanup")

_KERNEL_PKG_RE = re.compile(r"^linux(\d+)$")


def _installed_kernel_packages() -> list[str]:
    """يُرجع أسماء حزم النوى المثبَّتة، مثل ['linux54', 'linux515', 'linux61']."""
    result = run_unprivileged(["pacman", "-Qq"])
    if not result.ok:
        return []
    packages = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if _KERNEL_PKG_RE.match(name):
            packages.append(name)
    return packages


def _running_kernel_package() -> str | None:
    """
    يحوّل uname -r (مثل '6.6.10-1-MANJARO') إلى اسم حزمة متوقَّع
    (مثل 'linux66'). يُرجع None إن تعذّر التطابق بثقة — في هذه الحالة
    apply() يرفض المتابعة بدل التخمين.
    """
    result = run_unprivileged(["uname", "-r"])
    if not result.ok:
        return None
    match = re.match(r"(\d+)\.(\d+)", result.stdout.strip())
    if not match:
        return None
    major, minor = match.groups()
    candidate = f"linux{major}{minor}"

    installed = _installed_kernel_packages()
    if candidate in installed:
        return candidate

    # النظام قد يستخدم نواة بأرقام مختلفة عن اسم الحزمة (نادر لكن ممكن)؛
    # لا نخمّن — نُرجع None ونترك apply() يرفض العمل بأمان.
    return None


def _kernel_version_key(pkg_name: str) -> int:
    match = _KERNEL_PKG_RE.match(pkg_name)
    return int(match.group(1)) if match else 0


class KernelCleanupModule(MaintenanceModule):
    name = "تنظيف نُوى Linux القديمة"
    slug = "kernel_cleanup"
    description = "إزالة نُوى Linux غير المستخدمة، مع إبقاء النواة الحالية والأحدث دائماً"
    needs_root = True
    risk_level = RiskLevel.DESTRUCTIVE
    icon = "system-software-update"

    def scan(self) -> ScanResult:
        installed = _installed_kernel_packages()
        running = _running_kernel_package()
        findings: list[ScanFinding] = []

        if len(installed) <= 2:
            findings.append(ScanFinding(
                title=f"{len(installed)} نواة مثبَّتة فقط",
                detail="لا حاجة للتنظيف — العدد الحالي معقول.",
                severity=Severity.OK,
                actionable=False,
            ))
            return ScanResult(module_name=self.name, findings=findings)

        removable = self._compute_removable(installed, running)
        if removable:
            findings.append(ScanFinding(
                title=f"{len(removable)} نواة قديمة قابلة للإزالة",
                detail=(
                    f"مثبَّت حالياً: {', '.join(sorted(installed))}\n"
                    f"النواة العاملة الآن: {running or 'تعذّر تحديدها بثقة'}\n"
                    f"مرشّحة للإزالة: {', '.join(removable)}"
                ),
                severity=Severity.WARNING,
                actionable=bool(running),  # لا نسمح بالإجراء إن تعذّر تحديد النواة الحالية
                raw_value=removable,
            ))
        else:
            findings.append(ScanFinding(
                title="لا نُوى قابلة للإزالة بأمان",
                detail="تعذّر تحديد النواة الحالية بثقة كافية — لن تُقترح إزالة تلقائية.",
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(module_name=self.name, findings=findings)

    @staticmethod
    def _compute_removable(installed: list[str], running: str | None) -> list[str]:
        if not running or running not in installed:
            return []  # لا نتصرف أبداً دون تحديد موثوق للنواة الحالية
        newest = max(installed, key=_kernel_version_key)
        keep = {running, newest}
        return sorted(pkg for pkg in installed if pkg not in keep)

    def preview(self) -> list[PreviewStep]:
        installed = _installed_kernel_packages()
        running = _running_kernel_package()
        removable = self._compute_removable(installed, running)

        if not removable:
            return [PreviewStep(
                description="لا يوجد إجراء آمن للتنفيذ حالياً (تعذّر تحديد النواة الحالية بثقة).",
            )]

        packages_and_headers = []
        for pkg in removable:
            packages_and_headers.append(pkg)
            packages_and_headers.append(f"{pkg}-headers")  # إن وُجدت حزمة headers مرافقة

        return [PreviewStep(
            description=f"إزالة النُوى القديمة: {', '.join(removable)} (مع حزم headers المرافقة إن وُجدت)",
            command="pacman -Rns " + " ".join(packages_and_headers),
        )]

    def apply(self) -> ApplyResult:
        installed = _installed_kernel_packages()
        running = _running_kernel_package()

        if not running or running not in installed:
            return ApplyResult(
                success=False,
                message="تم رفض التنفيذ عمداً: تعذّر تحديد النواة الحالية بثقة كافية — "
                        "لتفادي أي احتمال لحذف نواة قيد التشغيل.",
            )

        removable = self._compute_removable(installed, running)
        if not removable:
            return ApplyResult(success=True, message="لا نُوى قديمة تحتاج إزالة")

        # أمان إضافي: تأكيد صريح أن النواة الحالية ليست ضمن قائمة الحذف
        assert running not in removable, "خطأ داخلي: النواة الحالية ضمن قائمة الحذف!"

        targets = []
        for pkg in removable:
            targets.append(pkg)
            targets.append(f"{pkg}-headers")

        result = run_privileged(["pacman", "-Rns", "--noconfirm", *targets])
        if result.ok:
            return ApplyResult(
                success=True,
                message=f"تمت إزالة النُوى القديمة: {', '.join(removable)}",
                log_output=result.stdout + result.stderr,
            )
        return ApplyResult(
            success=False,
            message=f"فشلت الإزالة (كود {result.returncode}) — قد تكون بعض حزم headers غير مثبتة أصلاً، وهذا طبيعي",
            log_output=result.stdout + result.stderr,
        )
