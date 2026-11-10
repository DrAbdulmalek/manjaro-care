#!/usr/bin/env bash
# mc-lib.sh (v3.3) — دوال مشتركة لتجربة manjaro-care. يُحمَّل بـ source ولا يُشغَّل مباشرة.
# لا يضع set -e بنفسه: يرث خيارات السكربت المستدعي (set -Eeuo pipefail).

REPO_SLUG="DrAbdulmalek/manjaro-care"
REPO_URL="https://github.com/${REPO_SLUG}.git"
PR_NUMBER="16"
PR_BRANCH="chore/repo-governance"

# القائمة البيضاء الوحيدة (جدول 5.0): الحالة ثم TAB ثم المسار
WHITELIST_LINES=$'A\t.github/PULL_REQUEST_TEMPLATE.md\nA\t.github/dependabot.yml\nA\tSECURITY.md'

# أداة التشفير: age (الافتراضي) أو gpg
ENC_TOOL="${MC_ENC_TOOL:-age}"

die() { echo "FAIL: $*" >&2; exit 1; }
log() { echo "== $*"; }

is_sha40() { [[ "${1:-}" =~ ^[0-9a-f]{40}$ ]]; }
is_sha64() { [[ "${1:-}" =~ ^[0-9a-f]{64}$ ]]; }

# قراءة مرجع حي دون توكن (بروتوكول git): يطبع SHA من 40 خانة أو يفشل
live_ref() {   # $1 = اسم المرجع الكامل
  local out sha
  out="$(GIT_TERMINAL_PROMPT=0 git -c credential.helper= ls-remote "$REPO_URL" "$1")" || return 1
  sha="$(printf '%s\n' "$out" | awk -v ref="$1" '$2 == ref { n++; s = $1 } END { if (n == 1) print s; else exit 1 }')" || return 1
  is_sha40 "$sha" || return 1
  printf '%s\n' "$sha"
}

# يعيد 0 فقط إن غاب المرجع فعلًا؛ خطأ الشبكة = فشل
ref_absent() {   # $1 = اسم المرجع الكامل
  local out
  out="$(GIT_TERMINAL_PROMPT=0 git -c credential.helper= ls-remote "$REPO_URL" "$1")" || return 2
  [ -z "$out" ]
}

# مقارنة تامة لقائمة الملفات المتغيرة بالقائمة البيضاء (الاسم + الحالة)
check_whitelist() {   # $1 = مستودع · $2 = المرجع القديم · $3 = المرجع الجديد
  local got want
  got="$(git -C "$1" -c core.quotepath=false diff --name-status --no-renames "$2" "$3" | LC_ALL=C sort)" || return 1
  want="$(printf '%s\n' "$WHITELIST_LINES" | LC_ALL=C sort)"
  if [ "$got" != "$want" ]; then
    echo "FAIL: الفرق الفعلي خارج القائمة البيضاء:" >&2
    printf '%s\n' "$got" >&2
    echo "المتوقع حرفيًا:" >&2
    printf '%s\n' "$want" >&2
    return 1
  fi
}

# مطابقة بايت-ببايت (sha256) للملفات الثلاثة مع بصمات G4 (من جدول المدخلات)
check_g4() {   # $1 = مستودع · $2 = المرجع
  local pair path var want got
  for pair in "SECURITY.md:G4_SHA256_SECURITY_MD" \
              ".github/dependabot.yml:G4_SHA256_DEPENDABOT_YML" \
              ".github/PULL_REQUEST_TEMPLATE.md:G4_SHA256_PR_TEMPLATE_MD"; do
    path="${pair%%:*}"; var="${pair##*:}"; want="${!var:-}"
    is_sha64 "$want" || { echo "FAIL: $var ليس sha256 كاملًا (64 خانة)" >&2; return 1; }
    got="$(git -C "$1" cat-file blob "$2:$path" | sha256sum | awk '{print $1}')" || return 1
    [ "$got" = "$want" ] || { echo "FAIL: بصمة $path ($got) لا تطابق G4 ($want)" >&2; return 1; }
  done
}

