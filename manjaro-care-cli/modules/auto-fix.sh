#!/usr/bin/env bash
#
# وحدة الإصلاح التلقائي (مُصحّحة: قراءة --force من أي موضع + MC_FORCE، وحماية التأكيد)
#

auto_fix() {
    log_section "الإصلاح التلقائي"

    local force=false arg
    for arg in "$@"; do
        [[ "$arg" == "--force" || "$arg" == "-f" ]] && force=true
    done
    [[ "${MC_FORCE:-0}" == "1" ]] && force=true

    if [[ "$force" != true ]]; then
        if [[ ! -t 0 ]]; then
            log_err "لا طرفية تفاعلية للتأكيد — مرّر --force صراحة إن أردت الإصلاح"
            return 1
        fi
        log_warn "هذا سيقوم بإصلاح المشاكل المكتشفة تلقائياً (تعديل GRUB، الشبكة، الخدمات)"
        local reply=""
        read -r -p "متابعة؟ (y/N) " reply
        echo
        if [[ ! $reply =~ ^[Yy]$ ]]; then
            log_info "تم الإلغاء"
            return 1
        fi
    fi

    # 1. إصلاح الإقلاع
    log_info "إصلاح مشاكل الإقلاع..."
    load_module "boot-sanity" && boot_sanity_fix || log_warn "تم تخطي إصلاح الإقلاع (فشل أو أُلغي)"

    # 2. إصلاح الشبكة (الواي فاي فقط — إعادة الضبط الكاملة تبقى يدوية عمداً)
    log_info "إصلاح مشاكل الشبكة..."
    load_module "network-reset" && network_wifi_fix || log_warn "تم تخطي إصلاح الشبكة (فشل أو أُلغي)"

    # 3. إصلاح الخدمات
    log_info "إصلاح الخدمات..."
    load_module "service-check" && service_fix || log_warn "تم تخطي إصلاح الخدمات"

    # 4. تنظيف الحزم
    log_info "تنظيف الحزم..."
    load_module "package-check" && package_clean || log_warn "تم تخطي تنظيف الحزم"

    # 5. تنظيف السجلات
    log_info "تنظيف السجلات..."
    load_module "log-analyzer" && log_clean || log_warn "تم تخطي تنظيف السجلات"

    log_ok "اكتمل الإصلاح التلقائي"
    log_info "يُنصح بإعادة التشغيل"
    return 0
}
