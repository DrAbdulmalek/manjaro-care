#!/usr/bin/env bash
#
# وحدة فحص الإقلاع (مُصحَّحة: عدّاد المشاكل بلا set -e، وحماية الأنابيب)
#

boot_sanity_check() {
    log_section "فحص الإقلاع"
    
    local problems=0
    
    # 1. التحقق من الجذر الحالي
    log_info "التحقق من مصدر الجذر..."
    local root_source
    root_source=$(findmnt -no SOURCE / 2>/dev/null || echo "unknown")
    
    if [[ "$root_source" == *"timeshift-btrfs/snapshots"* ]]; then
        log_err "النظام يعمل من داخل لقطة Timeshift!"
        log_warn "المصدر: $root_source"
        problems=$((problems + 1))
    else
        log_ok "الجذر يعمل من subvolume حقيقي"
    fi
    
    # 2. التحقق من grub.cfg
    log_info "التحقق من grub.cfg..."
    if [[ -f "/boot/grub/grub.cfg" ]]; then
        local main_entry
        main_entry=$(awk '/^menuentry .Manjaro Linux./{flag=1} flag && /linux[[:space:]]+\//{print; exit}' /boot/grub/grub.cfg 2>/dev/null || true)
        
        if [[ "$main_entry" == *"timeshift-btrfs/snapshots"* ]]; then
            log_err "grub.cfg يشير إلى لقطة قديمة"
            problems=$((problems + 1))
        else
            log_ok "grub.cfg يشير إلى المسار الصحيح"
        fi
    fi
    
    # 3. التحقق من rootflags
    log_info "التحقق من rootflags في /etc/default/grub..."
    if grep -q "rootflags=subvol=@" /etc/default/grub 2>/dev/null; then
        log_ok "rootflags=subvol=@ مُفعّل"
    else
        log_warn "rootflags=subvol=@ غير مُفعّل (موصى به)"
    fi
    
    # 4. التحقق من ملفات النواة
    log_info "التحقق من ملفات النواة..."
    local kernel_version
    kernel_version=$(uname -r)
    if [[ -f "/boot/vmlinuz-$kernel_version" ]]; then
        log_ok "ملف النواة موجود: vmlinuz-$kernel_version"
    else
        log_err "ملف النواة مفقود!"
        problems=$((problems + 1))
    fi
    
    # 5. التحقق من grubenv
    log_info "التحقق من grubenv..."
    if [[ -f "/boot/grub/grubenv" ]]; then
        local size
        size=$(stat -c%s /boot/grub/grubenv 2>/dev/null || echo 0)
        if [[ $size -eq 1024 ]]; then
            log_ok "grubenv سليم (1024 بايت)"
        else
            log_warn "grubenv بحجم غير قياسي: $size بايت"
        fi
    else
        log_warn "grubenv غير موجود"
    fi
    
    # 6. التحقق من EFI
    log_info "التحقق من EFI boot entries..."
    if command -v efibootmgr &>/dev/null; then
        local boot_current
        boot_current=$(efibootmgr 2>/dev/null | grep "BootCurrent" | awk '{print $2}' || true)
        if [[ -n "${boot_current:-}" ]]; then
            log_ok "الإقلاع الحالي: Boot$boot_current"
        else
            log_warn "لم يُقرأ BootCurrent من efibootmgr"
        fi
    fi
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "لا توجد مشاكل في الإقلاع"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi
    
    return $problems
}

boot_sanity_fix() {
    log_section "إصلاح مشاكل الإقلاع"
    
    # 1. إصلاح grubenv
    log_info "إصلاح grubenv..."
    if [[ -f "/boot/grub/grubenv" ]]; then
        cp -a /boot/grub/grubenv "$BACKUPS_DIR/grubenv.bak-$TIMESTAMP" \
            || { log_err "فشل النسخ الاحتياطي ل grubenv — إلغاء"; return 1; }
    fi
    if ! rm -f /boot/grub/grubenv; then
        log_err "تعذر حذف grubenv القديم — تحقق من الصلاحيات"
        return 1
    fi
    if ! grub-editenv /boot/grub/grubenv create 2>/dev/null; then
        log_err "فشل إنشاء grubenv — تحقق من صلاحيات root"
        return 1
    fi
    log_ok "تم إنشاء grubenv جديد"
    
    # 2. إضافة rootflags إذا لم يكن موجوداً
    log_info "التحقق من rootflags..."
    if ! grep -q "rootflags=subvol=@" /etc/default/grub; then
        cp -a /etc/default/grub "$BACKUPS_DIR/grub.bak-$TIMESTAMP"
        sed -i "s/GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT=\"quiet splash udev.log_priority=3 rootflags=subvol=@\"/" /etc/default/grub
        log_ok "تم إضافة rootflags=subvol=@"
    fi
    
    # 3. إعادة بناء grub.cfg
    log_info "إعادة بناء grub.cfg..."
    if ! grub-mkconfig -o /boot/grub/grub.cfg; then
        log_err "فشل grub-mkconfig — راجع النسخة الاحتياطية: $BACKUPS_DIR/grub.bak-*"
        return 1
    fi
    log_ok "تم تحديث grub.cfg"
    
    log_ok "اكتمل إصلاح الإقلاع. أعد التشغيل للتطبيق."
}
