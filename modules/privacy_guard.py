#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modules/privacy_guard.py — حماية الخصوصية ومسح الآثار (Advanced SystemCare)."""
from __future__ import annotations
import os
from pathlib import Path
from core.module_base import (
    MaintenanceModule, ScanResult, ScanFinding, Severity,
    PreviewStep, ApplyResult, RiskLevel,
)
from core.privilege import run_unprivileged
from core.logger import get_logger

log = get_logger("privacy_guard")

_PRIVACY_TARGETS = {
    "bash_history": ("~/.bash_history", "سجل أوامر bash"),
    "zsh_history": ("~/.zsh_history", "سجل أوامر zsh"),
    "recent_docs": ("~/.local/share/recently-used.xbel", "المستندات المفتوحة حديثاً"),
    "thumbnails": ("~/.cache/thumbnails", "الصور المصغرة (قد تحتوي على صور خاصة)"),
    "firefox_cache": ("~/.cache/mozilla/firefox", "كاش Firefox"),
    "chromium_cache": ("~/.cache/chromium", "كاش Chromium/Chrome"),
}


class PrivacyGuardModule(MaintenanceModule):
    name = "حماية الخصوصية 🔒"
    slug = "privacy_guard"
    description = "مسح سجل الأوامر، الملفات المؤقتة للمتصفحات، والمستندات الحديثة"
    needs_root = False
    risk_level = RiskLevel.MODERATE
    icon = "user-secret"

    def scan(self):
        findings = []
        for key, (path, desc) in _PRIVACY_TARGETS.items():
            p = Path(path).expanduser()
            if p.exists():
                size = self._get_size(p)
                findings.append(ScanFinding(
                    title=f"{desc} موجود",
                    detail=f"المسار: {p} ({self._human_size(size)})",
                    severity=Severity.INFO,
                    actionable=True,
                    raw_value=str(p),
                ))
        if not findings:
            findings.append(ScanFinding(
                title="لا آثار حساسة",
                detail="كل شيء نظيف.",
                severity=Severity.OK,
                actionable=False,
            ))
        return ScanResult(module_name=self.name, findings=findings)

    def preview(self):
        steps = []
        for key, (path, desc) in _PRIVACY_TARGETS.items():
            p = Path(path).expanduser()
            if p.exists():
                if key in ("bash_history", "zsh_history"):
                    steps.append(PreviewStep(
                        description=f"مسح {desc}",
                        command=f"> {p}",
                    ))
                else:
                    steps.append(PreviewStep(
                        description=f"حذف {desc}",
                        command=f"rm -rf {p}",
                    ))
        return steps or [PreviewStep(description="لا شيء للمسح.")]

    def apply(self):
        logs = []
        for key, (path, desc) in _PRIVACY_TARGETS.items():
            p = Path(path).expanduser()
            if not p.exists():
                continue

            try:
                if key in ("bash_history", "zsh_history"):
                    # نمسح المحتوى بدل الحذف لأن الملف مطلوب
                    p.write_text("", encoding="utf-8")
                    logs.append(f"تم مسح {desc}")
                elif p.is_dir():
                    for item in p.iterdir():
                        if item.is_dir():
                            import shutil
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                    logs.append(f"تم تنظيف {desc}")
                else:
                    p.unlink(missing_ok=True)
                    logs.append(f"تم حذف {desc}")
            except Exception as exc:
                logs.append(f"فشل في {desc}: {exc}")

        return ApplyResult(success=True, message="تم مسح الآثار", log_output="\n".join(logs))

    @staticmethod
    def _get_size(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = Path(root) / f
                    if fp.exists():
                        total += fp.stat().st_size
        except Exception:
            pass
        return total

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
