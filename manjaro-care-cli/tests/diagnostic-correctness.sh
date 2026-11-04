#!/usr/bin/env bash
#
# اختبارات صحة التشخيص — BUG-CLI-01..06 + حارس الحكم الإجمالي
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
  "scrub status")     printf 'UUID: test-uuid\nScrub started: Sun 02 Nov 2026 03:00:00 AM +03\nStatus: %s\nDuration: 123s\nError summary: no errors found\n' "${SCRUB_STATE:-}"; exit 0 ;;
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
assert_contains "$RUN_OUT" "[خارجي] udp 0.0.0.0:5353" "security → 0.0.0.0:5353 خارجي فعلاً"
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

echo "─────────────────────────────"
echo "GUARD: $PASS نجح، $FAIL فشل"
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
