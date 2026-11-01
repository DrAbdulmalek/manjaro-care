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
    local kernel_version kernel_series kernel_image
    kernel_version=$(uname -r)
    kernel_series="$(printf '%s' "$kernel_version" | cut -d. -f1,2)"
    kernel_image=""
    if [[ -d "/usr/lib/modules/$kernel_version" ]]; then
        kernel_image="$(find /boot -maxdepth 1 -type f -name "vmlinuz-${kernel_series}-*" -print -quit 2>/dev/null || true)"
    fi
    if [[ -n "$kernel_image" ]]; then
        log_ok "$(printf "$MSG_BOOT_KERNEL_OK" "$(basename "$kernel_image")")"
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

    # Do not guess the intended Btrfs subvolume or reset grubenv.
    local fs_type fs_root grub_default grub_cfg backup_dir tmp_cfg
    fs_type="$(findmnt -no FSTYPE / 2>/dev/null || true)"
    fs_root="$(findmnt -no FSROOT / 2>/dev/null || true)"
    grub_default="/etc/default/grub"
    grub_cfg="/boot/grub/grub.cfg"

    if [[ "$fs_type" != "btrfs" || "$fs_root" != "/@" ]]; then
        log_err "رفض الإصلاح الآلي: لم أتحقق من أن الجذر الحالي هو Btrfs subvolume @."
        log_warn "لم يتم تعديل grubenv أو /etc/default/grub أو grub.cfg."
        return 1
    fi
    if [[ ! -f "$grub_default" || ! -f "$grub_cfg" ]]; then
        log_err "ملفات GRUB المطلوبة غير موجودة؛ لا تغيير."
        return 1
    fi
    if grep -Eq '^[[:space:]]*GRUB_CMDLINE_LINUX(_DEFAULT)?=.*rootflags=' "$grub_default"; then
        log_warn "يوجد rootflags مسبقاً؛ لن أستبدله أو أعدّل معاملات النواة."
        log_info "راجع قيمة rootflags يدوياً قبل أي تغيير."
        return 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        log_err "Python 3 مطلوب لإضافة rootflags مع الحفاظ على بقية الإعدادات."
        return 1
    fi

    backup_dir="$BACKUPS_DIR/grub-safe-$TIMESTAMP"
    mkdir -p "$backup_dir" || return 1
    cp -a "$grub_default" "$grub_cfg" "$backup_dir/" || {
        log_err "فشل إنشاء النسخة الاحتياطية؛ لم يتم تعديل GRUB."
        return 1
    }

    if ! python3 - "$grub_default" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
pattern = re.compile(r'^(\s*GRUB_CMDLINE_LINUX_DEFAULT\s*=\s*")([^"\n]*)(".*)$', re.M)
match = pattern.search(text)
if not match:
    raise SystemExit("Could not safely parse GRUB_CMDLINE_LINUX_DEFAULT")
value = match.group(2).strip()
if "rootflags=" in value:
    raise SystemExit("Existing rootflags detected; refusing to overwrite")
replacement = match.group(1) + (value + " " if value else "") + "rootflags=subvol=@" + match.group(3)
path.write_text(text[:match.start()] + replacement + text[match.end():], encoding="utf-8")
PY
    then
        cp -a "$backup_dir/grub" "$grub_default" 2>/dev/null || true
        log_err "تعذر تحديث إعداد GRUB بأمان؛ أُعيدت النسخة الاحتياطية إن أمكن."
        return 1
    fi

    tmp_cfg="$(mktemp /boot/grub/grub.cfg.mcare.XXXXXX)" || {
        cp -a "$backup_dir/grub" "$grub_default"
        return 1
    }
    if ! grub-mkconfig -o "$tmp_cfg" || [[ ! -s "$tmp_cfg" ]] || ! grep -q '^menuentry ' "$tmp_cfg"; then
        rm -f "$tmp_cfg"
        cp -a "$backup_dir/grub" "$grub_default"
        log_err "فشل إنشاء grub.cfg صالح؛ أُعيدت إعدادات GRUB السابقة."
        return 1
    fi
    if ! mv -f "$tmp_cfg" "$grub_cfg"; then
        cp -a "$backup_dir/grub" "$grub_default"
        log_err "تعذر استبدال grub.cfg؛ أُعيدت إعدادات GRUB السابقة."
        return 1
    fi

    log_ok "تمت إضافة rootflags=subvol=@ مع الحفاظ على معاملات النواة الموجودة."
    log_info "نسخة الإعدادات السابقة: $backup_dir"
    log_ok "$MSG_BOOTFIX_COMPLETE"
}
