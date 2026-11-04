#!/usr/bin/env bash
#
# اختبارات صحة التشخيص — BUG-CLI-01..06 + حارس الحكم الإجمالي + دورات المراجعة R1–R7
#
# المبدأ (قرار 2026-11-04): لا يجوز أن يعلن أي قسم «سليم» بينما فيه
# مشكلات أمنية أو تشغيلية محسوبة. كل سيناريو هنا يحقن حالة معروفة
# ويتحقق أن (أ) المشكلة تُذكر بالاسم عبر المسجل، و(ب) رمز الخروج
# للقسم غير صفري، و(ج) القسم لا يعلن «سليم».
#
# القيود: لا تعتمد على جهاز حقيقي ولا صلاحيات root — أوامر النظام
# (systemctl/pacman/ss/btrfs/findmnt/docker/ufw/ldd) تُستبدل بشِعام
# PATH، والعينات مأخوذة من سجلات فحص حقيقية 2026-11-02 و2026-11-04.
#
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "$HERE/.." && pwd)"

PASS=0
FAIL=0

# سجلات بديلة تطبع نص الوسم حتى يمكن التحقق من المحتوى
log_section() { printf 'SECTION %s\n' "$*"; }
log_info()    { printf '[INFO] %s\n' "$1"; }
log_ok()      { printf '[OK] %s\n' "$1"; }
log_warn()    { printf '[WARN] %s\n' "$1"; }
log_err()     { printf '[ERR] %s\n' "$1"; }

SHIM_DIR="$(mktemp -d)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$SHIM_DIR" "$TMP_DIR"' EXIT

shim() { # shim <name> (يقرأ جسم السكربت من stdin)
    local name="$1"
    cat > "$SHIM_DIR/$name"
    chmod +x "$SHIM_DIR/$name"
}

