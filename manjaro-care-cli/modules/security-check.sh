#!/usr/bin/env bash
#
# وحدة فحص الأمان (مُصحّحة: عد الموانف بلا تكرار، فحص LLMNR بلا glob فارغ)
#

# BUG-CLI-04: تصنيف عنوان الربط المحلي — دالة نقية قابلة للاختبار دون جهاز حقيقي أو root
# المدخل: العنوان المحلي بصيغة ss (مثل 0.0.0.0:7860 أو 127.0.0.53:53 أو [::]:41641 أو 0.0.0.0%virbr0:67)
# المخرج: loopback | virtual | lan | wildcard | other
sec_classify_local() {
    local host="${1%:*}"
    case "$host" in
        127.*|::1|\[::1\])                                      printf 'loopback\n' ;;
        *%virbr*|*%veth*|*%br-*|*%docker*|*%tap*)               printf 'virtual\n' ;;
        0.0.0.0|\*|\[::\])                                      printf 'wildcard\n' ;;
        192.168.*|10.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*|\[fe80*|fe80*) printf 'lan\n' ;;
        # (R7) ULA ضمن fc00::/7 (يشمل fd00::/8) — عناوين محلية وليست إنترنت عامة
        \[fc*|\[fd*|fc*|fd*)                                    printf 'lan\n' ;;
        *)                                                      printf 'other\n' ;;
    esac
}

