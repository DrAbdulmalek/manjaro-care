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
    log_section "$MSG_NET_TITLE"

    local problems=0

    # 1. حالة الأجهزة
    log_info "$MSG_NET_DEVICES"
    nmcli device status 2>/dev/null | grep -E 'wifi|ethernet' | while read -r line; do
        if echo "$line" | grep -q "connected"; then
            log_ok "$line"
        else
            log_warn "$line"
        fi
    done || true

    # 2. التحقق من rfkill
    log_info "$MSG_NET_RADIO_CHECK"
    if rfkill list 2>/dev/null | grep -q "Soft blocked: yes"; then
        log_err "$MSG_NET_RADIO_BLOCKED"
        problems=$((problems + 1))
    else
        log_ok "$MSG_NET_RADIO_OK"
    fi

    # 3. التحقق من NetworkManager
    log_info "$MSG_NET_NM_CHECK"
    if systemctl is-active --quiet NetworkManager; then
        log_ok "$MSG_NET_NM_OK"
    else
        log_err "$MSG_NET_NM_DOWN"
        problems=$((problems + 1))
    fi

    # 4. التحقق من ملفات الواي فاي (psk-flags)
    log_info "$MSG_NET_PROFILES_CHECK"
    local profile psk_flags n_kw=0
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        psk_flags="$(nmcli -g 802-11-wireless-security.psk-flags connection show "$profile" 2>/dev/null || true)"
        case "$psk_flags" in
            1) log_warn "$(printf "$MSG_NET_PROFILE_KWALLET" "$profile")"
               n_kw=$((n_kw + 1)) ;;
            0) log_ok "$(printf "$MSG_NET_PROFILE_OK" "$profile")" ;;
            *) log_info "$(printf "$MSG_NET_PROFILE_OPEN" "$profile" "${psk_flags:-$MSG_EMPTY}")" ;;
        esac
    done < <(wifi_profile_list)
    (( n_kw > 0 )) && { log_warn "$(printf "$MSG_NET_KWALLET_COUNT" "$n_kw")"; problems=$((problems + 1)); }

    # 5. اختبار الاتصال
    log_info "$MSG_NET_PING_CHECK"
    if ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        log_ok "$MSG_NET_PING_OK"
    else
        log_err "$MSG_NET_PING_FAIL"
        problems=$((problems + 1))
    fi

    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "$MSG_NET_ALLGOOD"
    else
        log_err "$(printf "$MSG_NET_FOUND" "$problems")"
    fi

    return "$problems"
}

network_reset() {
    log_section "$MSG_NETRESET_TITLE"
    log_warn "$MSG_NETRESET_WARN"

    # 0) نسخة احتياطية — تفشل العملية كلها إن لم تتم
    log_info "$MSG_NETRESET_BACKUP"
    if [[ -d /etc/NetworkManager/system-connections ]]; then
        cp -a /etc/NetworkManager/system-connections "$BACKUPS_DIR/nm-connections.bak-$TIMESTAMP" \
            || { log_err "$MSG_NETRESET_BACKUP_FAIL"; return 1; }
        log_ok "$(printf "$MSG_NETRESET_BACKUP_OK" "$BACKUPS_DIR/nm-connections.bak-$TIMESTAMP")"
    else
        log_warn "$MSG_NETRESET_NO_NMDIR"
    fi

    # 1) إيقاف الخدمات
    log_info "$MSG_NETRESET_STOP"
    systemctl stop NetworkManager wpa_supplicant 2>/dev/null || true

    # 2) مسح حالات الطيار المتعطلة والذيلات
    log_info "$MSG_NETRESET_CLEAN"
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
    log_info "$MSG_NETRESET_START"
    systemctl start NetworkManager
    sleep 2
    nmcli networking on  2>/dev/null || true
    nmcli radio wifi on  2>/dev/null || true   # ← كانت مفقودة: بدونها لا يتصل الواي فاي بعد إعادة الضبط

    # 5) إعادة تعيين psk-flags للشبكات المحفوظة (كلمة المرور للنظام لا لـ KWallet)
    log_info "$MSG_NETRESET_PSK"
    local profile n_fixed=0
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        nmcli connection modify "$profile" 802-11-wireless-security.psk-flags 0 2>/dev/null \
            && { log_ok "$(printf "$MSG_NETRESET_PSK_DONE" "$profile")"; n_fixed=$((n_fixed + 1)); } || true
    done < <(wifi_profile_list)
    log_info "$(printf "$MSG_NETRESET_COUNT" "$n_fixed")"

    # 6) إعادة المسح
    log_info "$MSG_NETRESET_RESCAN"
    nmcli device wifi rescan 2>/dev/null || true
    sleep 3

    # 7) التحقق
    log_info "$MSG_NETRESET_VERIFY"
    if ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        log_ok "$MSG_NETRESET_DONE"
    else
        log_warn "$MSG_NETRESET_SOFT"
    fi

    log_ok "$MSG_NETRESET_COMPLETE"
    return 0
}

network_wifi_fix() {
    log_section "$MSG_WIFI_TITLE"

    # 1) اكتشاف الملفات الفاشلة فعلاً فقط:
    #    الشبكة المفتوحة (بلا key-mgmt) صالحة ولا تُحذف. الملف الفاشل هو
    #    الذي يفشل استعلامه أساساً من NetworkManager.
    log_info "$MSG_WIFI_SCAN"
    local broken=() profile
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        if ! nmcli -g connection.id connection show "$profile" &>/dev/null; then
            broken+=("$profile")
        fi
    done < <(wifi_profile_list)

    if (( ${#broken[@]} > 0 )); then
        log_warn "$(printf "$MSG_WIFI_BROKEN" "${#broken[@]}" "${broken[*]}")"
        if [[ -t 0 ]]; then
            local reply=""
            read -r -p "$MSG_WIFI_CONFIRM" reply
            if [[ "$reply" =~ ^[Yy]$ ]]; then
                local p
                for p in "${broken[@]}"; do
                    nmcli connection delete "$p" 2>/dev/null || true
                    log_ok "$(printf "$MSG_WIFI_DELETED" "$p")"
                done
            else
                log_info "$MSG_WIFI_SKIPPED"
            fi
        else
            log_info "$MSG_WIFI_NOTTY"
        fi
    else
        log_ok "$MSG_WIFI_CLEAN"
    fi

    # 2) إعادة تعيين psk-flags (الحل الفعلي لمشكلة KWallet عند الإقلاع)
    log_info "$MSG_WIFI_PSK"
    local n=0
    while IFS= read -r profile; do
        [[ -n "$profile" ]] || continue
        nmcli connection modify "$profile" 802-11-wireless-security.psk-flags 0 2>/dev/null \
            && n=$((n + 1)) || true
    done < <(wifi_profile_list)
    log_ok "$(printf "$MSG_WIFI_PSK_DONE" "$n")"

    # 3) إعادة تشغيل NetworkManager وتفعيل الراديو
    systemctl restart NetworkManager
    sleep 2
    nmcli radio wifi on 2>/dev/null || true

    log_ok "$MSG_WIFI_DONE"
    return 0
}