assert_contains() { # <haystack> <needle> <label>
    if printf '%s' "$1" | grep -qF -- "$2"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1)); echo "FAIL: $3 — لم يُعثر على: $2"
    fi
}
assert_not_contains() { # <haystack> <needle> <label>
    if printf '%s' "$1" | grep -qF -- "$2"; then
        FAIL=$((FAIL + 1)); echo "FAIL: $3 — وُجد ما لا يجب: $2"
    else
        PASS=$((PASS + 1))
    fi
}
assert_rc_nonzero() {
    if [[ "$1" != 0 ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "FAIL: $2 — RC=0 (أعلن سليماً خطأً)"; fi
}
assert_rc_zero() {
    if [[ "$1" == 0 ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "FAIL: $2 — RC=$1"; fi
}
assert_eq() { # <a> <b> <label>
    if [[ "$1" == "$2" ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "FAIL: $3 — '$1' != '$2'"; fi
}

case_run() { # case_run <module_file> <function>  (يستخدم env المُصدَّر من الحالة)
    local mod="$1" fn="$2"
    RUN_OUT="$(export PATH="$SHIM_DIR:$PATH"; source "$CLI_ROOT/modules/$mod"; "$fn" 2>/dev/null; printf '__RC__%s' "$?")"
    RUN_RC="${RUN_OUT##*__RC__}"
    RUN_OUT="${RUN_OUT%__RC__*}"
}

# ─────────────────────────────────────────────────────────────
# عينات حقيقية من سجل الفحص الميداني (2026-11-02 / 2026-11-04)
# ─────────────────────────────────────────────────────────────

# مخرجات ss -tulnp كما رُصدت على الجهاز (مع إضافة عمود users كما يطبعها ss -p)
cat > "$TMP_DIR/ss-dirty.txt" <<'EOF'
Netid State  Recv-Q Send-Q Local Address:Port       Peer Address:Port        Process
udp   UNCONN 0      0                                0.0.0.0:5353       0.0.0.0:*           users:(("avahi-daemon",pid=700,fd=12))
udp   UNCONN 0      0                                127.0.0.54:53      0.0.0.0:*           users:(("systemd-resolve",pid=701,fd=13))
udp   UNCONN 0      0                                192.168.122.1:53   0.0.0.0:*           users:(("dnsmasq",pid=702,fd=5))
udp   UNCONN 0      0                                0.0.0.0%virbr0:67  0.0.0.0:*           users:(("dnsmasq",pid=702,fd=6))
udp   UNCONN 0      0                                [::]:41641         [::]:*              users:(("tailscaled",pid=703,fd=15))
udp   UNCONN 0      0                                0.0.0.0:9999       0.0.0.0:*           users:(("myapp",pid=705,fd=18))
tcp   LISTEN 0      8192                             127.0.0.53%lo:53   0.0.0.0:*           users:(("systemd-resolve",pid=701,fd=17))
EOF

# منافذ نظيفة: loopback وافتراضية فقط
cat > "$TMP_DIR/ss-clean.txt" <<'EOF'
Netid State  Recv-Q Send-Q Local Address:Port       Peer Address:Port        Process
udp   UNCONN 0      0                                127.0.0.54:53      0.0.0.0:*           users:(("systemd-resolve",pid=701,fd=13))
tcp   LISTEN 0      8192                             127.0.0.53%lo:53   0.0.0.0:*           users:(("systemd-resolve",pid=701,fd=17))
udp   UNCONN 0      0                                0.0.0.0%virbr0:67  0.0.0.0:*           users:(("dnsmasq",pid=702,fd=6))
EOF

# pacman -Qk: العينات الثلاث الحقيقية من سجل 11-02/11-04
cat > "$TMP_DIR/qk.txt" <<'EOF'
fluent-icon-theme-git 1.0.r96.abc123: 96113 total files, 88 missing files
tela-icon-theme 20240612: 688068 total files, 3720 missing files
zsh-completions 1.0.0: 189 total files, 1 missing file
EOF

# ملفات pacnew الحقيقية من السجل (6 ملفات: العدد المعروض كان 5)
mkdir -p "$TMP_DIR/pacnew/default" "$TMP_DIR/pacnew/tpm" "$TMP_DIR/pacnew/plymouth"
touch "$TMP_DIR/pacnew/default/grub.pacnew" \
      "$TMP_DIR/pacnew/tpm/P_ECCP384SHA384.json.pacnew" \
      "$TMP_DIR/pacnew/tpm/P_RSA3072SHA384.json.pacnew" \
      "$TMP_DIR/pacnew/plymouth/plymouthd.conf.pacnew" \
      "$TMP_DIR/pacnew/locale.gen.pacnew" \
      "$TMP_DIR/pacnew/hosts.pacsave"

printf 'LLMNR=no\n' > "$TMP_DIR/resolved.conf"
mkdir -p "$TMP_DIR/resolved.d"

# ─────────────────────────────────────────────────────────────
# الشِعام (مصطنعة، حتمية)
# ─────────────────────────────────────────────────────────────

shim findmnt <<'EOF'
#!/usr/bin/env bash
echo "btrfs"
EOF

shim btrfs <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "filesystem usage") echo "Used: 1.00GiB"; exit 0 ;;
  "device stats")     echo "/dev/sda2 write_io_errs 0"; echo "/dev/sda2 read_io_errs 0"; exit 0 ;;
  "scrub status")     printf 'UUID: test-uuid\nScrub started: Sun 02 Nov 2026 03:00:00 AM +03\nStatus: %s\nDuration: 123s\nError summary: %s\n' "${SCRUB_STATE:-}" "${SCRUB_ERRS:-no errors found}"; exit 0 ;;
  *) exit 0 ;;
esac
EOF

shim systemctl <<'EOF'
#!/usr/bin/env bash
case "$1" in
  --failed)        printf '%s\n' "${FAILED_UNITS:-}"; exit 0 ;;
  list-unit-files) echo "$2 installed"; exit 0 ;;
  is-active)       if [[ "$3" == "power-profiles-daemon" ]]; then exit 1; else exit 0; fi ;;
  list-jobs)       exit 0 ;;
  *)               exit 0 ;;
esac
EOF

shim pacman <<'EOF'
#!/usr/bin/env bash
case "$1" in
  -Dk)   exit 0 ;;
  -Qk)   cat "${PACMAN_QK_FILE:-/dev/null}" ;;
  -Qdtq) exit 0 ;;
  -Qmq)  cat "${PACMAN_QMQ_FILE:-/dev/null}" ;;
  -Ql)   if [[ "$2" == "aur-broken" ]]; then echo "aur-broken /usr/bin/env"; fi ;;
  *)     exit 0 ;;
esac
EOF

shim ldd <<'EOF'
#!/usr/bin/env bash
printf '\tlibmissing.so => not found\n'
EOF

shim ss <<'EOF'
#!/usr/bin/env bash
cat "${SS_FILE:-/dev/null}"
EOF

shim docker <<'EOF'
#!/usr/bin/env bash
case "$1" in
  ps) [[ -n "${DOCKER_PS:-}" ]] && printf '%s\n' "$DOCKER_PS"; exit 0 ;;
  *)  exit 0 ;;
esac
EOF

shim nft <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "list ruleset") cat "${NFT_FILE:-/dev/null}" ;;
  *) exit 0 ;;
esac
EOF

shim ufw <<'EOF'
#!/usr/bin/env bash
case "$1" in
  status) printf 'Status: %s\n' "${UFW_STATE:-inactive}" ;;
  *)      exit 0 ;;
