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
    
    # 5. التحقق من ملفات .pacnew
    log_info "التحقق من ملفات .pacnew/.pacsave..."
    local pacnew_count
    pacnew_count=$(find /etc -name "*.pacnew" -o -name "*.pacsave" 2>/dev/null | wc -l)
    
    if [[ $pacnew_count -gt 0 ]]; then
        log_warn "تم العثور على $pacnew_count ملف .pacnew/.pacsave"
        find /etc -name "*.pacnew" -o -name "*.pacsave" 2>/dev/null | head -5 | while read -r f; do
            log_warn "  $f"
        done
    else
        log_ok "لا توجد ملفات .pacnew/.pacsave"
    fi
    
    # 6. التحقق من حزم AUR المعطوبة (مكتبات مفقودة في الثنائيات — حالة orthanc)
    log_info "التحقق من حزم AUR (قد يستغرق دقيقة)..."
    local broken_aur=0 pkg bin_path
    while IFS= read -r pkg; do
        [[ -n "$pkg" ]] || continue
        bin_path="$(pacman -Ql "$pkg" 2>/dev/null | awk '$2 ~ /^\/usr\/bin\//{print $2; exit}')"
        [[ -n "$bin_path" && -x "$bin_path" ]] || continue
        if ldd "$bin_path" 2>/dev/null | grep -q "not found"; then
            log_warn "حزمة AUR معطوبة: $pkg (مكتبة مفقودة في $bin_path)"
            broken_aur=$((broken_aur + 1))
        fi
    done < <(pacman -Qmq 2>/dev/null | head -30)
    (( broken_aur > 0 )) && problems=$((problems + broken_aur))
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "الحزم سليمة"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi
    
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
        printf '  %s\\n' "${orphan_packages[@]}"
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
    mapfile -t config_candidates < <(find /etc -type f \\( -name "*.pacnew" -o -name "*.pacsave" \\) -print 2>/dev/null)
    if (( ${#config_candidates[@]} > 0 )); then
        log_warn "تم الاحتفاظ بـ ${#config_candidates[@]} ملف إعدادات للمراجعة اليدوية:"
        printf '  %s\\n' "${config_candidates[@]}"
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