# ---------- مساحة العمل (tmpfs فقط) والتنظيف ----------
pick_workspace_base() {   # يطبع أكبر tmpfs قابل للكتابة من المرشحين أو يفشل — لا رجوع إلى القرص
  local cand fst avail best="" best_avail=-1
  for cand in "${XDG_RUNTIME_DIR:-}" /dev/shm /tmp; do
    [ -n "$cand" ] && [ -d "$cand" ] && [ -w "$cand" ] || continue
    fst="$(stat -f -c %T -- "$cand" 2>/dev/null)" || continue
    [ "$fst" = "tmpfs" ] || continue
    avail="$(df --output=avail -B1 -- "$cand" 2>/dev/null | tail -n 1 | tr -d ' ')" || continue
    case "$avail" in ''|*[!0-9]*) continue ;; esac
    if [ "$avail" -gt "$best_avail" ]; then best="$cand"; best_avail="$avail"; fi
  done
  if [ -z "$best" ]; then
    echo "FAIL: لا يوجد tmpfs قابل للكتابة (XDG_RUNTIME_DIR أو /dev/shm أو /tmp). لا رجوع إلى القرص — توقف." >&2
    return 1
  fi
  printf '%s\n' "$best"
}

need_space() {   # $1 = مجلد · $2 = بايتات مطلوبة · $3 = وصف الخطوة
  local dir="$1" need="$2" label="$3" avail
  case "$need" in ''|*[!0-9]*) echo "FAIL: مقياس السعة للخطوة «$label» غير رقمي" >&2; return 1 ;; esac
  avail="$(df --output=avail -B1 -- "$dir" | tail -n 1 | tr -d ' ')" || return 1
  case "$avail" in ''|*[!0-9]*) echo "FAIL: تعذر قياس السعة المتاحة في $dir" >&2; return 1 ;; esac
  if [ "$avail" -lt "$need" ]; then
    echo "FAIL: سعة غير كافية للخطوة «$label»: المتاح $avail بايت والمطلوب $need بايت في $dir" >&2
    return 1
  fi
}

load_space_factor() {   # يتحقق من MC_SPACE_FACTOR (افتراضي 4) ويطبعه عند كل تشغيل
  MC_SPACE_FACTOR="${MC_SPACE_FACTOR:-4}"
  case "$MC_SPACE_FACTOR" in ''|*[!0-9]*|0) die "MC_SPACE_FACTOR يجب أن يكون عددًا صحيحًا موجبًا" ;; esac
  log "MC_SPACE_FACTOR=$MC_SPACE_FACTOR (افتراضي موثق 4: أسوأ خطوة تحمل معًا المفكوك والمستعاد والمستنسخ وشجرة عمله — تقدير تحفظي لا قياس؛ لإعادة الإنتاج مرّر القيمة نفسها)"
}

repo_size_kb() {   # يطبع حجم المستودع بالكيلوبايت من الواجهة أو من MC_REPO_SIZE_KB
  local kb
  if [ -n "${MC_REPO_SIZE_KB:-}" ]; then kb="$MC_REPO_SIZE_KB"
  else kb="$(gh api "repos/${REPO_SLUG}" --jq .size)" || return 1
  fi
  case "$kb" in ''|*[!0-9]*|0) echo "FAIL: تعذر تقدير حجم المستودع (size=$kb) — مرّر MC_REPO_SIZE_KB" >&2; return 1 ;; esac
  printf '%s\n' "$kb"
}