# (مراجعة مستقلة 2026-11-05 — R5/R5-2) فعالية ruleset لـ nftables — دالة نقية:
# الإدخال: نص nft list ruleset. المخرج: 0 فقط عند دليل حماية *قابل للإثبات* على مسار الإدخال.
#
# الدليل المقبول حصراً:
#   (أ) سلسلة أساس hook input *تظل نهايتها قابلة للبلوغ* وسياسة policy drop/reject، أو
#   (ب) قاعدة *قابلة للوصول* حكمها drop/reject ختامي *غير مشروط* على مسار الإدخال —
#       أي سلاسل hook input الأساس + ما يُوصل إليها بـ jump/goto غير مشروط
#       داخل الجدول نفسه (مسار تطبيق القواعد).
#
# تحليل ترتيب القواعد (R5-2 — القواعد الميتة لا تُعلن حماية):
#   * بعد قاعدة حكمها الختامي غير مشروط في السلسلة نفسها (accept/drop/reject)
#     أو return غير مشروطة أو goto غير مشروطة — كل ما يليها في هذه السلسلة
#     غير قابل للوصول: لا يُفحص ولا يُلاحق هدفه (لا jump/go إلى سلاسل ميتة).
#   * jump غير مشروطة إلى سلسلة *لا يمكنها العودة* (كل مساراتها تنتهي بحكم
#     ختامي غير مشروط) تُميت ما بعدها في السلسلة الاستدعائية — ومن ذلك
#     policy تلك السلسلة (الحزمة لا تصل لنهايتها إطلاقاً).
#   * القفزات المشروطة (مطابقة قبل jump/goto) لا تُلاحق أهدافها: drop خلفها
#     يخص الحزم المطابقة فقط — ليس حماية افتراضية لمسار الإدخال كله.
#   * return غير مشروطة تُميت ما بعدها؛ وفي سلسلة أساس لا تُبنى عليها
#     سياسة (سلوك return في السلسلة الأساس غير محسوم هنا — لا نعلن حماية
#     ولا ننفيها بناءً عليه؛ الحزم التي تتجاوز السلاسل الأخرى قد تحسم لاحقاً).
#   * الحلقات الدورية في jump لا تعلّق التحليل (nft الحقيقي يرفض تحميلها أصلاً).
#
# ما يُحلَّل بأمان — أشكال الأحكام غير المشروطة المقبولة حصراً (من nft list ruleset):
#   [counter [packets N bytes M]] (accept|drop|return)
#   [counter [packets N bytes M]] reject [with icmp|icmpv6|icmpx type NAME | with tcp reset]
#   [counter [packets N bytes M]] [log [prefix "..."] [level L]] <الحكم أعلاه>
#   [counter [packets N bytes M]] (jump|goto) NAME
# وكل ما عدا ذلك — تعبيرات مطابقة (tcp dport / ct state / ip saddr...)، limit،
# مجموعات inline {..} (يُقسّمها تجريد الأقواس لأسطر تُصنف كلٌّ على حدة)،
# vmap، notrack، log بخيارات غير مدعومة — يُصنَّف *مشروطاً/غير محسوم*:
#   لا يُعدّ دليلاً بذاته، ولا يقتل قابلية الوصول لما بعده.
# اتجاه الأمان: الغموض يُفسَّر لصالح عدم الإعلان عن حماية — قاعدة غير محسومة
# لا تُنتج إعلان حماية زائفاً بذاتها، ولا تحجب دليلاً حقيقياً يليها.
sec_nft_effective() {
    local rs="${1:-}"
    # تجريد نصوص comment أولاً كي لا تُعدّ دليلاً، ثم فصل الأقواس أسطراً
    # كي تُقرأ السلاسل المكتوبة في سطر واحد كذلك
    rs=$(printf '%s\n' "$rs" | sed 's/comment "[^"]*"//g; s/#.*//' | sed 's/[{}]/&\n/g')
    local -A CH_BODY=() CH_HOOK=() CH_POLICY=()
    local cur_tbl="" cur="" in_chain=0 line
    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*table[[:space:]]+[^[:space:]]+[[:space:]]+([^[:space:]]+)[[:space:]]*\{ ]]; then
            cur_tbl="${BASH_REMATCH[1]}"
            cur=""
            in_chain=0
            continue
        fi
        if [[ "$line" =~ ^[[:space:]]*chain[[:space:]]+([^[:space:]]+)[[:space:]]*\{ ]]; then
            cur="${cur_tbl}|${BASH_REMATCH[1]}"
            in_chain=1
            CH_BODY[$cur]=""
            continue
        fi
        if (( in_chain )); then
            if [[ "$line" =~ ^[[:space:]]*\}[[:space:]]*$ ]]; then
                cur=""
                in_chain=0
                continue
            fi
            # فصل مقاطع «;»: الترويسة (type ...؛ policy ...) وقواعد الصيغ
            # المكتوبة بسطر واحد (nft -f) — كل مقطع يُعامل قاعدة مستقلة؛
            # مقطع type يُتخطى في المسح وسياسة policy تُكتشف بال regex عادي.
            # ملاحظة موثقة: «;» داخل نص مقتبس (log prefix "a;b") في هذه الصيغة
            # الاصطناعية يُقسّم القاعدة لمقاطع غير محسومة — اتجاه آمن (لا دليل
            # زائف ولا قتل للوصول).
            local rest="$line" seg
            while [[ -n "$rest" ]]; do
                if [[ "$rest" == *";"* ]]; then
                    seg="${rest%%;*}"
                    rest="${rest#*;}"
                else
                    seg="$rest"
                    rest=""
                fi
                seg="${seg#"${seg%%[![:space:]]*}"}"
                seg="${seg%"${seg##*[![:space:]]}"}"
                # في الصيغة أحادية السطر تلتصق «}» الختامية بآخر قاعدة
                # (drop } ← drop)؛ نقتطعها كي تُصنَّف القاعدة أصلاً
                seg="${seg%%\}*}"
                seg="${seg#"${seg%%[![:space:]]*}"}"
                seg="${seg%"${seg##*[![:space:]]}"}"
                [[ -n "$seg" ]] && CH_BODY[$cur]+="$seg"$'\n'
            done
        fi
    done <<< "$rs"
    # تعليم سلاسل الإدخال الأساسية وسياساتها
    local key body
    for key in "${!CH_BODY[@]}"; do
        body="${CH_BODY[$key]}"
        if [[ "$body" == *"hook input"* ]]; then
            CH_HOOK[$key]=1
        fi
        if [[ "$body" =~ policy[[:space:]]+(drop|reject) ]]; then
            CH_POLICY[$key]="${BASH_REMATCH[1]}"
        fi
    done
    # حالة التحليل: مذكرتا «هل تعود السلسلة؟» و«قيد الفحص» لمنع الحلقات
    local -A SEC_CR_MEM=() SEC_CR_INPROG=() SEC_WK_INPROG=()
    for key in "${!CH_HOOK[@]}"; do
        sec_nft_walk_chain "$key"
        # (ب) دليل قاعدة: حكم ختامي غير مشروط قابل للوصول على مسار الإدخال
        if (( SEC_WALK_DROP )); then
            return 0
        fi
        # (أ) سياسة الإسقاط دليل فقط إذا ظل نهاية السلسلة قابلاً للبلوغ —
        # accept/goto/قفزة-لا-تعود قبلها تجعلها قاعدة ميتة لا تُعلن حماية
        if (( SEC_WALK_END )) && [[ "${CH_POLICY[$key]:-}" =~ ^(drop|reject)$ ]]; then
            return 0
        fi
    done
    return 1
}

# ─── مساعدات sec_nft_effective (تُستدعى منها فقط؛ ترى متغيراتها بالتغليف الديناميكي) ───

# تصنيف سطر قاعدة واحدة (بعد تجريد comment/#): يضبط
#   RC_KIND: term | return | jump | goto | cond | empty
#   RC_VERD: drop | reject | accept (لـ term حصراً)
#   RC_TGT : اسم السلسلة الهدف (لـ jump/goto حصراً)
# الأشكال غير المشروطة المقبولة حصراً موثقة أعلاه؛ كل ما عداها = cond.
sec_nft_rule_classify() {
    RC_KIND=cond
    RC_VERD=""
    RC_TGT=""
    local r="$1"
    # تجريد الفراغات الطرفية وفاصلة منقوطة ختامية محتملة
    r="${r#"${r%%[![:space:]]*}"}"
    r="${r%"${r##*[![:space:]]}"}"
    r="${r%";"}"
    [[ -n "$r" ]] || { RC_KIND=empty; return 0; }
    # بادئة counter اختيارية (بإحصاءات العرض أو بدونها)
    local re_counter='^counter([[:space:]]+packets[[:space:]]+[0-9]+[[:space:]]+bytes[[:space:]]+[0-9]+)?[[:space:]]+(.+)$'
    if [[ "$r" =~ $re_counter ]]; then
        r="${BASH_REMATCH[2]}"
    elif [[ "$r" == "counter" ]]; then
        return 0   # عدّاد مجرد: بلا حكم — غير محسوم ولا يقتل الوصول
    fi
    # بادئة log اختيارية (الأشكال الضيقة فقط؛ غير المدعوم يبقى غير محسوم)
    local re_log='^log([[:space:]]+prefix[[:space:]]+"[^"]+")?([[:space:]]+level[[:space:]]+[a-z0-9]+)?[[:space:]]+(.+)$'
    if [[ "$r" =~ $re_log ]]; then
        r="${BASH_REMATCH[3]}"
    elif [[ "$r" == "log" || "$r" =~ ^log[[:space:]] ]]; then
        return 0   # log بلا حكم لاحق معروف — قاعدة تسجيل لا تحسم شيئاً
    fi
    case "$r" in
        accept|drop)
            RC_KIND=term
            RC_VERD="$r" ;;
        return)
            RC_KIND="return" ;;   # عودة صريحة: خاتمة للسلسلة لكنها «تعود» للقافز
        reject)
            RC_KIND=term
            RC_VERD=reject ;;
        reject\ with\ *)
            local re_reject='^reject[[:space:]]+with[[:space:]]+((icmpx?|icmpv6)[[:space:]]+type[[:space:]]+[a-z0-9-]+|tcp[[:space:]]+reset)$'
            if [[ "$r" =~ $re_reject ]]; then
                RC_KIND=term
                RC_VERD=reject
            fi ;;
        jump\ *|goto\ *)
            local t="${r#* }"
            t="${t#"${t%%[![:space:]]*}"}"
            t="${t%"${t##*[![:space:]]}"}"
            if [[ "$t" =~ ^[A-Za-z0-9_.-]+$ ]]; then
                RC_KIND="${r%%[[:space:]]*}"
                RC_TGT="$t"
            fi ;;
    esac
    return 0
}

