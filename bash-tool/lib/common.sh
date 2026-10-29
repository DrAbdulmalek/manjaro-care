#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: lib/common.sh
# المكتبة المشتركة: الإعدادات، الألوان، التسجيل في التقارير، أدوات sudo،
# إدارة ملفات التقارير، وخدمات المسح المشتركة بين الوحدات.
# =============================================================================

set -u -o pipefail

MC_VERSION="1.0.0"

# ---------------------------------------------------------------- paths ------
MC_ROOT="${MC_ROOT:-$(pwd)}"
MC_CONFIG_DIR="${MC_USER_CONFIG_DIR:-${HOME}/.config/manjaro-care}"
MC_CONFIG_FILE="${MC_CONFIG_DIR}/config"
MC_TOKEN_FILE="${MC_CONFIG_DIR}/token"
MC_REPORTS_DIR="${MC_ROOT}/reports"

# ---------------------------------------------------------------- state ------
MC_LOGFILE=""
MC_SUMMARY=""
MC_REPORT_DIR=""
MC_TASK="manual"
MC_RUN_STARTED=0
MC_AUTO=0          # --auto    : وضع غير تفاعلي بقيم آمنة
MC_ASSUME_YES=0    # --yes     : الموافقة على كل الأسئلة
MC_NO_PUSH=0       # --no-push : تعطيل الرفع إلى GitHub
MC_MIRRORS=0       # --mirrors : ترتيب المرايا قبل التحديث
MC_FAILURES=0
MC_WARNINGS=0
MC_PAMAC_STOPPED=0
MC_TS_HOOK_SAVED=""