esac
EOF

# ─────────────────────────────────────────────────────────────
# A) BUG-CLI-01 — مصنف حالة scrub (دالة نقية)
# ─────────────────────────────────────────────────────────────
source "$CLI_ROOT/modules/btrfs-check.sh"
source "$CLI_ROOT/modules/security-check.sh"

assert_eq "$(btrfs_classify_scrub 'Status: interrupted')" "interrupted" "scrub=interrupted"
assert_eq "$(btrfs_classify_scrub 'Status: running')"     "running"     "scrub=running"
assert_eq "$(btrfs_classify_scrub 'Status: finished')"    "finished"    "scrub=finished"
assert_eq "$(btrfs_classify_scrub 'Status: aborted')"     "aborted"     "scrub=aborted"
assert_eq "$(btrfs_classify_scrub '')"                    "unknown"     "scrub=empty→unknown"

# B) BUG-CLI-05 — مصنف عنوان الربط المحلي (عينات حقيقية من السجل)
assert_eq "$(sec_classify_local '0.0.0.0:5353')"                    "wildcard" "addr 0.0.0.0 → wildcard"
assert_eq "$(sec_classify_local '127.0.0.54:53')"                   "loopback" "addr 127.x → loopback"
assert_eq "$(sec_classify_local '127.0.0.53%lo:53')"                "loopback" "addr 127.x%lo → loopback"
assert_eq "$(sec_classify_local '192.168.122.1:53')"                "lan"      "addr 192.168 → lan"
assert_eq "$(sec_classify_local '0.0.0.0%virbr0:67')"               "virtual"  "addr %virbr0 → virtual"
assert_eq "$(sec_classify_local '[::]:41641')"                      "wildcard" "addr [::] → wildcard"
assert_eq "$(sec_classify_local '[fe80::99df:9ddf:cdf1:a22e%wlo1]:546')" "lan" "addr fe80 → lan"

# B2) مراجعة مستقلة — فعالية nftables (دالة نقية)
assert_eq "$(sec_nft_effective 'table inet f { chain input { type filter hook input priority 0; policy drop; } }'; echo $?)" "0" "nft: policy drop → فعّال"
assert_eq "$(sec_nft_effective 'table inet t { chain c { type filter hook input priority 0; policy accept; } }'; echo $?)" "1" "nft: policy accept فقط → غير فعّال"
assert_eq "$(sec_nft_effective 'table ip nat { chain p { type nat hook postrouting priority 100; masquerade } }'; echo $?)" "1" "nft: NAT فقط → غير فعّال"
assert_eq "$(sec_nft_effective 'counter ip saddr 1.2.3.4 drop'; echo $?)" "1" "R5: قاعدة drop معزولة بلا سلسلة hook input → غير فعّال (كان يُعلن حماية زائفة)"
assert_eq "$(sec_nft_effective 'chain x { counter } # drop here'; echo $?)" "1" "nft: كلمة drop بعد # لا تُعدّ دليلاً"

# B3) مراجعة مستقلة — تمييز بروتوكولات الاكتشاف (دالة نقية)
assert_eq "$(sec_is_discovery udp '0.0.0.0:5353' 'avahi-daemon'; echo $?)" "0" "disc: avahi mDNS → اكتشاف"
assert_eq "$(sec_is_discovery udp '0.0.0.0:5355' ''; echo $?)" "1" "R6: LLMNR 5355 بلا مالك معروف → لا إعفاء (كان يُعفى بالمنفذ وحده)"
assert_eq "$(sec_is_discovery udp '0.0.0.0:1900' ''; echo $?)" "1" "R6: SSDP 1900 بلا مالك معروف → لا إعفاء (كان يُعفى بالمنفذ وحده)"
assert_eq "$(sec_is_discovery udp '0.0.0.0:9999' 'myapp'; echo $?)" "1" "disc: منفذ مجهول → ليس اكتشافاً"
assert_eq "$(sec_is_discovery tcp '0.0.0.0:9999' ''; echo $?)" "1" "disc: tcp لا يدخل الاكتشاف بالمنفذ"


# C) BUG-CLI-01 — سيناريو scrub متقطع: يُحسب ولا يعلن سليماً
export SCRUB_STATE="interrupted"
case_run btrfs-check.sh btrfs_check
assert_rc_nonzero "$RUN_RC" "btrfs interrupted → RC≠0"
assert_contains "$RUN_OUT" "متقطع" "btrfs interrupted → ذكر الانقطاع"
assert_contains "$RUN_OUT" "btrfs scrub resume /" "btrfs interrupted → أشار للاستئناف اليدوي"
assert_not_contains "$RUN_OUT" "Btrfs وTimeshift سليمان" "btrfs interrupted → لا يعلن سليماً"
unset SCRUB_STATE