# هل يمكن للسلسلة أن «تعود» للحزمة التي قفزت إليها (بلوغ نهايتها بلا حكم ختامي)؟
# RC=0 نعم / RC=1 لا. تحليل بترتيب القواعد مع مذكرة وحارس حلقات.
sec_nft_chain_can_return() {
    local key="$1"
    if [[ -n "${SEC_CR_INPROG[$key]+x}" ]]; then
        return 0   # حلقة: نفترض العودة (nft الحقيقي يرفض الحلقات أصلاً)
    fi
    if [[ -n "${SEC_CR_MEM[$key]+x}" ]]; then
        return "${SEC_CR_MEM[$key]}"
    fi
    if [[ -z "${CH_BODY[$key]+x}" ]]; then
        return 0   # هدف غير موجود في الجدول: نفترض العودة (nft يرفض ذلك عند التحميل)
    fi
    SEC_CR_INPROG[$key]=1
    # اصطلاح موحد: res = رمز العودة (0 = يمكن للسلسلة أن تعود، 1 = لا تعود أبداً)
    local body="${CH_BODY[$key]}" rr reachable=1 res=0
    while IFS= read -r rr; do
        [[ "$rr" =~ ^[[:space:]]*type[[:space:]] ]] && continue   # سطر type/hook/policy ليس قاعدة
        [[ -n "${rr//[[:space:]]/}" ]] || continue
        (( reachable )) || break
        sec_nft_rule_classify "$rr"
        case "$RC_KIND" in
            term)
                res=1        # حكم ختامي غير مشروط: لا عودة أبداً (RC=1)
                reachable=0
                ;;
            return)
                res=0        # عودة صريحة: تعود للقافز (وما بعدها ميت)
                reachable=0
                ;;
            jump)
                if sec_nft_chain_can_return "${key%%|*}|$RC_TGT"; then
                    :        # الهدف قد يعود → بقية القواعد ما تزال قابلة للوصول
                else
                    res=1    # الهدف لا يعود أبداً → ما بعد القفزة ميت (RC=1)
                    reachable=0
                fi
                ;;
            goto)
                sec_nft_chain_can_return "${key%%|*}|$RC_TGT"
                res=$?       # مصير السلسلة = مصير هدف goto
                reachable=0  # goto لا يعود إلى هذه السلسلة
                ;;
            *)
                res=0        # قاعدة مشروطة/غير محسومة: حزم تتجاوزها → عودة ممكنة (RC=0)
                ;;
        esac
    done <<< "$body"
    unset "SEC_CR_INPROG[$key]"
    SEC_CR_MEM[$key]=$res
    return "$res"
}

