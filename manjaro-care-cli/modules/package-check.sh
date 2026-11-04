#!/usr/bin/env bash
#
# وحدة فحص الحزم (مُصحّحة: عدّ AUR المعطوبة خارج الـ subshell، حماية ldd والأنابيب)
#

package_check() {
    log_section "فحص الحزم"
    
    local problems=0
    
    # 1. التحقق من قاعدة البيانات
    log_info "التحقق من قاعدة بيانات الحزم..."
    if pacman -Dk &>/dev/null; then
        log_ok "قاعدة البيانات سليمة"
    else
        log_err "خطأ في قاعدة البيانات! (جرّب: sudo pacman -Dk لعرض التفاصيل)"
        problems=$((problems + 1))
    fi
    
    # 2. البحث عن ملفات مفقودة
    log_info "البحث عن ملفات مفقودة..."
    local missing_files
    missing_files=$(pacman -Qk 2>/dev/null | grep -E ", [1-9][0-9]* missing files?" | wc -l || true)
    missing_files=$(( ${missing_files:-0} + 0 ))
    
    if [[ $missing_files -gt 0 ]]; then
        log_warn "تم العثور على $missing_files حزمة بها ملفات مفقودة"
        pacman -Qk 2>/dev/null | grep -E ", [1-9][0-9]* missing files?" | head -5 | while read -r line; do
            log_warn "  $line"
        done
        problems=$((problems + missing_files))
    else
        log_ok "لا توجد ملفات مفقودة"
    fi
    
    # 3. البحث عن حزم يتيمة
    log_info "البحث عن حزم يتيمة..."
    local orphans
    orphans=$(pacman -Qdtq 2>/dev/null | wc -l || true)
    orphans=$(( ${orphans:-0} + 0 ))
    
    if [[ $orphans -gt 0 ]]; then
        log_warn "تم العثور على $orphans حزمة يتيمة (الإزالة: sudo mcare packages clean)"
        pacman -Qdtq 2>/dev/null | head -5 | while read -r pkg; do
            log_warn "  $pkg"
        done
    else
        log_ok "لا توجد حزم يتيمة"
    fi
    
    # 4. التحقق من التحديثات المعلقة
    log_info "التحقق من التحديثات المعلقة..."
    local pending
    pending=$(checkupdates 2>/dev/null | wc -l || true)
    pending=$(( ${pending:-0} + 0 ))
    
    if [[ $pending -gt 0 ]]; then
        log_warn "يوجد $pending تحديث معلق"
    else
        log_ok "النظام محدث"
    fi
    
    # 5. التحقق من ملفات .pacnew/.pacsave
    # (BUG-CLI-03: العدد يطابق القائمة؛ الاقتطاع يُعلن؛ لا دمج تلقائي؛
    #  الملفات الحرجة تُوسم وتُحتسب في problems — التحذير بلا عدّ هو عين العيب الذي نُصلحه)
    log_info "التحقق من ملفات .pacnew/.pacsave..."
    local pacnew_root="${CARE_PACNEW_ROOT:-/etc}"
    local pacnew_list pacnew_count pacnew_crit shown f
    pacnew_list=$(find "$pacnew_root" \( -name "*.pacnew" -o -name "*.pacsave" \) 2>/dev/null | LC_ALL=C sort)
    pacnew_count=$(printf '%s\n' "$pacnew_list" | grep -c . || true)
    pacnew_count=$(( ${pacnew_count:-0} + 0 ))
    if [[ $pacnew_count -gt 0 ]]; then
        log_warn "تم العثور على $pacnew_count ملف .pacnew/.pacsave"
        shown=0
        pacnew_crit=0
        # (مراجعة مستقلة 2026-11-04: العدّ مستقل عن العرض — الملف الحرج رقم 16+
        #  وما بعده يُحسب حتى لو لم يُعرض، والاقتطاع يمس السجل لا العدّ)
        while IFS= read -r f; do
            [[ -n "$f" ]] || continue
            local is_crit=false
            case "$f" in
                */default/grub*|*/mkinitcpio.conf*|*/locale.gen*|*/pacman.conf*|*/fstab*|*/crypttab*|*/vconsole.conf*|*/NetworkManager/*|*/systemd/*|*/plymouth/*)
                    is_crit=true ;;
            esac
            if $is_crit; then
                pacnew_crit=$((pacnew_crit + 1))   # (العدّ مستقل عن العرض)
            fi
            if [[ $shown -lt 15 ]]; then
                if $is_crit; then
                    log_warn "  [حرج] $f — مراجعة يدوية عبر: sudo pacdiff"
                else
                    log_warn "  $f"
                fi
            fi
            shown=$((shown + 1))
        done <<< "$pacnew_list"
        problems=$((problems + pacnew_crit))
        if [[ $pacnew_count -gt 15 ]]; then
            log_warn "  (العرض مقتطع: 15 من $pacnew_count — القائمة الكاملة: find $pacnew_root \\( -name '*.pacnew' -o -name '*.pacsave' \\))"
            if [[ $pacnew_crit -gt 0 ]]; then
                log_warn "  (من ضمنها $pacnew_crit ملف حرج مُحتسب — بعضها قد يكون خارج الـ15 المعروضة)"
            fi
        fi
        log_info "لن يُدمج أو يُستبدل أي ملف تلقائياً — المراجعة اليدوية: sudo pacdiff"
    else
        log_ok "لا توجد ملفات .pacnew/.pacsave"
    fi
    
    # 6. فحص حزم AUR المعطوبة (مكتبات مفقودة في الثنائيات — حالة orthanc)
    # (شفافية فحص AUR: ماذا فُحص، ماذا تُخطي، ماذا وُجد، وهل اكتمل)
    log_info "التحقق من حزم AUR..."
    if ! command -v pacman &>/dev/null; then
        log_warn "تعذر فحص AUR: pacman غير متوفر — فحص غير مكتمل"
        problems=$((problems + 1))
    else
        local broken_aur=0 aur_total=0 aur_no_bin=0 pkg bin_path
        while IFS= read -r pkg; do
            [[ -n "$pkg" ]] || continue
            aur_total=$((aur_total + 1))
            bin_path="$(pacman -Ql "$pkg" 2>/dev/null | awk '$2 ~ /^\/usr\/bin\//{print $2; exit}')"
            if [[ -z "$bin_path" || ! -x "$bin_path" ]]; then
                aur_no_bin=$((aur_no_bin + 1))
                continue
            fi
            if ldd "$bin_path" 2>/dev/null | grep -q "not found"; then
                log_warn "حزمة AUR معطوبة: $pkg (مكتبة مفقودة في $bin_path)"
                broken_aur=$((broken_aur + 1))
            fi
        done < <(pacman -Qmq 2>/dev/null | head -30)
        log_info "ملخص فحص AUR: ${aur_total} حزمة أجنبية في النطاق (أول 30)، ${aur_no_bin} بلا تنفيذي في /usr/bin (تخطي)، ${broken_aur} معطوبة"
        log_info "حالة فحص AUR: اكتمل"
        (( broken_aur > 0 )) && problems=$((problems + broken_aur))
    fi
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "الحزم سليمة"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi
    
    # حارس الاتساق: رمز الخروج في bash محدود 0-255 والقيم فوقه تلتف
    # (256 مشكلة → 0 → «سليم» زائفة) — نسقف قبل الإرجاع
    (( problems > 255 )) && problems=255
    return $problems
}

package_clean() {
    log_section "تنظيف الحزم"
    
    # 1. إزالة الحزم اليتيمة
    log_info "إزالة الحزم اليتيمة..."
    local orphans
    orphans=$(pacman -Qdtq 2>/dev/null)
    
    if [[ -n "$orphans" ]]; then
        local -a orphan_packages=()
        mapfile -t orphan_packages <<< "$orphans"
        log_warn "الحزم المرشحة للإزالة:"
        printf '  %s\n' "${orphan_packages[@]}"
        if [[ ! -t 0 ]]; then
            log_err "لا توجد طرفية تفاعلية؛ لن تُزال أي حزمة."
            return 1
        fi
        local reply=""
        read -r -p "إزالة الحزم المعروضة باستخدام pacman -Rns؟ [y/N] " reply
        if [[ "$reply" =~ ^[Yy]$ ]]; then
            if pacman -Rns -- "${orphan_packages[@]}"; then
                log_ok "تمت إزالة الحزم اليتيمة بعد موافقتك"
            else
                log_err "فشل إزالة بعض الحزم اليتيمة"
                return 1
            fi
        else
            log_info "أُلغي حذف الحزم."
        fi
    else
        log_ok "لا توجد حزم يتيمة"
    fi
    
    # 2. تنظيف ذاكرة التخزين المؤقت
    log_info "تنظيف ذاكرة التخزين المؤقت..."
    if command -v paccache &>/dev/null; then
        paccache -r -k 2
        log_ok "تم تنظيف الذاكرة المؤقتة"
    else
        log_warn "paccache غير مثبت"
    fi
    
    # 3. Preserve pacnew/pacsave files; they may contain administrator changes.
    log_info "فحص ملفات .pacnew/.pacsave دون حذفها..."
    local -a config_candidates=()
    mapfile -t config_candidates < <(find /etc -type f \( -name "*.pacnew" -o -name "*.pacsave" \) -print 2>/dev/null)
    if (( ${#config_candidates[@]} > 0 )); then
        log_warn "تم الاحتفاظ بـ ${#config_candidates[@]} ملف إعدادات للمراجعة اليدوية:"
        printf '  %s\n' "${config_candidates[@]}"
    else
        log_ok "لا توجد ملفات .pacnew/.pacsave"
    fi
    log_ok "اكتمل تنظيف ذاكرة الحزم؛ لم تُحذف ملفات الإعدادات."
}

package_rebuild() {
    log_section "إعادة بناء حزم AUR"
    
    local pkg_list
    pkg_list="$(pacman -Qmq 2>/dev/null || true)"
    if [[ -z "$pkg_list" ]]; then
        log_ok "لا توجد حزم AUR لإعادة البناء"
        return 0
    fi
    
    log_warn "هذا سيعيد بناء جميع حزم AUR (قد يستغرق وقتاً طويلاً)"
    read -p "متابعة؟ (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # shellcheck disable=SC2086
        if command -v paru &>/dev/null; then
            paru -S --rebuild $pkg_list
        elif command -v yay &>/dev/null; then
            yay -S --rebuild $pkg_list
        else
            log_err "لا يوجد مساعد AUR مثبت (paru أو yay)"
            return 1
        fi
    fi
}
