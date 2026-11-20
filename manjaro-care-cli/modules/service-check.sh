#!/usr/bin/env bash
#
# وحدة فحص الخدمات (مُصحّحة: عدّاد المشاكل، وعدم اعتبار الخدمة غير المثبتة مشكلة)
#

service_check() {
    log_section "فحص الخدمات"
    
    local problems=0
    
    # 1. الخدمات الفاشلة
    # (BUG-CLI-02: أسماء الوحدات تمر عبر المسجل لتصل إلى التقرير وليس الطرفية فقط)
    log_info "البحث عن خدمات فاشلة..."
    local failed_list failed_count row
    failed_list=$(systemctl --failed --no-legend 2>/dev/null | awk 'NF' || true)
    failed_count=$(printf '%s\n' "$failed_list" | grep -c . || true)
    failed_count=$(( ${failed_count:-0} + 0 ))

    if [[ $failed_count -gt 0 ]]; then
        log_err "يوجد $failed_count خدمة فاشلة"
        printf '%s\n' "$failed_list" | head -10 | while IFS= read -r row; do
            log_err "  خدمة فاشلة: $(printf '%s' "$row" | awk '{print $1}') (الحالة: $(printf '%s' "$row" | awk '{print $4}')) — التفاصيل: systemctl status $(printf '%s' "$row" | awk '{print $1}')"
        done
        problems=$((problems + failed_count))
    else
        log_ok "لا توجد خدمات فاشلة"
    fi
    
    # 2. التحقق من الخدمات الأساسية
    log_info "التحقق من الخدمات الأساسية..."
    local essential_services=("NetworkManager" "systemd-resolved" "systemd-logind")
    
    for svc in "${essential_services[@]}"; do
        # الخدمة غير المثبتة ليست مشكلة (systemd-resolved اختيارية على مانجارو)
        if ! systemctl list-unit-files "$svc.service" --no-legend 2>/dev/null | grep -q .; then
            log_info "$svc غير مثبت — تخطي"
        elif systemctl is-active --quiet "$svc" 2>/dev/null; then
            log_ok "$svc يعمل"
        else
            log_err "$svc معطل!"
            problems=$((problems + 1))
        fi
    done
    
    # 3. التحقق من تعارضات إدارة الطاقة
    log_info "التحقق من تعارضات إدارة الطاقة..."
    local tlp_active=false
    local ppd_active=false
    
    if systemctl is-active --quiet tlp 2>/dev/null; then
        tlp_active=true
    fi
    
    if systemctl is-active --quiet power-profiles-daemon 2>/dev/null; then
        ppd_active=true
    fi
    
    if $tlp_active && $ppd_active; then
        log_err "تعارض: TLP و power-profiles-daemon يعملان معاً! (الإصلاح: sudo mcare services fix)"
        problems=$((problems + 1))
    else
        log_ok "لا يوجد تعارض في إدارة الطاقة"
    fi
    
    # 4. التحقق من الخدمات المعلقة
    log_info "التحقق من الخدمات المعلقة..."
    local hanging_jobs
    hanging_jobs=$(systemctl list-jobs --no-legend 2>/dev/null | wc -l || true)
    hanging_jobs=$(( ${hanging_jobs:-0} + 0 ))
    
    if [[ $hanging_jobs -gt 0 ]]; then
        log_warn "يوجد $hanging_jobs مهمة معلقة"
        systemctl list-jobs --no-pager 2>/dev/null | head -5 || true
    else
        log_ok "لا توجد مهام معلقة"
    fi
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "الخدمات سليمة"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi
    
    # حارس الاتساق: رمز الخروج في bash محدود 0-255 والقيم فوقه تلتف
    # (256 مشكلة → 0 → «سليم» زائفة) — نسقف قبل الإرجاع
    (( problems > 255 )) && problems=255
    return $problems
}

service_fix() {
    log_section "إصلاح الخدمات"
    
    # 1. إعادة تعيين الخدمات الفاشلة
    log_info "إعادة تعيين الخدمات الفاشلة..."
    systemctl --failed --no-legend 2>/dev/null | awk '{print $1}' | while read -r svc; do
        log_info "إعادة تعيين: $svc"
        systemctl reset-failed "$svc" 2>/dev/null || true
    done
    
    # 2. حل تعارض إدارة الطاقة
    log_info "التحقق من تعارض إدارة الطاقة..."
    if systemctl is-active --quiet tlp && systemctl is-active --quiet power-profiles-daemon; then
        log_warn "إيقاف power-profiles-daemon (TLP نشط)..."
        if systemctl mask --now power-profiles-daemon; then
            log_ok "تم حل التعارض"
        else
            log_err "تعذر إيقاف power-profiles-daemon — أوقفه يدوياً"
        fi
    fi
    
    # 3. إعادة تحميل systemd
    log_info "إعادة تحميل systemd..."
    systemctl daemon-reload
    
    log_ok "اكتمل إصلاح الخدمات"
}