# مسح سلسلة بترتيب قواعدها بحثاً عن دليل (حكم ختامي غير مشروط قابل للوصول).
# يضبط عند العودة: SEC_WALK_DROP=1 عند وجود دليل، SEC_WALK_END=1 إذا ظل
# نهاية السلسلة قابلاً للبلوغ (لحسم قابلية تفعيل policy).
sec_nft_walk_chain() {
    SEC_WALK_DROP=0
    SEC_WALK_END=0
    local key="$1"
    if [[ -n "${SEC_WK_INPROG[$key]+x}" ]]; then
        SEC_WALK_END=1   # حلقة: نُكمل كأن المسار يتابع، بلا دليل من الحلقة ذاتها
        return 0
    fi
    if [[ -z "${CH_BODY[$key]+x}" ]]; then
        return 0         # هدف غير موجود: بلا جسم ولا دليل
    fi
    SEC_WK_INPROG[$key]=1
    local body="${CH_BODY[$key]}" rr reachable=1 sub=0
    while IFS= read -r rr; do
        [[ "$rr" =~ ^[[:space:]]*type[[:space:]] ]] && continue   # سطر type/hook/policy ليس قاعدة
        [[ -n "${rr//[[:space:]]/}" ]] || continue
        (( reachable )) || break   # R5-2: قواعد بعد حكم ختامي/عودة/goto ميتة — لا تُفحص
        sec_nft_rule_classify "$rr"
        case "$RC_KIND" in
            term)
                if [[ "$RC_VERD" == drop || "$RC_VERD" == reject ]]; then
                    SEC_WALK_DROP=1
                fi
                reachable=0   # كل ما بعد الحكم الختامي غير المشروط لا يمكن الوصول إليه
                ;;
            return)
                reachable=0   # عودة صريحة: ما بعدها ميت في هذه السلسلة
                ;;
            jump)
                # حفظ الهدف قبل النداء التراجعي: classify في السلسلة الفرعية
                # يَطمس RC_TGT العام — نداء لاحق بمفتاح فارغ يفترض «تعود» خطأً
                local tgt="${key%%|*}|$RC_TGT"
                sec_nft_walk_chain "$tgt"
                sub=$SEC_WALK_DROP
                (( sub )) && SEC_WALK_DROP=1
                if ! sec_nft_chain_can_return "$tgt"; then
                    reachable=0   # الهدف لا يعود أبداً → ما بعد القفزة ميت (ومنه policy)
                fi
                ;;
            goto)
                local tgt="${key%%|*}|$RC_TGT"
                sec_nft_walk_chain "$tgt"
                sub=$SEC_WALK_DROP
                (( sub )) && SEC_WALK_DROP=1
                reachable=0   # goto لا يعود: ما بعده ميت والسياسة لا تُفعَّل
                ;;
            *)
                :             # مشروطة/غير محسومة: لا دليل ولا قتل للوصول
                ;;
        esac
    done <<< "$body"
    (( reachable )) && SEC_WALK_END=1
    unset "SEC_WK_INPROG[$key]"
    return 0
}