# --------------------------------------------------------------- colors ------
if [ -t 1 ] && [ "${MC_NO_COLOR:-0}" != "1" ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_CYAN=$'\033[36m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_CYAN=""
fi

# -------------------------------------------------------- configuration ------
load_config() {
  if [ -f "$MC_CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    . "$MC_CONFIG_FILE"
  fi
  MC_GH_USER="${MC_GH_USER:-DrAbdulmalek}"
  MC_GH_REPO="${MC_GH_REPO:-manjaro-care}"
  MC_GH_BRANCH="${MC_GH_BRANCH:-main}"
  MC_KEEP_REPORTS="${MC_KEEP_REPORTS:-150}"
  MC_TOKEN=""
  if [ -f "$MC_TOKEN_FILE" ]; then
    MC_TOKEN="$(tr -d ' \t\r\n' < "$MC_TOKEN_FILE" | head -c 100)"
  fi
}

# ------------------------------------------------------------ output ---------
# يحجب التوكن من أي نص قبل كتابته في ملفات السجل
sanitize() {
  if [ -n "${MC_TOKEN:-}" ]; then
    sed -e "s|${MC_TOKEN}|***REDACTED***|g"
  else
    cat
  fi
}

_note_line() {
  # $1 = اسم متغير اللون ، $2 = الوسم ، $3 = الرسالة
  local color="$1" tag="$2" msg="$3"
  printf '%s[%s]%s %s\n' "${!color}" "$tag" "$C_RESET" "$msg"
  if [ -n "$MC_LOGFILE" ]; then
    printf '%s\n' "[$tag] $msg" | sanitize >> "$MC_LOGFILE"
  fi
}

info() { _note_line C_CYAN   "info"  "$*"; }
ok()   { _note_line C_GREEN  "ok"    "$*"; }
warn() { _note_line C_YELLOW "warn"  "$*"; MC_WARNINGS=$((MC_WARNINGS + 1)); }
err()  { _note_line C_RED    "ERROR" "$*"; MC_FAILURES=$((MC_FAILURES + 1)); }

hr() {
  printf '%s%s%s\n' "$C_DIM" "────────────────────────────────────────────────────────────" "$C_RESET"
  if [ -n "$MC_LOGFILE" ]; then printf '%s\n' "----" >> "$MC_LOGFILE"; fi
}

section() {
  printf '\n%s%s== %s ==%s\n' "$C_BOLD" "$C_BLUE" "$1" "$C_RESET"
  if [ -n "$MC_LOGFILE" ]; then printf '\n== %s ==\n' "$1" >> "$MC_LOGFILE"; fi
}

# ---------------------------------------------------------- summary.md -------
sum_h2()   { [ -n "$MC_SUMMARY" ] && printf '\n## %s\n' "$*" >> "$MC_SUMMARY"; return 0; }
sum_line() { [ -n "$MC_SUMMARY" ] && printf -- '- %s\n' "$*" >> "$MC_SUMMARY"; return 0; }

# -------------------------------------------------------- report files -------
start_report() {
  # $1 = اسم المهمة (doctor / fix / clean / update / all / sync / manual)
  MC_TASK="$1"
  if [ "$MC_RUN_STARTED" = "1" ]; then
    section "task: $MC_TASK"
    return 0
  fi
  local stamp day
  stamp="$(date +%H%M%S)"
  day="$(date +%F)"
  MC_REPORT_DIR="${MC_REPORTS_DIR}/${day}/${stamp}-${MC_TASK}"
  mkdir -p "$MC_REPORT_DIR"
  MC_LOGFILE="${MC_REPORT_DIR}/log.txt"
  MC_SUMMARY="${MC_REPORT_DIR}/summary.md"
  MC_RUN_STARTED=1
  : > "$MC_LOGFILE"
  {
    printf '# manjaro-care report — %s\n\n' "$MC_TASK"
    printf -- '- **host:** %s  \n' "$(hostname 2>/dev/null || echo '?')"
    printf -- '- **date:** %s  \n' "$(date '+%F %T %Z')"
    printf -- '- **kernel:** %s  \n' "$(uname -r)"
    printf -- '- **mode:** %s\n' "$([ "$MC_AUTO" = "1" ] && echo auto || echo interactive)"
  } >> "$MC_SUMMARY"
  info "report dir: ${MC_REPORT_DIR#${MC_ROOT}/}"
}

end_report() {
  local status="$1"
  if [ -n "$MC_SUMMARY" ]; then
    printf '\n---\n\n**result:** %s | **warnings:** %d | **errors:** %d | finished: %s\n' \
      "$status" "$MC_WARNINGS" "$MC_FAILURES" "$(date '+%F %T')" >> "$MC_SUMMARY"
  fi
}

# ------------------------------------------------------------ run helpers ----
capture() {
  # تشغيل أمر مع عرضه الحي ونسخ نظيف (بدون توكن) إلى ملف السجل
  # ملاحظة: يُمرَّر الإخراج عبر sanitize قبل الطرفية أيضاً، لأن مخرجات
  # git push قد تحتوي التوكن داخل الرابط.
  [ $# -eq 0 ] && return 0
  "$@" 2>&1 | sanitize | tee >(cat >> "${MC_LOGFILE:-/dev/null}")
  return "${PIPESTATUS[0]}"
}

as_root() {
  # تنفيذ أمر بصلاحيات root (مباشرة إن كنا root، وإلا عبر sudo)
  if [ "$(id -u)" = "0" ]; then
    capture "$@"
  else
    capture sudo "$@"
  fi
}

require_sudo() {
  if [ "$(id -u)" = "0" ]; then return 0; fi
  if ! sudo -v; then
    err "sudo credentials required but not available"
    return 1
  fi
  return 0
}

have() { command -v "$1" >/dev/null 2>&1; }
is_tty() { [ -t 0 ]; }
is_manjaro() { grep -qi 'manjaro' /etc/os-release 2>/dev/null; }

free_gb_root() {
  local v
  v="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
  printf '%s' "${v:-0}"
}

gh_push_url() {
  printf 'https://%s:%s@github.com/%s/%s.git' "$MC_GH_USER" "$MC_TOKEN" "$MC_GH_USER" "$MC_GH_REPO"
}

gh_clean_url() {
  printf 'https://github.com/%s/%s.git' "$MC_GH_USER" "$MC_GH_REPO"
}

# --------------------------------------------------------------- prompts -----
ask_yes() {
  # ask_yes "السؤال" [y|n]  → 0 نعم / 1 لا
  # في وضع --auto تُعاد القيمة الافتراضية تلقائياً.
  local q="$1" def="${2:-y}" a hint
  if [ "$MC_ASSUME_YES" = "1" ]; then return 0; fi
  if [ "$MC_AUTO" = "1" ]; then
    [ "$def" = "y" ] && return 0 || return 1
  fi
  hint="[y/N]"; [ "$def" = "y" ] && hint="[Y/n]"
  printf '%s%s %s %s' "$C_BOLD" "$q" "$hint" "$C_RESET"
  if ! read -r a; then
    echo
    [ "$def" = "y" ] && return 0 || return 1
  fi
  a="${a:-$def}"
  case "$a" in y|Y|yes|YES|نعم|Y|ن) return 0 ;; *) return 1 ;; esac
}

# ------------------------------------------------- transient-state cleanup ---
mc_cleanup() {
  # يُستدعى تلقائياً عند الخروج: يعيد هوك timeshift وخدمة pamac كما كانا
  if [ -n "$MC_TS_HOOK_SAVED" ] && [ -e "$MC_TS_HOOK_SAVED" ]; then
    local hook="${MC_TS_HOOK_SAVED%.mc-saved}"
    if [ "$(id -u)" = "0" ]; then
      mv "$MC_TS_HOOK_SAVED" "$hook" 2>/dev/null || true
    else
      sudo mv "$MC_TS_HOOK_SAVED" "$hook" 2>/dev/null || true
    fi
    info "timeshift-autosnap hook restored"
    MC_TS_HOOK_SAVED=""
  fi
  if [ "$MC_PAMAC_STOPPED" = "1" ]; then
    if [ "$(id -u)" = "0" ]; then
      systemctl start pamac-daemon.service >/dev/null 2>&1 || true
    else
      sudo systemctl start pamac-daemon.service >/dev/null 2>&1 || true
    fi
    info "pamac-daemon restarted"
    MC_PAMAC_STOPPED=0
  fi
  return 0
}

stop_pamac_if_running() {
  # إيقاف pamac-daemon مؤقتاً كي لا يزاحم pacman على قفل قاعدة البيانات
  if systemctl is-active pamac-daemon.service >/dev/null 2>&1; then
    info "pamac-daemon is running"
    if ask_yes "stop pamac-daemon during this operation (restored automatically on exit)?" "y"; then
      if as_root systemctl stop pamac-daemon.service; then
        MC_PAMAC_STOPPED=1
        ok "pamac-daemon stopped"
      fi
    fi
  else
    ok "pamac-daemon not running"
  fi
  return 0
}

# ------------------------------------------------------- pacman log utils ----
pacman_log_len() {
  if [ -f /var/log/pacman.log ]; then wc -l < /var/log/pacman.log; else echo 0; fi
}

pacman_log_since() {
  # $1 = عدد أسطر السجل قبل العملية؛ يطبع الأسطر الجديدة فقط
  if [ -f /var/log/pacman.log ]; then
    tail -n "+$(( $1 + 1 ))" /var/log/pacman.log 2>/dev/null | grep -E '\[ALPM\]' || true
  fi
}

# --------------------------------------- shared scan: broken foreign bins ----
# يفحص حزم AUR/الأجنبية بحثاً عن مكتبات مشتركة مفقودة (مثل حالة Orthanc بعد
# ترقية jsoncpp/boost/protobuf). النتائج في MC_SCAN_RESULTS (pkg|binary|lib)
scan_foreign_broken_bins() {
  MC_SCAN_RESULTS=""
  local pkgs p bin missing
  pkgs="$(pacman -Qmq 2>/dev/null | head -n 40 || true)"
  [ -z "$pkgs" ] && return 0
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    while IFS= read -r bin; do
      case "$bin" in
        /usr/bin/*|/usr/sbin/*|/bin/*|/sbin/*) ;;
        *) continue ;;
      esac
      [ -f "$bin" ] || continue
      missing="$(ldd "$bin" 2>/dev/null | grep 'not found' | sed 's/^\s*//' || true)"
      if [ -n "$missing" ]; then
        while IFS= read -r m; do
          MC_SCAN_RESULTS="${MC_SCAN_RESULTS}${p}|${bin}|${m}"$'\n'
        done <<< "$missing"
      fi
    done < <(pacman -Qlq "$p" 2>/dev/null | grep -E '^/(usr/)?s?bin/' | head -n 8)
  done <<< "$pkgs"
  return 0
}
