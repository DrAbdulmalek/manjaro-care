#!/usr/bin/env bash
#
# وحدة إعادة ضبط الشبكة (مُصحَّحة v1.1.0)
#
# أخطاء صُحّحت هنا:
#  1) ((problems++)) بقيمة 0 يُرجع حالة 1 — كان يقتل السكربت مع set -e.
#  2) `nmcli device status | grep ...` بلا نتائج wifi كان يكسر pipefail.
#  3) network_wifi_fix كان يحذف شبكات مفتوحة (open) مشروعة: قيمة
#     key-mgmt الفارغة تعني شبكة بلا تشفير وليست ملفاً تالفاً.
#     الآن لا يُحذف شيء إلا بتأكيد صريح ولملفات فاشلة فعلاً.
#  4) /var/lib/dhcp مسار دبيان؛ على مانجارو الذيلات في /var/lib/dhcpcd.
#  5) network_reset لم يكن يُعيد تشغيل الراديو (nmcli radio wifi on) —
#     بدونها "إعادة المسح" لا تفعل شيئاً إذا كان الواي فاي معطلاً برمجياً.
#  6) أسماء ملفات الواي فاي المحتوية على ":" كانت تُقرأ خاطئة في الوضع terse.

# قائمة ملفات الواي فاي مع فك تهريب «\:» وحدّ اللاحقة الصحيح
wifi_profile_list() {
    nmcli -t -f NAME,TYPE connection show 2>/dev/null \
        | grep -E ':802-11-wireless$' \
        | sed -E 's/:802-11-wireless$//; s/\\:/:/g' || true
}

network_check() {
    log_section "فحص الشبكة"

    local problems=0

    # 1. حالة الأجهزة
    log_info "حالة أجهزة الشبكة:"
    nmcli device status 2>/dev/null | grep -E 'wifi|ethernet' | while read -r line; do
        if echo "$line" | grep -q "connected"; then
            log_ok "$line"
        else
            log_warn "$line"
        fi
    done || true

    # 2. التحقق من rfkill
    log_info "التحقق من حظر الراديو..."
    if rfkill list 2>/dev/null | grep -q "Soft blocked: yes"; then
        log_err "الراديو محجوب برمجياً! (الحل: sudo mcare network reset)"
        problems=$((problems + 1))
    else
        log_ok "لا يوجد حظر للراديو"
    fi

    # 3. التحقق من NetworkManager
    log_info "التحقق من NetworkManager..."
    if systemctl is-active --quiet NetworkManager; then
        log_ok "NetworkManager يعمل"
    else
        log_err "NetworkManager معطل!"
        problems=$((problems + 1))
    fi

    # 4. التحقق من ملفات الواي فاي (psk-flags)
    log_info "التحقق من ملفات الواي فاي..."
    local profile psk_flags n_kw=0
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        psk_flags="$(nmcli -g 802-11-wireless-security.psk-flags connection show "$profile" 2>/dev/null || true)"
        case "$psk_flags" in
            1) log_warn "الملف '$profile': كلمة المرور في KWallet (psk-flags=1) → قد يفشل الاتصال التلقائي عند الإقلاع"
               n_kw=$((n_kw + 1)) ;;
            0) log_ok "الملف '$profile': كلمة المرور مخزنة للنظام (psk-flags=0)" ;;
            *) log_info "الملف '$profile': شبكة مفتوحة أو بلا إعدادات تخزين خاصة (psk-flags=${psk_flags:-فارغ})" ;;
        esac
    done < <(wifi_profile_list)
    (( n_kw > 0 )) && { log_warn "يوجد $n_kw ملفاً يعتمد KWallet — الإصلاح: sudo mcare network wifi"; problems=$((problems + 1)); }

    # 5. اختبار الاتصال
    log_info "اختبار الاتصال بالإنترنت..."
    if ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        log_ok "الاتصال بالإنترنت يعمل"
    else
        log_err "لا يوجد اتصال بالإنترنت"
        problems=$((problems + 1))
    fi

    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "الشبكة تعمل بشكل طبيعي"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi

    return "$problems"
}

