from core.module_base import ScanFinding, ScanResult, Severity
from core.scanner import SystemHealthReport
from gui.health_sections import build_health_sections


def test_groups_findings_and_prioritizes_critical():
    report = SystemHealthReport(results=[
        ScanResult("سلامة الإقلاع والنظام", findings=[ScanFinding("fstab", "bad", Severity.WARNING, False)]),
        ScanResult("الحرارة وإدارة الطاقة", findings=[ScanFinding("CPU hot", "91 C", Severity.CRITICAL, False)]),
        ScanResult("توافق الحزم والمكتبات", findings=[ScanFinding("foreign", "local", Severity.INFO, False)]),
    ])
    sections = build_health_sections(report)
    flattened = [f for section in sections for f in section["findings"]]
    assert flattened[0].severity == Severity.CRITICAL
    assert {s["key"] for s in sections} == {"boot_storage", "thermal_power", "packages"}


def test_empty_modules_do_not_create_synthetic_findings():
    assert build_health_sections(SystemHealthReport([ScanResult("الخدمات", findings=[])])) == []


def test_scan_error_is_visible_as_unknown_information():
    sections = build_health_sections(SystemHealthReport([ScanResult("سلامة الإقلاع والنظام", error="permission denied")]))
    assert sections[0]["findings"][0].severity == Severity.INFO
    assert "غير مكتمل" in sections[0]["findings"][0].title