# (مراجعة مستقلة 2026-11-05 — R6) تمييز بروتوكولات الاكتشاف الشبكي — دالة نقية:
# الإعفاء يتطلب تطابق ثلاثي: البروتوكول (udp حصراً) + المنفذ + المالك النظامي المعروف.
# أولاً: البروتوكول — لا يُعفى TCP مطلقاً حتى لو كان المالك avahi/systemd-resolve،
# فالإصلاح السابق كان يعفي TCP بفحص المالك قبل البروتوكول.
# المنفذ وحده لا يكفي: خدمة مجهولة على 5353/1900/67... لا تُعفى ولا تُخفى —
# تسقط في التصنيف العادي فتظهر كتحذير [خارجي] قابل للمراجعة.
# المدخلات: $1=Netid من ss (tcp/udp)، $2=العنوان المحلي، $3=المالك إن توفر.
sec_is_discovery() {
    local netid="$1" owner="${3:-}" port="${2##*:}"
    [[ "$netid" == "udp" ]] || return 1
    case "$owner:$port" in
        avahi-daemon:5353)                          return 0 ;;   # mDNS
        systemd-resolve:5355|systemd-resolved:5355) return 0 ;;   # LLMNR
        dnsmasq:67|dnsmasq:68)                      return 0 ;;   # DHCP
        dhcpd:67|dhclient:68)                       return 0 ;;
        NetworkManager:68|systemd-networkd:68)      return 0 ;;
        minissdpd:1900)                             return 0 ;;   # SSDP
        wsdd:3702)                                  return 0 ;;   # WS-Discovery
    esac
    return 1
}