network_reset() {
    log_section "إعادة ضبط الشبكة"
    log_warn "تنبيه: سيُقطع الاتصال لثوانٍ أثناء إعادة التشغيل — لا تشغّل هذا عبر SSH."

    # 0) نسخة احتياطية — تفشل العملية كلها إن لم تتم
    log_info "إنشاء نسخة احتياطية من ملفات الاتصال..."
    if [[ -d /etc/NetworkManager/system-connections ]]; then
        cp -a /etc/NetworkManager/system-connections "$BACKUPS_DIR/nm-connections.bak-$TIMESTAMP" \
            || { log_err "فشل النسخ الاحتياطي — إلغاء إعادة الضبط"; return 1; }
        log_ok "النسخة: $BACKUPS_DIR/nm-connections.bak-$TIMESTAMP"
    else
        log_warn "لا يوجد مجلد /etc/NetworkManager/system-connections — تخطي النسخ"
    fi

    # 1) إيقاف الخدمات
    log_info "إيقاف خدمات الشبكة..."
    systemctl stop NetworkManager wpa_supplicant 2>/dev/null || true

    # 2) مسح حالات الطيار المتعطلة والذيلات
    log_info "مسح حالة NetworkManager وذيلات DHCP..."
    rm -f /var/lib/NetworkManager/NetworkManager.state
    # على مانجارو: dhcpcd يخزن في /var/lib/dhcpcd (وليس /var/lib/dhcp كما في دبيان)
    if [[ -d /var/lib/dhcpcd ]]; then
        rm -f /var/lib/dhcpcd/*.lease 2>/dev/null || true
    fi
    if [[ -d /var/lib/dhcp ]]; then
        rm -f /var/lib/dhcp/*.lease 2>/dev/null || true
    fi

    # 3) إعادة تعيين psk-flags قبل التشغيل (nmcli يحتاج NM حياً — سنفعلها بعد التشغيل)

    # 4) إعادة تشغيل الخدمات وتشغيل الشبكة والراديو صراحةً
    log_info "إعادة تشغيل خدمات الشبكة..."
    systemctl start NetworkManager
    sleep 2
    nmcli networking on  2>/dev/null || true
    nmcli radio wifi on  2>/dev/null || true   # ← كانت مفقودة: بدونها لا يتصل الواي فاي بعد إعادة الضبط

    # 5) إعادة تعيين psk-flags للشبكات المحفوظة (كلمة المرور للنظام لا لـ KWallet)
    log_info "إعادة تعيين psk-flags للشبكات المحفوظة..."
    local profile n_fixed=0
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        nmcli connection modify "$profile" 802-11-wireless-security.psk-flags 0 2>/dev/null \
            && { log_ok "تم تحديث: $profile"; n_fixed=$((n_fixed + 1)); } || true
    done < <(wifi_profile_list)
    log_info "عدد الملفات المحدّثة: $n_fixed"

    # 6) إعادة المسح
    log_info "إعادة مسح شبكات الواي فاي..."
    nmcli device wifi rescan 2>/dev/null || true
    sleep 3

    # 7) التحقق
    log_info "التحقق من الاتصال..."
    if ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        log_ok "تم إعادة ضبط الشبكة بنجاح"
    else
        log_warn "الشبكة مُعاد ضبطها، لكن الاتصال قد يحتاج وقتاً (أو اختر الشبكة يدوياً)"
    fi

    log_ok "اكتملت إعادة الضبط"
    return 0
}

network_wifi_fix() {
    log_section "إصلاح مشاكل الواي فاي"

    # 1) اكتشاف الملفات الفاشلة فعلاً فقط:
    #    الشبكة المفتوحة (بلا key-mgmt) صالحة ولا تُحذف. الملف الفاشل هو
    #    الذي يفشل استعلامه أساساً من NetworkManager.
    log_info "البحث عن ملفات واي فاي غير صالحة..."
    local broken=() profile
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        if ! nmcli -g connection.id connection show "$profile" &>/dev/null; then
            broken+=("$profile")
        fi
    done < <(wifi_profile_list)

    if (( ${#broken[@]} > 0 )); then
        log_warn "ملفات غير صالحة (${#broken[@]}): ${broken[*]}"
        if [[ -t 0 ]]; then
            local reply=""
            read -r -p "حذف هذه الملفات؟ لن تُحذف الشبكات المفتوحة السليمة (y/N): " reply
            if [[ "$reply" =~ ^[Yy]$ ]]; then
                local p
                for p in "${broken[@]}"; do
                    nmcli connection delete "$p" 2>/dev/null || true
                    log_ok "حُذف: $p"
                done
            else
                log_info "تم تخطي الحذف"
            fi
        else
            log_info "لا طرفية تفاعلية — لن يُحذف شيء. أعد التشغيل تفاعلياً للتأكيد."
        fi
    else
        log_ok "لا توجد ملفات غير صالحة"
    fi

    # 2) إعادة تعيين psk-flags (الحل الفعلي لمشكلة KWallet عند الإقلاع)
    log_info "تعيين psk-flags=0 لجميع الشبكات (تخزين في النظام لا KWallet)..."
    local n=0
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        nmcli connection modify "$profile" 802-11-wireless-security.psk-flags 0 2>/dev/null \
            && n=$((n + 1)) || true
    done < <(wifi_profile_list)
    log_ok "تم تحديث $n ملفاً"

    # 3) إعادة تشغيل NetworkManager وتفعيل الراديو
    systemctl restart NetworkManager
    sleep 2
    nmcli radio wifi on 2>/dev/null || true

    log_ok "تم إصلاح الواي فاي"
    return 0
}