# D) BUG-CLI-01 — حالة مجهولة = فحص غير مكتمل (ليس PASS)
case_run btrfs-check.sh btrfs_check
assert_rc_nonzero "$RUN_RC" "btrfs unknown → RC≠0"
assert_contains "$RUN_OUT" "غير مكتمل" "btrfs unknown → فحص غير مكتمل"

# E) BUG-CLI-01 — سيناريو نظيف (finished بلا أخطاء) يبقى سليماً
export SCRUB_STATE="finished"
case_run btrfs-check.sh btrfs_check
assert_rc_zero "$RUN_RC" "btrfs finished-clean → RC=0"
assert_contains "$RUN_OUT" "Btrfs وTimeshift سليمان" "btrfs finished-clean → سليم"
unset SCRUB_STATE

# F) BUG-CLI-02 — الخدمة الفاشلة تُذكر بالاسم عبر المسجل
export FAILED_UNITS="cups.service loaded failed failed Scheduler"
case_run service-check.sh service_check
assert_rc_nonzero "$RUN_RC" "service failed → RC≠0"
assert_contains "$RUN_OUT" "خدمة فاشلة: cups.service" "service failed → الاسم عبر المسجل"
assert_contains "$RUN_OUT" "systemctl status cups.service" "service failed → أمر التفاصيل"
unset FAILED_UNITS

# G) BUG-CLI-02 — لا خدمات فاشلة → سليم
case_run service-check.sh service_check
assert_rc_zero "$RUN_RC" "service clean → RC=0"

# H) BUG-CLI-03 — الحزم: عداد مطابق للقائمة + وسوم حرجة مُحتسبة + ملخص AUR
export CARE_PACNEW_ROOT="$TMP_DIR/pacnew"
export PACMAN_QK_FILE="$TMP_DIR/qk.txt"
export PACMAN_QMQ_FILE="$TMP_DIR/aur.txt"
printf 'aur-broken\naur-nobin\n' > "$TMP_DIR/aur.txt"
case_run package-check.sh package_check
assert_rc_nonzero "$RUN_RC" "packages dirty → RC≠0"
assert_contains "$RUN_OUT" "6 ملف .pacnew/.pacsave" "pacnew → العدد 6"
assert_contains "$RUN_OUT" "grub.pacnew" "pacnew → grub مذكور"
assert_contains "$RUN_OUT" "[حرج]" "pacnew → وسم الملفات الحرجة"
assert_contains "$RUN_OUT" "pacdiff" "pacnew → إحالة لمراجعة يدوية"
assert_contains "$RUN_OUT" "hosts.pacsave" "pacnew → القائمة كاملة (لا اقتطاع صامت)"
assert_contains "$RUN_OUT" "88 missing files" "missing-files → عينة حقيقية معروضة"
assert_contains "$RUN_OUT" "ملخص فحص AUR" "AUR → ملخص قابل للتدقيق"
assert_contains "$RUN_OUT" "حزمة AUR معطوبة: aur-broken" "AUR → المكتبة المفقودة بالاسم"
unset CARE_PACNEW_ROOT PACMAN_QK_FILE PACMAN_QMQ_FILE

# I) BUG-CLI-04/05/06 — الأمان: تصنيف المنافذ + احتساب الجدار والحاوية
export SS_FILE="$TMP_DIR/ss-dirty.txt"
export DOCKER_PS="telegram-tools: 0.0.0.0:7860->7860/tcp"
case_run security-check.sh security_check
assert_rc_nonzero "$RUN_RC" "security dirty → RC≠0"
assert_not_contains "$RUN_OUT" "127.0.0.54" "security → loopback ليس خارجياً"
assert_not_contains "$RUN_OUT" "127.0.0.53%lo" "security → loopback%lo ليس خارجياً"
assert_contains "$RUN_OUT" "[افتراضية]" "security → virbr0 مصنّف افتراضية"
assert_contains "$RUN_OUT" "[vpn]" "security → tailscaled مصنّف vpn"
assert_contains "$RUN_OUT" "[اكتشاف شبكي] udp 0.0.0.0:5353" "security → avahi 5353 اكتشاف شبكي لا إنذار (مراجعة مستقلة)"
assert_contains "$RUN_OUT" "[خارجي] udp 0.0.0.0:9999" "security → خدمة مجهولة 9999 على 0.0.0.0 = تعرض فعلي"
assert_contains "$RUN_OUT" "حاوية مكشوفة: telegram-tools" "security → الحاوية المكشوفة بالاسم"
assert_contains "$RUN_OUT" "لا يوجد جدار حماية فعّال" "security → الجدار المعطل يُرصد"
assert_contains "$RUN_OUT" "تم اكتشاف" "security → الحكم الإجمالي يعكس المشاكل"
assert_not_contains "$RUN_OUT" "الفحص الأمني اكتمل" "security → لا يعلن سليماً"

