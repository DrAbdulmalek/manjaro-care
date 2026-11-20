#!/usr/bin/env bash
#
# وحدة فحص Btrfs وTimeshift
# (مُصحّحة: grep -c || echo 0 كان يطبع عدداً مزدوجاً ويكسر المقارنة
#  الرقمية؛ وحذف اللقطات صار بوسم تاريخي موثوق وتأكيد)
#

# BUG-CLI-01: تصنيف حالة scrub — دالة نقية قابلة للاختبار دون جهاز حقيقي أو root
# المدخل: مخرجات btrfs scrub status (قد تكون فارغة)
# المخرج: running | finished | interrupted | aborted | unknown
btrfs_classify_scrub() {
    local out="$1" st
    st=$(printf '%s' "$out" | sed -n 's/^[[:space:]]*[Ss]tatus:[[:space:]]*//p' | head -n1 | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
    case "$st" in
        running)     printf 'running\n' ;;
        finished)    printf 'finished\n' ;;
        interrupted) printf 'interrupted\n' ;;
        aborted)     printf 'aborted\n' ;;
        *)           printf 'unknown\n' ;;
    esac
}

btrfs_check() {
    log_section "فحص Btrfs وTimeshift"
    
    local problems=0
    
    # 1. التحقق من نظام الملفات
    log_info "التحقق من نظام الملفات Btrfs..."
    if findmnt -no FSTYPE / | grep -q "btrfs"; then
        log_ok "الجذر يستخدم Btrfs"
    else
        log_warn "الجذر لا يستخدم Btrfs"
    fi
    
    # 2. التحقق من صحة Btrfs
    log_info "التحقق من صحة Btrfs..."
    if btrfs filesystem usage / &>/dev/null; then
        log_ok "Btrfs سليم"
        local usage
        usage=$(btrfs filesystem usage / 2>/dev/null | grep "Used:" | awk '{print $2}')
        log_info "الاستخدام: $usage"
    else
        log_err "خطأ في Btrfs!"
        problems=$((problems + 1))
    fi
    
    # 3. التحقق من أخطاء الجهاز
    log_info "التحقق من أخطاء الجهاز..."
    local errors
    errors=$(btrfs device stats / 2>/dev/null | grep -v "0$" | wc -l || true)
    errors=$(( ${errors:-0} + 0 ))
    
    if [[ $errors -gt 0 ]]; then
        log_err "يوجد $errors أخطاء في الجهاز"
        btrfs device stats / 2>/dev/null | grep -v "0$" || true
        problems=$((problems + errors))
    else
        log_ok "لا توجد أخطاء في الجهاز"
    fi
    
    # 4. التحقق من Timeshift
    log_info "التحقق من Timeshift..."
    if command -v timeshift &>/dev/null; then
        local snapshots
        # تنبيه: grep -c يطبع «0» مع حالة خروج 1 عند لا تطابق، و\"|| echo 0\"
        # كانت تضيف صفراً ثانياً فتصبح القيمة "0\n0" وتكسر [[ -gt ]]
        snapshots=$(timeshift --list 2>/dev/null | grep -c "^[0-9]" || true)
        log_ok "يوجد $snapshots لقطة Timeshift"
        
        if [[ $snapshots -gt 10 ]]; then
            log_warn "عدد كبير من اللقطات (قد يستهلك مساحة)"
        fi
    else
        log_warn "Timeshift غير مثبت"
    fi
    
    # 5. التحقق من حالة scrub
    # (BUG-CLI-01: الحالة تُصنَّف وتُحتسب في الحكم؛ المجهول = فحص غير مكتمل وليس PASS)
    if findmnt -no FSTYPE / | grep -q "btrfs"; then
        log_info "التحقق من حالة scrub..."
        local scrub_raw scrub_state scrub_started scrub_errs
        scrub_raw=$(btrfs scrub status / 2>/dev/null || true)
        scrub_state=$(btrfs_classify_scrub "$scrub_raw")
        case "$scrub_state" in
            running)
                log_info "scrub قيد التشغيل الآن — راجع التقدم: sudo btrfs scrub status /"
                ;;
            finished)
                scrub_started=$(printf '%s' "$scrub_raw" | grep -m1 "Scrub started" | cut -d: -f2- | xargs || true)
                scrub_errs=$(printf '%s' "$scrub_raw" | grep -m1 "Error summary" | cut -d: -f2- | xargs || true)
                if printf '%s' "$scrub_errs" | grep -qi "no errors"; then
                    log_ok "آخر scrub اكتمل بلا أخطاء (بدأ: ${scrub_started:-غير معروف})"
                else
                    log_warn "آخر scrub اكتمل مع أخطاء: ${scrub_errs:-غير معروف} (بدأ: ${scrub_started:-غير معروف})"
                    problems=$((problems + 1))
                fi
                ;;
            interrupted)
                log_warn "scrub متقطع منذ آخر تشغيل — استئناف يدوي: sudo btrfs scrub resume /"
                problems=$((problems + 1))
                ;;
            aborted)
                log_err "توقف scrub قسراً (aborted) — راجع سجل النواة ثم أعد التشغيل: sudo btrfs scrub start -B /"
                problems=$((problems + 1))
                ;;
            *)
                log_warn "تعذر تحديد حالة scrub — فحص غير مكتمل (قد يتطلب صلاحيات root)"
                problems=$((problems + 1))
                ;;
        esac
    else
        log_info "الجذر ليس btrfs — فحص scrub غير منطبق"
    fi
    
    echo ""
    if [[ $problems -eq 0 ]]; then
        log_ok "Btrfs وTimeshift سليمان"
    else
        log_err "تم اكتشاف $problems مشكلة"
    fi
    
    # حارس الاتساق: رمز الخروج في bash محدود 0-255 والقيم فوقه تلتف
    # (256 مشكلة → 0 → «سليم» زائفة) — نسقف قبل الإرجاع
    (( problems > 255 )) && problems=255
    return $problems
}