mc_cleanup() {
  local rc=$?
  trap - EXIT
  cd / 2>/dev/null || true
  if [ -n "${WS:-}" ]; then
    case "$WS" in
      */mc-work-*) rm -rf -- "$WS" ;;
      *) echo "تحذير: مسار عمل غير متوقع لن يُحذف: $WS" >&2 ;;
    esac
  fi
  if [ "${FINAL_CREATED:-no}" = "yes" ] && [ "${PUBLISH_OK:-no}" != "yes" ]; then
    case "${FINAL:-}" in
      "$HOME"/mc-backups/*) rm -rf -- "$FINAL"; echo "حُذف ناتج نشر لم يكتمل: $FINAL" >&2 ;;
    esac
  fi
  exit "$rc"
}

install_traps() {
  trap mc_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
}

make_workspace() {   # يضبط WS ويثبّت الفخاخ — يُستدعى قبل أول أمر يولّد بيانات
  local base
  base="$(pick_workspace_base)" || return 1
  umask 077
  WS="$(mktemp -d "$base/mc-work-XXXXXX")" || return 1
  install_traps
  log "مساحة العمل (tmpfs): $WS"
}

# ---------- التشفير ----------
encrypt_file() {   # $1 = إدخال · $2 = ناتج
  case "$ENC_TOOL" in
    age) age -r "$PUBKEY" -o "$2" "$1" ;;
    gpg) gpg --batch --yes --encrypt --recipient "$GPG_RECIPIENT" -o "$2" "$1" ;;
    *)   die "MC_ENC_TOOL غير مدعومة: $ENC_TOOL" ;;
  esac
}

decrypt_file() {   # $1 = مشفَّر · $2 = ناتج
  case "$ENC_TOOL" in
    age) age -d -i "$AGE_KEY_FILE" -o "$2" "$1" ;;
    gpg) gpg --batch --yes --decrypt -o "$2" "$1" ;;
    *)   die "MC_ENC_TOOL غير مدعومة: $ENC_TOOL" ;;
  esac
}

decrypt_hash() {   # $1 = مشفَّر → يطبع sha256 للنص الصريح دون كتابته على القرص
  case "$ENC_TOOL" in
    age) age -d -i "$AGE_KEY_FILE" "$1" | sha256sum | awk '{print $1}' ;;
    gpg) gpg --batch --decrypt "$1" | sha256sum | awk '{print $1}' ;;
    *)   die "MC_ENC_TOOL غير مدعومة: $ENC_TOOL" ;;
  esac
}

# ---------- تمرين الاستعادة رباعي الطبقات ----------
# المتغيرات المرجعية الاختيارية (تضبطها T1 كلها؛ وفي الاستعادة المستقبلية يُترك ما لا يتوفر فارغًا
# فتُعلَن الطبقة المقابلة جزئية): DRILL_WANT_ENC_HASH · DRILL_WANT_RAW_HASH · DRILL_WANT_MAIN · DRILL_WANT_REFS
# تُستدعى دون || أو if حتى يبقى set -e فعّالًا؛ وكل فحص فيها يستعمل die صراحةً.
restore_drill() {   # $1 = الملف المشفَّر · $2 = مجلد التمرين (داخل WS)
  local enc="$1" d="$2" got m want_main got_main r_refs b_mirror b_clone
  mkdir -p "$d/x"

  log "① سلامة الأرشيف المشفَّر"
  [ -s "$enc" ] || die "الملف المشفَّر غير موجود أو فارغ: $enc"
  if [ -n "${DRILL_WANT_ENC_HASH:-}" ]; then
    got="$(sha256sum "$enc" | awk '{print $1}')"
    [ "$got" = "$DRILL_WANT_ENC_HASH" ] || die "بصمة الملف المشفَّر لا تطابق المسجلة لحظة إنشائه"
  else
    log "تنبيه: لا بصمة مرجعية لملف التشفير — الطبقة ① جزئية (فك مصادَق فقط)"
  fi
  decrypt_file "$enc" "$d/restored.tgz" || die "فك التشفير أو مصادقته فشل"
  got="$(sha256sum "$d/restored.tgz" | awk '{print $1}')"
  if [ -n "${DRILL_WANT_RAW_HASH:-}" ]; then
    [ "$got" = "$DRILL_WANT_RAW_HASH" ] || die "بصمة المفكوك لا تطابق بصمة الأرشيف الخام"
  else
    log "تنبيه: لا بصمة مرجعية للأرشيف الخام — مطابقة المفكوك غير مُجراة"
  fi
  log "① ناجحة"

  log "② سلامة فك الأرشفة"
  gzip -t "$d/restored.tgz" || die "gzip -t فشل"
  tar -tzf "$d/restored.tgz" > "$d/members.txt" || die "قراءة قائمة الأرشيف فشلت"
  for m in manjaro-care.git/HEAD mc_pr_pages.json mc_issue_pages.json mc_prs.json \
           mc_issues.json mc_issues_pure.json main_head.sha fsck.log; do
    grep -Fxq -- "$m" "$d/members.txt" || die "عضو إلزامي مفقود في الأرشيف: $m"
  done
  tar -xzf "$d/restored.tgz" -C "$d/x" || die "فك الأرشفة فشل"
  log "② ناجحة"

  log "③ سلامة مستودع Git المستعاد"
  git -C "$d/x/manjaro-care.git" fsck --full > "$d/fsck-restored.log" 2>&1 || { cat "$d/fsck-restored.log" >&2; die "fsck على المرآة المستعادة فشل"; }
  r_refs="$(git -C "$d/x/manjaro-care.git" for-each-ref --format='%(objectname) %(refname)' | LC_ALL=C sort)" || die "تعذرت قراءة مراجع المرآة المستعادة"
  if [ -n "${DRILL_WANT_REFS:-}" ]; then
    [ "$r_refs" = "$DRILL_WANT_REFS" ] || die "لقطة المراجع المستعادة لا تطابق لقطة المرآة الأصل"
  else
    log "تنبيه: لا لقطة مراجع مرجعية — مطابقة المراجع غير مُجراة"
  fi
  log "③ ناجحة"

  log "④ استنساخ من المرآة المستعادة (الحاسمة)"
  git clone --no-local -q "$d/x/manjaro-care.git" "$d/clone" || die "فشل الاستنساخ من المرآة المستعادة"
  got_main="$(git -C "$d/clone" rev-parse refs/remotes/origin/main)" || die "تعذرت قراءة origin/main في الاستنساخ"
  want_main="${DRILL_WANT_MAIN:-}"
  if [ -z "$want_main" ]; then
    want_main="$(tr -d ' \n' < "$d/x/main_head.sha")"
    log "تنبيه: لا SHA مرجعي لـmain — المقارنة بـmain_head.sha داخل الأرشيف نفسه (اتساق ذاتي فقط)"
  fi
  [ "$got_main" = "$want_main" ] || die "origin/main المستنسخة ($got_main) لا تطابق المسجلة ($want_main)"
  # قاعدة العدّ المعلنة: refs/heads/* في المرآة مقابل refs/remotes/origin/* في الاستنساخ
  # بعد استبعاد origin/HEAD، بأسماء مقطوعة السوابق (strip=2 و strip=3) مع SHA كل فرع
  b_mirror="$(git -C "$d/x/manjaro-care.git" for-each-ref --format='%(refname:strip=2) %(objectname)' refs/heads/ | LC_ALL=C sort)" || die "تعذرت قراءة فروع المرآة"
  b_clone="$(git -C "$d/clone" for-each-ref --format='%(refname:strip=3) %(objectname)' refs/remotes/origin/ | awk '$1 != "HEAD"' | LC_ALL=C sort)" || die "تعذرت قراءة فروع الاستنساخ"
  [ "$b_mirror" = "$b_clone" ] || die "فروع الاستنساخ (بعد استبعاد origin/HEAD) لا تطابق فروع المرآة المستعادة"
  log "④ ناجحة"
}