# J) BUG-CLI-04/05/06 — سيناريو نظيف يبقى سليماً (حارس عكسي)
export SS_FILE="$TMP_DIR/ss-clean.txt"
export DOCKER_PS=""
export UFW_STATE="active"
export CARE_RESOLVED_CONF="$TMP_DIR/resolved.conf"
export CARE_RESOLVED_CONF_D="$TMP_DIR/resolved.d"
case_run security-check.sh security_check
assert_rc_zero "$RUN_RC" "security clean → RC=0"
assert_contains "$RUN_OUT" "الفحص الأمني اكتمل" "security clean → سليم"
assert_contains "$RUN_OUT" "جدار الحماية نشط" "security clean → الجدار النشط يُرصد"
unset SS_FILE DOCKER_PS UFW_STATE CARE_RESOLVED_CONF CARE_RESOLVED_CONF_D

# K) BUG-CLI-03 — ملف حرج وحيد يكمنه لمنع «سليم» (الوسم بلا عدّ = عين العيب)
mkdir -p "$TMP_DIR/pacnew-k"
touch "$TMP_DIR/pacnew-k/fstab.pacnew"
export CARE_PACNEW_ROOT="$TMP_DIR/pacnew-k"
case_run package-check.sh package_check
assert_rc_nonzero "$RUN_RC" "pacnew critical-only → RC≠0"
assert_contains "$RUN_OUT" "[حرج]" "pacnew critical-only → وسم حرج"
assert_contains "$RUN_OUT" "تم اكتشاف 1 مشكلة" "pacnew critical-only → العدّ يعكس الملف الحرج"
assert_not_contains "$RUN_OUT" "الحزم سليمة" "pacnew critical-only → لا يعلن سليماً"
unset CARE_PACNEW_ROOT

# L) BUG-CLI-03 — الاقتطاع فوق 15 ملفاً يُعلن ولا يصمت
mkdir -p "$TMP_DIR/pacnew-l"
for i in $(seq -w 1 16); do touch "$TMP_DIR/pacnew-l/app$i.conf.pacnew"; done
export CARE_PACNEW_ROOT="$TMP_DIR/pacnew-l"
case_run package-check.sh package_check
assert_contains "$RUN_OUT" "16 ملف .pacnew/.pacsave" "pacnew truncation → العدد الكامل 16"
assert_contains "$RUN_OUT" "العرض مقتطع: 15 من 16" "pacnew truncation → الإعلان موجود"
assert_rc_zero "$RUN_RC" "pacnew truncation → غير الحرجة لا تُحسب (تصميم مُوثّق)"
unset CARE_PACNEW_ROOT

# M) حارس السقف — 256 مشكلة: RC=255 (لا يلتف إلى 0) والعرض يبقى بالعدد الحقيقي
export FAILED_UNITS="$(for i in $(seq 1 256); do printf 'unit%03d.service loaded failed failed Test\n' "$i"; done)"
case_run service-check.sh service_check
assert_eq "$RUN_RC" "255" "cap-255 → RC=255 لا 0 (لا التفاف)"
assert_contains "$RUN_OUT" "256 خدمة فاشلة" "cap-255 → العرض يذكر العدد الحقيقي 256"
unset FAILED_UNITS

# N) حالات scrub الحدّية — aborted / running / finished-with-errors / حروف كبيرة
export SCRUB_STATE="aborted"
case_run btrfs-check.sh btrfs_check
assert_rc_nonzero "$RUN_RC" "scrub aborted → RC≠0"
assert_contains "$RUN_OUT" "توقف scrub قسراً" "scrub aborted → يُرصد بالاسم"
unset SCRUB_STATE
export SCRUB_STATE="running"
case_run btrfs-check.sh btrfs_check
assert_rc_zero "$RUN_RC" "scrub running → RC=0 (تشغيل ليس عطباً)"
assert_contains "$RUN_OUT" "قيد التشغيل الآن" "scrub running → إبلاغ بالحالة"
unset SCRUB_STATE
export SCRUB_STATE="finished" SCRUB_ERRS="uncorrectable: 2"
case_run btrfs-check.sh btrfs_check
assert_rc_nonzero "$RUN_RC" "scrub finished-with-errors → RC≠0"
assert_contains "$RUN_OUT" "اكتمل مع أخطاء" "scrub finished-with-errors → الأخطاء تُذكر"
unset SCRUB_STATE SCRUB_ERRS
assert_eq "$(btrfs_classify_scrub 'Status: FINISHED')" "finished" "scrub: FINISHED بحروف كبيرة → finished"