btrfs_scrub() {
    log_section "تشغيل Btrfs scrub"
    
    log_info "بدء scrub..."
    if ! btrfs scrub start / 2>/dev/null; then
        log_err "فشل بدء scrub (يتطلب root وأنظام ملفات btrfs)"
        return 1
    fi
    
    sleep 2
    btrfs scrub status /
    
    # تمكين المؤقت الشهري
    log_info "تمكين المؤقت الشهري..."
    systemctl enable --now btrfs-scrub@-.timer 2>/dev/null || true
    
    log_ok "تم بدء scrub"
}

btrfs_snapshots() {
    log_section "إدارة لقطات Timeshift"
    
    if ! command -v timeshift &>/dev/null; then
        log_err "Timeshift غير مثبت"
        return 1
    fi
    
    log_info "اللقطات الحالية:"
    timeshift --list 2>/dev/null | grep "^[0-9]" | head -20
    
    local count
    count=$(timeshift --list 2>/dev/null | grep -c "^[0-9]" || true)
    log_info "إجمالي اللقطات: $count"
    
    if [[ ${count:-0} -gt 10 ]]; then
        log_warn "يوجد $count لقطة. هل تريد حذف اللقطات القديمة؟"
        read -r -p "احتفظ بآخر (عدد) لقطة: " keep
        
        if [[ $keep =~ ^[0-9]+$ ]]; then
            # استخراج وسوم اللقطات (صيغة التاريخ الرسمية لـ timeshift) بدل الاعتماد
            # على رقم عمود هش في جدول العرض. القائمة الأحدث أولاً: ما بعد
            # keep+1 هو الأقدم.
            local old_tags
            old_tags=$(timeshift --list 2>/dev/null | grep "^[0-9]" \
                | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}' \
                | tail -n +$((keep + 1)) || true)
            if [[ -z "$old_tags" ]]; then
                log_ok "لا لقطات قديمة للحذف"
            else
                log_warn "سيُحذف:"
                printf '  %s\n' $old_tags
                local reply=""
                read -r -p "تأكيد الحذف النهائي؟ (y/N): " reply
                if [[ $reply =~ ^[Yy]$ ]]; then
                    local tag
                    while IFS= read -r tag; do
                        [[ -n "$tag" ]] || continue
                        log_info "حذف: $tag"
                        timeshift --delete --snapshot "$tag" 2>/dev/null || log_warn "تعذر حذف: $tag"
                    done <<< "$old_tags"
                else
                    log_info "تم الإلغاء — لم يُحذف شيء"
                fi
            fi
        fi
    fi
}