security_check() {
    log_section "فحص الأمان"
    
    local problems=0
    
    # 1. التحقق من جدار الحماية
    # (BUG-CLI-04: لا نفترض ufw وحده — ufw وfirewalld وقواعد nftables؛
    #  النتيجة تُحتسب في problems، وقواعد فارغة وحدها لا تعني تعرضاً)
    log_info "التحقق من جدار الحماية..."
    local fw_active=false fw_details=""
    if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
        fw_active=true
        fw_details="ufw نشط"
    fi
    if command -v firewall-cmd &>/dev/null && firewall-cmd --state 2>/dev/null | grep -q "running"; then
        fw_active=true
        fw_details="${fw_details:+${fw_details}، }firewalld نشط"
    fi
    if ! $fw_active && command -v nft &>/dev/null; then
        # (R5: الفعالية تُثبت من مسار الإدخال — سلسلة hook input بسياسة إسقاط
        #  أو حكم إفلات ختامي غير مشروط على المسار؛ القواعد المعزولة لا تُعدّ جداراً)
        local nft_rs
        nft_rs=$(nft list ruleset 2>/dev/null)
        if sec_nft_effective "$nft_rs"; then
            fw_active=true
            fw_details="nftables بحماية فعّالة على مسار الإدخال (hook input)"
        elif [[ -n "$(printf '%s' "$nft_rs" | tr -d '[:space:]')" ]]; then
            log_warn "nftables موجود لكن بلا حماية مؤكدة على مسار الإدخال (hook input) — قواعد drop المعزولة لا تُعتبر جداراً"
        fi
    fi
    if $fw_active; then
        log_ok "جدار الحماية نشط (${fw_details})"
    else
        log_warn "لا يوجد جدار حماية فعّال (ufw/firewalld/nftables) — الإصلاح: sudo mcare security firewall"
        problems=$((problems + 1))
    fi
    
    # 2. التحقق من SSH
    log_info "التحقق من SSH..."
    if systemctl is-active --quiet sshd 2>/dev/null; then
        log_warn "SSH يعمل (تأكد من أمانه)"
    else
        log_ok "SSH معطل"
    fi
    
    # 3. التحقق من المنافذ المفتوحة
    # (BUG-CLI-05: التصنيف من عمود العنوان المحلي فقط؛ tcp وudp معاً؛
    #  المالك يُعرض عند توفر الصلاحية؛
    #  مراجعة مستقلة 2026-11-04: الاستماع على كل الواجهات ≠ تعرض خارجي —
    #  بروتوكولات الاكتشاف (mDNS/LLMNR/SSDP/WS-Disc/DHCP) تُميّز ولا تُحسب،
    #  والإعفاء الوحيد بالمالك: tailscaled — سلوكه الطبيعي)
    log_info "التحقق من المنافذ المفتوحة..."
    local ss_out tcp_count udp_count ext_count line laddr owner cls
    ss_out=$(ss -tulnp 2>/dev/null | awk 'NR>1')
    tcp_count=$(printf '%s\n' "$ss_out" | awk '$1 ~ /^tcp/ && $2 == "LISTEN"' | grep -c . || true)
    udp_count=$(printf '%s\n' "$ss_out" | awk '$1 ~ /^udp/' | grep -c . || true)
    tcp_count=$(( ${tcp_count:-0} + 0 ))
    udp_count=$(( ${udp_count:-0} + 0 ))
    log_info "المنافذ المفتوحة: $((tcp_count + udp_count)) (${tcp_count} tcp مستمع + ${udp_count} udp)"

    log_info "المنافذ المنشورة على جميع الواجهات (خارجية فعلاً):"
    ext_count=0
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        laddr=$(printf '%s' "$line" | awk '{print $5}')
        owner=$(printf '%s' "$line" | sed -n 's/^.*users:(("\([^"]*\)".*/\1/p')
        cls=$(sec_classify_local "$laddr")
        if [[ "$cls" == "wildcard" && "$owner" == "tailscaled" ]]; then
            cls="vpn"
        fi
        if [[ "$cls" == "wildcard" ]] && sec_is_discovery "$(printf '%s' "$line" | awk '{print $1}')" "$laddr" "$owner"; then
            cls="discovery"
        fi
        case "$cls" in
            loopback)
                : ;;
            virtual)
                log_info "  [افتراضية] $(printf '%s' "$line" | awk '{print $1}') $laddr (Docker/libvirt)" ;;
            vpn)
                log_info "  [vpn] $(printf '%s' "$line" | awk '{print $1}') $laddr (${owner:-غير معروف})" ;;
            discovery)
                log_info "  [اكتشاف شبكي] $(printf '%s' "$line" | awk '{print $1}') $laddr (${owner:-غير معروف}) — بروتوكول اكتشاف بالتصميم، ليس تعرضاً" ;;
            lan)
                log_info "  [شبكة محلية] $(printf '%s' "$line" | awk '{print $1}') $laddr" ;;
            wildcard)
                ext_count=$((ext_count + 1))
                log_warn "  [خارجي] $(printf '%s' "$line" | awk '{print $1}') $laddr ${owner:+($owner)}" ;;
            *)
                ext_count=$((ext_count + 1))
                log_warn "  [خارجي؟] $(printf '%s' "$line" | awk '{print $1}') $laddr ${owner:+($owner)}" ;;
        esac
    done <<< "$ss_out"
    if [[ $ext_count -gt 0 ]]; then
        log_warn "$ext_count منفذاً منشورة على جميع الواجهات — راجع القائمة أعلاه"
        problems=$((problems + 1))
    else
        log_ok "لا توجد منافذ منشورة على جميع الواجهات"
    fi
    
    # 4. التحقق من Docker
    # (BUG-CLI-06: الحاوية المكشوفة تُحتسب في problems مع إرشاد إصلاح)
    log_info "التحقق من حاويات Docker..."
    if command -v docker &>/dev/null && docker ps &>/dev/null; then
        local containers exposed dline
        containers=$(docker ps --format "{{.Names}}: {{.Ports}}" 2>/dev/null | grep -c . || true)
        containers=$(( ${containers:-0} + 0 ))
        log_info "يوجد $containers حاوية عاملة"
        exposed=0
        while IFS= read -r dline; do
            [[ -n "$dline" ]] || continue
            if printf '%s' "$dline" | grep -Eq "0\.0\.0\.0:[0-9]+->|:::[0-9]+->|\[::\]:[0-9]+->"; then
                log_warn "حاوية مكشوفة: $dline — الإصلاح: أعد نشرها بربط محلي (127.0.0.1) بدل 0.0.0.0/::"
                exposed=$((exposed + 1))
            fi
        done <<< "$(docker ps --format "{{.Names}}: {{.Ports}}" 2>/dev/null)"
        if [[ $exposed -gt 0 ]]; then
            problems=$((problems + exposed))
        fi
    fi
    
    # 5. التحقق من LLMNR (النمط السابق كان يفشل إن كان المجلد فارغاً فتظهر
    #    تحذير كاذبة "مفعّل")
    log_info "التحقق من LLMNR..."
    local resolved_dir="${CARE_RESOLVED_CONF_D:-/etc/systemd/resolved.conf.d/}"
    local resolved_conf="${CARE_RESOLVED_CONF:-/etc/systemd/resolved.conf}"
    if grep -rqs "LLMNR=no" "$resolved_dir" 2>/dev/null \
       || grep -qs "LLMNR=no" "$resolved_conf" 2>/dev/null; then
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
    
    # حارس الاتساق: رمز الخروج في bash محدود 0-255 والقيم فوقه تلتف
    # (256 مشكلة → 0 → «سليم» زائفة) — نسقف قبل الإرجاع
    (( problems > 255 )) && problems=255
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