# O) مراجعة مستقلة — ملف حرج في الموقع 16 يُحسب رغم عدم عرضه
mkdir -p "$TMP_DIR/pacnew-o"
for i in $(seq -w 1 15); do touch "$TMP_DIR/pacnew-o/aaa$i.conf.pacnew"; done
touch "$TMP_DIR/pacnew-o/fstab.pacnew"
export CARE_PACNEW_ROOT="$TMP_DIR/pacnew-o"
case_run package-check.sh package_check
assert_rc_nonzero "$RUN_RC" "critical-at-16 → RC≠0"
assert_contains "$RUN_OUT" "16 ملف .pacnew/.pacsave" "critical-at-16 → العدد الكامل 16"
assert_contains "$RUN_OUT" "من ضمنها 1 ملف حرج مُحتسب" "critical-at-16 → إعلان العدّ خارج العرض"
unset CARE_PACNEW_ROOT

# P) مراجعة مستقلة — nftables: بلا سياسة إسقاط = ليس جداراً؛ بسياسة drop = فعّال
export NFT_FILE="$TMP_DIR/nft-accept.txt"
printf 'table inet filter {\n\tchain input { type filter hook input priority 0; policy accept; }\n}\n' > "$TMP_DIR/nft-accept.txt"
export SS_FILE="$TMP_DIR/ss-clean.txt" DOCKER_PS=""
case_run security-check.sh security_check
assert_contains "$RUN_OUT" "بلا حماية مؤكدة على مسار الإدخال" "nft accept-only → يُرصد كغير فعّال (R5)"
assert_rc_nonzero "$RUN_RC" "nft accept-only → RC≠0 (ليس جداراً)"
printf 'table inet filter {\n\tchain input { type filter hook input priority 0; policy drop; }\n}\n' > "$TMP_DIR/nft-accept.txt"
export UFW_STATE="inactive" CARE_RESOLVED_CONF="$TMP_DIR/resolved.conf" CARE_RESOLVED_CONF_D="$TMP_DIR/resolved.d"
case_run security-check.sh security_check
assert_contains "$RUN_OUT" "nftables بحماية فعّالة على مسار الإدخال" "nft policy drop → جدار فعّال (R5)"
assert_rc_zero "$RUN_RC" "nft policy drop → سيناريو نظيف يبقى سليماً"
unset NFT_FILE SS_FILE DOCKER_PS UFW_STATE CARE_RESOLVED_CONF CARE_RESOLVED_CONF_D

# R) مراجعة مستقلة — Docker نشر IPv6 بصيغة :::port يُحسب مكشوفاً
export SS_FILE="$TMP_DIR/ss-clean.txt" DOCKER_PS="mybox: :::8080->80/tcp"
case_run security-check.sh security_check
assert_contains "$RUN_OUT" "حاوية مكشوفة: mybox" "docker :::8080 → يُحسب مكشوفاً"
assert_rc_nonzero "$RUN_RC" "docker :::8080 → RC≠0"
unset SS_FILE DOCKER_PS

# S) R5 — قواعد drop معزولة (سلاسل output/docker) لا تُعلن حماية (السيناريو المضاد للإعلان الزائف)
printf 'table inet filter {\n\tchain input { type filter hook input priority 0; policy accept; }\n\tchain output { type filter hook output priority 0; policy drop; }\n}\ntable ip nat {\n\tchain docker-fw { counter ip daddr 172.17.0.0/16 drop }\n}\n' > "$TMP_DIR/nft-r5-isolated.txt"
export NFT_FILE="$TMP_DIR/nft-r5-isolated.txt"
export SS_FILE="$TMP_DIR/ss-clean.txt" DOCKER_PS=""
export UFW_STATE="inactive" CARE_RESOLVED_CONF="$TMP_DIR/resolved.conf" CARE_RESOLVED_CONF_D="$TMP_DIR/resolved.d"
case_run security-check.sh security_check
assert_contains "$RUN_OUT" "بلا حماية مؤكدة على مسار الإدخال" "R5: drop معزول في output/docker → لا يُعلن جداراً"
assert_not_contains "$RUN_OUT" "nftables بحماية فعّالة" "R5: لا إعلان حماية من قواعد معزولة"
assert_rc_nonzero "$RUN_RC" "R5: drop معزول → RC≠0"
unset NFT_FILE SS_FILE DOCKER_PS UFW_STATE CARE_RESOLVED_CONF CARE_RESOLVED_CONF_D

