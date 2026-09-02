#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/performance_optimizer.py — تحسين أداء النظام (TuneUp Utilities)."""
from __future__ import annotations
import shutil
from pathlib import Path
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_privileged, run_unprivileged
from core.logger import get_logger

log = get_logger("performance_optimizer")


def _service_enabled(name: str) -> bool:
    r = run_unprivileged(["systemctl", "is-enabled", name])
    return r.ok and "enabled" in r.stdout


def _service_active(name: str) -> bool:
    r = run_unprivileged(["systemctl", "is-active", name])
    return r.ok and "active" in r.stdout


class PerformanceOptimizerModule(MaintenanceModule):
    name = "تحسين الأداء ⚡"
    slug = "performance_optimizer"
    description = "تفعيل zram, ananicy, preload, fstrim لتحسين الاستجابة"
    needs_root = True
    risk_level = RiskLevel.MODERATE
    icon = "preferences-system-performance"

    def scan(self):
        findings = []
        recommendations = []

        # 1. zram
        if _service_active("systemd-zram-setup@zram0") or Path("/sys/block/zram0").exists():
            findings.append(ScanFinding(
                title="zram مفعّل ✅",
                detail="الضغط في الذاكرة يعمل.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            recommendations.append("zram")
            findings.append(ScanFinding(
                title="zram معطّل",
                detail="يُنصح بتفعيله لتقليل استخدام SWAP على القرص.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        # 2. ananicy (nice levels للعمليات)
        if shutil.which("ananicy"):
            if _service_active("ananicy"):
                findings.append(ScanFinding(
                    title="ananicy يعمل ✅",
                    detail="إدارة أولويات العمليات نشطة.",
                    severity=Severity.OK,
                    actionable=False,
                ))
            else:
                recommendations.append("ananicy")
                findings.append(ScanFinding(
                    title="ananicy متوقف",
                    detail="تفعيله يحسن استجابة سطح المكتب.",
                    severity=Severity.WARNING,
                    actionable=True,
                ))
        else:
            recommendations.append("ananicy")
            findings.append(ScanFinding(
                title="ananicy غير مثبت",
                detail="ثبّته من AUR: yay -S ananicy",
                severity=Severity.INFO,
                actionable=True,
            ))

        # 3. preload
        if shutil.which("preload"):
            if _service_active("preload"):
                findings.append(ScanFinding(
                    title="preload يعمل ✅",
                    detail="تحميل مسبق للتطبيقات الشائعة.",
                    severity=Severity.OK,
                    actionable=False,
                ))
            else:
                recommendations.append("preload")
                findings.append(ScanFinding(
                    title="preload متوقف",
                    detail="تفعيله يُسرّع فتح التطبيقات.",
                    severity=Severity.WARNING,
                    actionable=True,
                ))
        else:
            recommendations.append("preload")
            findings.append(ScanFinding(
                title="preload غير مثبت",
                detail="sudo pacman -S preload",
                severity=Severity.INFO,
                actionable=True,
            ))

        # 4. fstrim (SSD TRIM)
        if _service_enabled("fstrim.timer"):
            findings.append(ScanFinding(
                title="fstrim.timer مفعّل ✅",
                detail="صيانة دورية لأقراص SSD.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            recommendations.append("fstrim")
            findings.append(ScanFinding(
                title="fstrim.timer معطّل",
                detail="مهم لأداء SSD على المدى الطويل.",
                severity=Severity.WARNING,
                actionable=True,
            ))

        # 5. zswap (بديل/مكمل لـ zram)
        zswap = run_unprivileged(["bash", "-c", "cat /sys/module/zswap/parameters/enabled 2>/dev/null"]).stdout.strip()
        if zswap == "Y":
            findings.append(ScanFinding(
                title="zswap مفعّل ✅",
                detail="ضغط SWAP في الذاكرة.",
                severity=Severity.OK,
                actionable=False,
            ))
        else:
            findings.append(ScanFinding(
                title="zswap معطّل",
                detail="يمكن تفعيله عبر kernel parameter.",
                severity=Severity.INFO,
                actionable=False,
            ))

        return ScanResult(
            module_name=self.name,
            findings=findings,
            raw_value=recommendations,
        )

    def preview(self):
        steps = []
        recs = self.scan().raw_value or []

        if "zram" in recs:
            steps.append(PreviewStep(
                description="تثبيت وتفعيل zram-generator",
                command="pacman -S --noconfirm zram-generator && systemctl enable --now systemd-zram-setup@zram0",
            ))
        if "ananicy" in recs:
            steps.append(PreviewStep(
                description="تثبيت ananicy من AUR وتفعيله",
                command="yay -S --noconfirm ananicy && systemctl enable --now ananicy",
            ))
        if "preload" in recs:
            steps.append(PreviewStep(
                description="تثبيت وتفعيل preload",
                command="pacman -S --noconfirm preload && systemctl enable --now preload",
            ))
        if "fstrim" in recs:
            steps.append(PreviewStep(
                description="تفعيل fstrim.timer",
                command="systemctl enable --now fstrim.timer",
            ))

        return steps or [PreviewStep(description="كل محسّنات الأداء مفعّلة! 🚀")]

    def apply(self):
        logs = []
        success = True
        recs = self.scan().raw_value or []

        if "zram" in recs:
            r1 = run_privileged(["pacman", "-S", "--noconfirm", "zram-generator"])
            logs.append(r1.stdout + r1.stderr)
            # إنشاء ملف الإعداد
            zram_conf = "/etc/systemd/zram-generator.conf"
            conf_text = "[zram0]\nzram-size = ram / 2\ncompression-algorithm = zstd\n"
            r1b = run_privileged(["bash", "-c", f"cat > {zram_conf} << 'EOF'\n{conf_text}EOF"])
            r1c = run_privileged(["systemctl", "daemon-reload"])
            r1d = run_privileged(["systemctl", "start", "systemd-zram-setup@zram0"])
            if not r1d.ok:
                success = False

        if "ananicy" in recs:
            if shutil.which("yay"):
                r2 = run_privileged(["bash", "-c", "sudo -u $SUDO_USER yay -S --noconfirm ananicy 2>/dev/null || true"])
            else:
                r2 = run_privileged(["git", "clone", "https://aur.archlinux.org/ananicy.git", "/tmp/ananicy-build"])
                if r2.ok:
                    r2 = run_privileged(["bash", "-c", "cd /tmp/ananicy-build && makepkg -si --noconfirm"])
            logs.append(r2.stdout + r2.stderr if hasattr(r2, 'stdout') else "")
            r2b = run_privileged(["systemctl", "enable", "--now", "ananicy"])
            if not r2b.ok:
                success = False

        if "preload" in recs:
            r3 = run_privileged(["pacman", "-S", "--noconfirm", "preload"])
            r3b = run_privileged(["systemctl", "enable", "--now", "preload"])
            logs.append(r3.stdout + r3.stderr)
            if not r3b.ok:
                success = False

        if "fstrim" in recs:
            r4 = run_privileged(["systemctl", "enable", "--now", "fstrim.timer"])
            logs.append(r4.stdout + r4.stderr)
            if not r4.ok:
                success = False

        return ApplyResult(
            success=success,
            message="تم تطبيق تحسينات الأداء 🚀" if success else "فشل جزئي",
            log_output="\n".join(logs),
        )
