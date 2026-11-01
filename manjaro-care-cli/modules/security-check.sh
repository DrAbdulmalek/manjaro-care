#!/usr/bin/env bash
#
# وحدة فحص الأمان (مُصحّحة: عد الموانف بلا تكرار، فحص LLMNR بلا glob فارغ)
#

security_check() {
    log_section "فحص الأمان"
    
    local problems=0
    
    # 1. التحقق من جدار الحماية
    log_info "التحقق من جدار الحماية..."
    if command -v ufw &>/dev/null; then
        if ufw status | grep -q "Status: active"; then
            log_ok "جدار الحماية نشط"
        else
            log_warn "جدار الحماية معطل"
        fi
    else
        log_warn "ufw غير مثبت"
    fi
    
    # 2. التحقق من SSH
    log_info "التحقق من SSH..."
    if systemctl is-active --quiet sshd 2>/dev/null; then
        log_warn "SSH يعمل (تأكد من أمانه)"
    else
        log_ok "SSH معطل"
    fi
    
    # 3. التحقق من المنافذ المفتوحة
    log_info "التحقق من المنافذ المفتوحة..."
    local open_ports
    open_ports=$(ss -tuln 2>/dev/null | grep -c "LISTEN" || true)
    open_ports=$(( ${open_ports:-0} + 0 ))
    log_info "يوجد $open_ports منفذ مفتوح"
    
    # عرض المنافذ الخارجية
    log_info "المنافذ الخارجية:"
    ss -tuln 2>/dev/null | grep "0.0.0.0\|\[::" | head -10 | while read -r line; do
        log_warn "  $line"
    done || true
    
    # 4. التحقق من Docker
    log_info "التحقق من حاويات Docker..."
    if command -v docker &>/dev/null && docker ps &>/dev/null; then
        local containers
        containers=$(docker ps --format "{{.Names}}: {{.Ports}}" 2>/dev/null | wc -l || true)
        containers=$(( ${containers:-0} + 0 ))
        log_info "يوجد $containers حاوية عاملة"
        
        docker ps --format "{{.Names}}: {{.Ports}}" 2>/dev/null | while read -r line; do
            if echo "$line" | grep -q "0.0.0.0"; then
                log_warn "حاوية مكشوفة: $line"
            fi
        done
    fi
    
    # 5. التحقق من LLMNR (النمط السابق كان يفشل إن كان المجلد فارغاً فتظهر
    #    تحذير كاذبة "مفعّل")
    log_info "التحقق من LLMNR..."
    if grep -rqs "LLMNR=no" /etc/systemd/resolved.conf.d/ 2>/dev/null \
       || grep -qs "LLMNR=no" /etc/systemd/resolved.conf 2>/dev/null; then
        log_ok "LLMNR معطل"
    else
        log_warn "LLMNR مفعّل (مخاطر أمنية) — أضف LLMNR=no في resolved.conf.d"
        problems=$((problems + 1))
    fi
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "الفحص الأمني اكتمل"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi
    
    return $problems
}

security_ports() {
    log_section "عرض المنافذ المفتوحة"
    
    log_info "المنافذ المفتوحة:"
    ss -tulnp 2>/dev/null | head -30
}

security_firewall() {
    log_section "إدارة جدار الحماية"
    
    if ! command -v ufw &>/dev/null; then
        log_err "ufw غير مثبت"
        return 1
    fi
    
    log_info "حالة جدار الحماية:"
    ufw status verbose
    
    echo ""
    read -p "تفعيل جدار الحماية؟ (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ufw enable
        ufw default deny incoming
        ufw default allow outgoing
        log_ok "تم تفعيل جدار الحماية"
    fi
}