# T) R5 — وحدات مسار الإدخال: الدليل المقبول حصراً (hook input أو قفزة غير مشروطة منه)
cat > "$TMP_DIR/nft-fwld.txt" <<'EOF'
table inet firewalld {
        chain filter_INPUT {
                type filter hook input priority filter; policy accept;
                ct status dnat accept
                jump filter_INPUT_ZONES
                reject with icmpx type admin-prohibited
        }
}
EOF
assert_eq "$(sec_nft_effective "$(< "$TMP_DIR/nft-fwld.txt")"; echo $?)" "0" "R5: نمط firewalld — حكم رفض ختامي في سلسلة input الأساس → فعّال"

cat > "$TMP_DIR/nft-fwd.txt" <<'EOF'
table inet fwd {
        chain forward { type filter hook forward priority 0; policy drop; }
}
EOF
assert_eq "$(sec_nft_effective "$(< "$TMP_DIR/nft-fwd.txt")"; echo $?)" "1" "R5: policy drop على forward حصراً → غير فعّال (لا يخص الإدخال)"

cat > "$TMP_DIR/nft-jump-ok.txt" <<'EOF'
table inet m {
        chain input {
                type filter hook input priority 0; policy accept;
                jump inp_rules
        }
        chain inp_rules {
                tcp dport 22 accept
                drop
        }
}
EOF
assert_eq "$(sec_nft_effective "$(< "$TMP_DIR/nft-jump-ok.txt")"; echo $?)" "0" "R5: قفزة غير مشروطة إلى سلسلة تنتهي بـ drop → فعّال (مسار تطبيق القواعد)"

cat > "$TMP_DIR/nft-jump-cond.txt" <<'EOF'
table inet m2 {
        chain input {
                type filter hook input priority 0; policy accept;
                ip saddr 203.0.113.0/24 jump blocklist
        }
        chain blocklist {
                drop
        }
}
EOF
assert_eq "$(sec_nft_effective "$(< "$TMP_DIR/nft-jump-cond.txt")"; echo $?)" "1" "R5: drop خلف قفزة مشروطة → ليس حماية افتراضية (لا إعلان زائف)"

cat > "$TMP_DIR/nft-out-only.txt" <<'EOF'
table inet u {
        chain output {
                type filter hook output priority 0; policy accept;
                jump out_rules
        }
        chain out_rules {
                drop
        }
}
EOF
assert_eq "$(sec_nft_effective "$(< "$TMP_DIR/nft-out-only.txt")"; echo $?)" "1" "R5: مسار الإخراج وحده بلا سلسلة input → غير فعّال"

cat > "$TMP_DIR/nft-cycle.txt" <<'EOF'
table inet c {
        chain input {
                type filter hook input priority 0; policy accept;
                jump a
        }
        chain a { jump b }
        chain b { jump a }
}
EOF
assert_eq "$(sec_nft_effective "$(< "$TMP_DIR/nft-cycle.txt")"; echo $?)" "1" "R5: حلقة قفزات لا تُعلّق ولا تُعلن حماية"

# U) R6 — وحدات: الإعفاء ثلاثي (udp + منفذ + مالك معروف)؛ غير المؤكد يبقى تحذيراً قابلاً للمراجعة
assert_eq "$(sec_is_discovery tcp '0.0.0.0:5353' 'avahi-daemon'; echo $?)" "1" "R6: TCP مع مالك كان يُعفى → لا إعفاء (البروتوكول أولاً)"
assert_eq "$(sec_is_discovery tcp '127.0.0.1:5355' 'systemd-resolve'; echo $?)" "1" "R6: TCP systemd-resolve → لا إعفاء"
assert_eq "$(sec_is_discovery udp '0.0.0.0:5355' 'systemd-resolve'; echo $?)" "0" "R6: LLMNR 5355 بالمالك الصحيح → اكتشاف"
assert_eq "$(sec_is_discovery udp '0.0.0.0:5353' 'myapp'; echo $?)" "1" "R6: مالك مجهول على منفذ mDNS → لا يُخفى"
assert_eq "$(sec_is_discovery udp '0.0.0.0:5353' ''; echo $?)" "1" "R6: بلا معلومة مالك على 5353 → مراجعة لا إعفاء"
assert_eq "$(sec_is_discovery udp '0.0.0.0:1900' 'minissdpd'; echo $?)" "0" "R6: SSDP بالمالك النظامي → اكتشاف"
assert_eq "$(sec_is_discovery udp '0.0.0.0:3702' 'wsdd'; echo $?)" "0" "R6: WS-Discovery بالمالك النظامي → اكتشاف"
assert_eq "$(sec_is_discovery udp '0.0.0.0:3702' 'myapp'; echo $?)" "1" "R6: 3702 بمالك مجهول → لا يُخفى"
assert_eq "$(sec_is_discovery udp '0.0.0.0:68' 'NetworkManager'; echo $?)" "0" "R6: DHCP client بالمالك النظامي → اكتشاف"
assert_eq "$(sec_is_discovery udp '0.0.0.0:67' 'dnsmasq'; echo $?)" "0" "R6: DHCP server بالمالك النظامي → اكتشاف"
assert_eq "$(sec_is_discovery udp '0.0.0.0:67' 'rogue-dhcpd'; echo $?)" "1" "R6: DHCP بمالك غريب → لا يُخفى"
assert_eq "$(sec_is_discovery udp '0.0.0.0:5354' 'avahi-daemon'; echo $?)" "1" "R6: المالك الصحيح على منفذ خاطئ → لا إعفاء"

