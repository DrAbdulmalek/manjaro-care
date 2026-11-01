#!/usr/bin/env bash
#
# وحدة تحليل السجلات (مُصحّحة: حماية الأنابيب والعدادات الرقمية)
#

log_analyze() {
    log_section "تحليل السجلات"
    
    # 1. أخطاء الإقلاع الحالي
    log_info "الأخطاء في الإقلاع الحالي:"
    local errors
    errors=$(journalctl -p 3 -b --no-pager 2>/dev/null | wc -l || true)
    errors=$(( ${errors:-0} + 0 ))
    log_info "يوجد $errors خطأ"
    
    # عرض أهم الأخطاء
    log_info "أهم الأخطاء:"
    journalctl -p 3 -b -o cat --no-pager 2>/dev/null | sort | uniq -c | sort -rn | head -10 | while read -r line; do
        log_warn "  $line"
    done || true
    
    # 2. أخطاء النواة
    log_info "أخطاء النواة المتعلقة بالقرص:"
    journalctl -k -b --no-pager 2>/dev/null | grep -iE "I/O error|btrfs.*(error|corrupt)" | tail -5 | while read -r line; do
        log_err "  $line"
    done || true
    
    # 3. Coredumps
    log_info "Coredumps:"
    if command -v coredumpctl &>/dev/null; then
        local coredumps
        coredumps=$(coredumpctl list --no-pager 2>/dev/null | wc -l || true)
        coredumps=$(( ${coredumps:-0} + 0 ))
        log_info "يوجد $coredumps سطر في قائمة coredump"
        
        if [[ $coredumps -gt 0 ]]; then
            coredumpctl list --no-pager 2>/dev/null | tail -5 | while read -r line; do
                log_warn "  $line"
            done || true
        fi
    fi
    
    # 4. حجم السجلات
    log_info "حجم السجلات:"
    journalctl --disk-usage 2>/dev/null | while read -r line; do
        log_info "  $line"
    done || true
    
    log_ok "اكتمل تحليل السجلات"
}

log_clean() {
    log_section "تنظيف السجلات"
    
    # 1. حذف coredumps القديمة
    log_info "حذف coredumps القديمة (> 14 يوم)..."
    if command -v coredumpctl &>/dev/null; then
        find /var/lib/systemd/coredump -type f -mtime +14 -delete 2>/dev/null || true
        log_ok "تم الحذف"
    fi
    
    # 2. تدوير السجلات
    log_info "تدوير السجلات..."
    journalctl --rotate 2>/dev/null || true
    journalctl --vacuum-time=7d 2>/dev/null || true
    
    log_ok "تم التنظيف"
    journalctl --disk-usage 2>/dev/null
}
