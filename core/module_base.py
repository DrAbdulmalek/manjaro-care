#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/module_base.py
====================
الكلاس الأساسي (Abstract Base Class) الذي يجب أن ترثه كل وحدة صيانة.

الفلسفة: كل وحدة يجب أن تفصل بوضوح بين:
  1) scan()    — فحص القراءة فقط، لا يغيّر شيئاً في النظام إطلاقاً.
  2) preview() — يشرح بالتفصيل ماذا سيحدث *قبل* أي تنفيذ (بالأوامر الفعلية
                 إن أمكن)، حتى يستطيع المستخدم اتخاذ قرار واعٍ.
  3) apply()   — التنفيذ الفعلي، ويُستدعى فقط بعد موافقة المستخدم الصريحة.

هذا يمنع نمط "زر نظّف الآن" الغامض الذي تنتقده أدوات مثل Advanced
SystemCare، ويحافظ على شفافية reset-net نفسها (لوغ + تفسير واضح).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    SAFE = "safe"               # لا خطر، قابل للتراجع أو بلا أثر يُذكر
    MODERATE = "moderate"       # يغيّر حالة النظام لكن قابل للتصحيح
    DESTRUCTIVE = "destructive"  # لا يمكن التراجع عنه بسهولة (حذف نهائي مثلاً)


class Severity(str, Enum):
    OK = "ok"           # كل شيء طبيعي
    INFO = "info"        # ملاحظة بسيطة، لا تستدعي القلق
    WARNING = "warning"  # يستحق الانتباه
    CRITICAL = "critical"  # يستحق التصرف السريع


@dataclass
class ScanFinding:
    """نتيجة فحص واحدة قابلة للعرض كبطاقة في الواجهة."""
    title: str                     # عنوان مختصر بالعربية
    detail: str                    # شرح تفصيلي
    severity: Severity = Severity.INFO
    actionable: bool = True        # هل يوجد إجراء يمكن تطبيقه لحل هذا الشيء؟
    raw_value: object = None       # القيمة الخام (عدد الحزم، حجم بالبايت...) لأغراض الفرز/الاختبار


@dataclass
class ScanResult:
    """نتيجة scan() الكاملة لوحدة واحدة."""
    module_name: str
    findings: list[ScanFinding] = field(default_factory=list)
    error: str | None = None       # إن فشل الفحص نفسه (صلاحيات، أداة غير مثبتة...)

    @property
    def worst_severity(self) -> Severity:
        order = [Severity.CRITICAL, Severity.WARNING, Severity.INFO, Severity.OK]
        present = {f.severity for f in self.findings}
        for level in order:
            if level in present:
                return level
        return Severity.OK


@dataclass
class PreviewStep:
    """خطوة واحدة ستُنفَّذ، مع الأمر الفعلي إن وُجد (للشفافية الكاملة)."""
    description: str
    command: str | None = None     # الأمر الحرفي الذي سيُنفَّذ، إن كان قابلاً للعرض


@dataclass
class ApplyResult:
    success: bool
    message: str
    log_output: str = ""


class MaintenanceModule(ABC):
    """كل وحدة صيانة (تنظيف حزم، journal، mirrors...) ترث من هذا الكلاس."""

    # ---- بيانات وصفية يجب على كل وحدة تعريفها ----
    name: str = "وحدة بلا اسم"
    slug: str = "unnamed"          # معرّف فريد بالإنجليزية (لأسماء الملفات/اللوغ)
    description: str = ""
    needs_root: bool = False
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "applications-system"  # اسم أيقونة من ثيمات freedesktop

    # إن كانت True، تعرض بطاقة الوحدة زر "إدارة فردية" إضافياً يفتح نافذة
    # مخصصة (مسجَّلة في gui/custom_dialogs.py) بدل الاعتماد فقط على
    # نمط فحص/معاينة/تطبيق الجماعي — مناسب لحالات مثل قائمة عناصر كل
    # واحد منها قرار مستقل (برامج بدء التشغيل مثلاً).
    has_custom_ui: bool = False

    @abstractmethod
    def scan(self) -> ScanResult:
        """فحص للقراءة فقط. يجب ألا يُغيّر أي حالة في النظام."""
        raise NotImplementedError

    @abstractmethod
    def preview(self) -> list[PreviewStep]:
        """يُرجع قائمة الخطوات التي سيُنفّذها apply(), مع الأوامر الفعلية إن أمكن."""
        raise NotImplementedError

    @abstractmethod
    def apply(self) -> ApplyResult:
        """التنفيذ الفعلي. يجب استدعاؤه فقط بعد موافقة المستخدم على preview()."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<MaintenanceModule slug={self.slug!r} risk={self.risk_level}>"