# V) R7 — ULA fc00::/7 (fd00::/8): محلية لا خارجية؛ والعناوين العالمية تبقى خارجية (regression)
assert_eq "$(sec_classify_local '[fd00::1]:8080')" "lan" "R7: ULA fd00::/8 → محلية"
assert_eq "$(sec_classify_local '[fc00::1]:53')" "lan" "R7: ULA fc00::/7 → محلية"
assert_eq "$(sec_classify_local '[fd00::1%eth0]:8080')" "lan" "R7: ULA مع %zone → محلية"
assert_eq "$(sec_classify_local '[2001:db8::1]:443')" "other" "R7: عالمية 2001:db8 → ليست محلية (regression)"
assert_eq "$(sec_classify_local '[2606:4700:4700::1111]:443')" "other" "R7: عالمية 2606 → ليست محلية (regression)"

# V2) R6+R7 — نهاية-إلى-نهاية: الخدمة المجهولة على منفذ اكتشاف تظهر [خارجي]، وULA لا تُعلن خارجية
cat > "$TMP_DIR/ss-r7.txt" <<'EOF'
Netid State  Recv-Q Send-Q Local Address:Port       Peer Address:Port        Process
udp   UNCONN 0      0                                0.0.0.0:5353       0.0.0.0:*           users:(("myapp",pid=801,fd=10))
udp   UNCONN 0      0                                0.0.0.0:1900       0.0.0.0:*           users:(("mysteryd",pid=802,fd=11))
tcp   LISTEN 0      128                              [fd00::1]:8080     [::]:*              users:(("myapp",pid=803,fd=12))
tcp   LISTEN 0      128                              [2001:db8::1]:443  [::]:*              users:(("myapp",pid=804,fd=13))
EOF
printf 'table inet filter {\n\tchain input { type filter hook input priority 0; policy drop; }\n}\n' > "$TMP_DIR/nft-r7.txt"
export NFT_FILE="$TMP_DIR/nft-r7.txt" SS_FILE="$TMP_DIR/ss-r7.txt" DOCKER_PS=""
export UFW_STATE="inactive" CARE_RESOLVED_CONF="$TMP_DIR/resolved.conf" CARE_RESOLVED_CONF_D="$TMP_DIR/resolved.d"
case_run security-check.sh security_check
assert_contains "$RUN_OUT" "[خارجي] udp 0.0.0.0:5353" "R6: خدمة مجهولة على 5353 تظهر [خارجي] (لا تُخفى)"
assert_contains "$RUN_OUT" "[خارجي] udp 0.0.0.0:1900" "R6: خدمة مجهولة على 1900 تظهر [خارجي] (لا تُخفى)"
assert_not_contains "$RUN_OUT" "[اكتشاف شبكي]" "R6: لا وسم اكتشاف لأي خدمة مجهولة في المشهد"
assert_contains "$RUN_OUT" "[شبكة محلية] tcp [fd00::1]:8080" "R7: مستمع ULA → شبكة محلية لا خارجية"
assert_contains "$RUN_OUT" "[خارجي؟] tcp [2001:db8::1]:443" "R7: مستمع IPv6 عالمي يبقى خارجياً (regression)"
assert_contains "$RUN_OUT" "3 منفذاً منشورة" "R6/R7: العد الخارجي 3 بالضبط (5353+1900+2001:db8)"
assert_rc_nonzero "$RUN_RC" "R6/R7: مشهد ملوث → RC≠0"
unset NFT_FILE SS_FILE DOCKER_PS UFW_STATE CARE_RESOLVED_CONF CARE_RESOLVED_CONF_D

echo "─────────────────────────────"
echo "GUARD: $PASS نجح، $FAIL فشل"
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
