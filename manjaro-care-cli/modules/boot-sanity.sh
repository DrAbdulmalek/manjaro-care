#!/usr/bin/env bash
#
# وحدة فحص الإقلاع (مُصحَّحة: عدّاد المشاكل بلا set -e، وحماية الأنابيب)
#

boot_sanity_check() {
    log_section "$MSG_BOOT_TITLE"
    
    local problems=0
    
    # 1. التحقق من الجذر الحالي
    log_info "$MSG_BOOT_ROOT_CHECK"
    local root_source
    root_source=$(findmnt -no SOURCE / 2>/dev/null || echo "unknown")
    
    if [[ "$root_source" == *"timeshift-btrfs/snapshots"* ]]; then
        log_err "$MSG_BOOT_ROOT_SNAPSHOT"
        log_warn "$(printf "$MSG_BOOT_ROOT_SOURCE" "$root_source")"
        problems=$((problems + 1))
    else
        log_ok "$MSG_BOOT_ROOT_REAL"
    fi
    
    # 2. التحقق من grub.cfg
    log_info "$MSG_BOOT_GRUB_CHECK"
    if [[ -f "/boot/grub/grub.cfg" ]]; then
        local main_entry
        main_entry=$(awk '/^menuentry .Manjaro Linux./{flag=1} flag && /linux[[:space:]]+\//{print; exit}' /boot/grub/grub.cfg 2>/dev/null || true)
        
        if [[ "$main_entry" == *"timeshift-btrfs/snapshots"* ]]; then
            log_err "$MSG_BOOT_GRUB_SNAPSHOT"
            problems=$((problems + 1))
        else
            log_ok "$MSG_BOOT_GRUB_REAL"
        fi
    fi
    
    # 3. التحقق من rootflags
    log_info "$MSG_BOOT_ROOTFLAGS_CHECK"
    if grep -q "rootflags=subvol=@" /etc/default/grub 2>/dev/null; then
        log_ok "$MSG_BOOT_ROOTFLAGS_OK"
    else
        log_warn "$MSG_BOOT_ROOTFLAGS_WARN"
    fi
    
    # 4. التحقق من ملفات النواة
    log_info "$MSG_BOOT_KERNEL_CHECK"
    local kernel_version
    kernel_version=$(uname -r)
    if [[ -f "/boot/vmlinuz-$kernel_version" ]]; then
        log_ok "$(printf "$MSG_BOOT_KERNEL_OK" "vmlinuz-$kernel_version")"
    else
        log_err "$MSG_BOOT_KERNEL_ERR"
        problems=$((problems + 1))
    fi
    
    # 5. التحقق من grubenv
    log_info "$MSG_BOOT_GRUBENV_CHECK"
    if [[ -f "/boot/grub/grubenv" ]]; then
        local size
        size=$(stat -c%s /boot/grub/grubenv 2>/dev/null || echo 0)
        if [[ $size -eq 1024 ]]; then
            log_ok "$MSG_BOOT_GRUBENV_OK"
        else
            log_warn "$(printf "$MSG_BOOT_GRUBENV_WARN" "$size")"
        fi
    else
        log_warn "$MSG_BOOT_GRUBENV_MISSING"
    fi
    
    # 6. التحقق من EFI
    log_info "$MSG_BOOT_EFI_CHECK"
    if command -v efibootmgr &>/dev/null; then
        local boot_current
        boot_current=$(efibootmgr 2>/dev/null | grep "BootCurrent" | awk '{print $2}' || true)
        if [[ -n "${boot_current:-}" ]]; then
            log_ok "$(printf "$MSG_BOOT_EFI_OK" "$boot_current")"
        else
            log_warn "$MSG_BOOT_EFI_FAIL"
        fi
    fi
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "$MSG_BOOT_NONE"
    else
        log_err "$(printf "$MSG_BOOT_FOUND" "$problems")"
    fi
    
    return $problems
}

boot_sanity_fix() {
    log_section "$MSG_BOOTFIX_TITLE"
    
    # 1. إصلاح grubenv
    log_info "$MSG_BOOTFIX_GRUBENV"
    if [[ -f "/boot/grub/grubenv" ]]; then
        cp -a /boot/grub/grubenv "$BACKUPS_DIR/grubenv.bak-$TIMESTAMP" \
            || { log_err "$MSG_BOOTFIX_BAK_FAIL"; return 1; }
    fi
    if ! rm -f /boot/grub/grubenv; then
        log_err "$MSG_BOOTFIX_RM_FAIL"
        return 1
    fi
    if ! grub-editenv /boot/grub/grubenv create 2>/dev/null; then
        log_err "$MSG_BOOTFIX_CREATE_FAIL"
        return 1
    fi
    log_ok "$MSG_BOOTFIX_GRUBENV_DONE"
    
    # 2. إضافة rootflags إذا لم يكن موجوداً
    log_info "$MSG_BOOTFIX_ROOTFLAGS_CHECK"
    if ! grep -q "rootflags=subvol=@" /etc/default/grub; then
        cp -a /etc/default/grub "$BACKUPS_DIR/grub.bak-$TIMESTAMP"
        sed -i "s/GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT=\"quiet splash udev.log_priority=3 rootflags=subvol=@\"/" /etc/default/grub
        log_ok "$MSG_BOOTFIX_ROOTFLAGS_DONE"
    fi
    
    # 3. إعادة بناء grub.cfg
    log_info "$MSG_BOOTFIX_GRUBCFG"
    if ! grub-mkconfig -o /boot/grub/grub.cfg; then
        log_err "$(printf "$MSG_BOOTFIX_GRUBCFG_FAIL" "$BACKUPS_DIR/grub.bak-*")"
        return 1
    fi
    log_ok "$MSG_BOOTFIX_GRUBCFG_DONE"
    
    log_ok "$MSG_BOOTFIX_COMPLETE"
}
