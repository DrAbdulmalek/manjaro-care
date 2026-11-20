#!/usr/bin/env bash
# T1 (v3.3) — النسخ الاحتياطي المشفَّر لـ manjaro-care — محكوم بالفشل
# يُشغَّل على جهازك: bash mc-backup.sh  (وملف mc-lib.sh في المجلد نفسه) — لا يُلصق سطرًا سطرًا
set -Eeuo pipefail
trap 'echo "FAIL: سطر $LINENO — الأمر: $BASH_COMMAND" >&2' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-lib.sh
source "$SCRIPT_DIR/mc-lib.sh"

AGE_KEY_FILE="${AGE_KEY_FILE:-$HOME/.config/age/mc-backup-key.txt}"   # خارج مجلد النسخة
AGE_PUBKEY="${AGE_PUBKEY:-}"
AGE_KEY_BACKUP_LOCATION="${AGE_KEY_BACKUP_LOCATION:-}"
GPG_RECIPIENT="${GPG_RECIPIENT:-}"
MC_SWAP_ENCRYPTED="${MC_SWAP_ENCRYPTED:-no}"

# 0) فحوص أولية: أدوات، توكن الجلسة، المفتاح، swap، مجلد النشر
for t in git gh jq tar gzip sha256sum stat df mktemp awk sort tr tail grep cut du ls id date swapon; do
  command -v "$t" >/dev/null || die "الأداة $t غير مثبتة"
done
case "$ENC_TOOL" in
  age) command -v age >/dev/null || die "age غير مثبت"; ENC_EXT="age" ;;
  gpg) command -v gpg >/dev/null || die "gpg غير مثبت"; ENC_EXT="gpg" ;;
  *)   die "MC_ENC_TOOL غير مدعومة: $ENC_TOOL" ;;
esac
[ -n "${GH_TOKEN:-}" ] || die "GH_TOKEN (توكن G3-R) غير مُعرَّف في هذه الجلسة — يُدخَل بـ read -rs ولا يُلصق في أي محادثة"
load_space_factor

DAY="$(date +%F)"
ARCH="mc_backup_${DAY}.tgz"
ENC_NAME="${ARCH}.${ENC_EXT}"
FINAL="$HOME/mc-backups/$DAY"
FINAL_CREATED="no"; PUBLISH_OK="no"
[ ! -e "$FINAL" ] || die "المجلد $FINAL موجود مسبقًا — تشغيل سابق لم يكتمل: انقله أو أعد تسميته ثم أعد المحاولة"

if [ "$ENC_TOOL" = "age" ]; then
  # تحصين المفتاح (ملاحظة 6): -L يخص الملف نفسه، و%a لا يرى ACLs — انظر 5.2
  [ ! -L "$AGE_KEY_FILE" ] || die "ملف المفتاح رابط رمزي (symlink) — مرفوض"
  [ -f "$AGE_KEY_FILE" ] || die "لا مفتاح في $AGE_KEY_FILE. ولّده مرة واحدة يدويًا خارج مجلد النسخ:
  mkdir -p '$(dirname "$AGE_KEY_FILE")' && age-keygen -o '$AGE_KEY_FILE'
  ثم خزّن نسخة منه في موقع مستقل (مدير كلمات مرور أو وسيط غير متصل) ولا ترسله لأي جهة."
  KEY_MODE="$(stat -c '%a' -- "$AGE_KEY_FILE")"
  [ $(( 8#$KEY_MODE & 077 )) -eq 0 ] || die "صلاحيات المفتاح ($KEY_MODE) تسمح لغير المالك — نفّذ chmod 600"
  [ "$(stat -c '%u' -- "$AGE_KEY_FILE")" = "$(id -u)" ] || die "مالك ملف المفتاح ليس المستخدم الحالي"
  KEY_DIR_MODE="$(stat -c '%a' -- "$(dirname -- "$AGE_KEY_FILE")")"
  [ $(( 8#$KEY_DIR_MODE & 022 )) -eq 0 ] || die "المجلد الأب للمفتاح ($KEY_DIR_MODE) يسمح بالكتابة لغير المالك"
  [ -n "$AGE_KEY_BACKUP_LOCATION" ] || die "AGE_KEY_BACKUP_LOCATION فارغ — صرّح بموقع النسخة الاحتياطية المستقلة للمفتاح"
  PUBKEY="${AGE_PUBKEY:-$(grep '^# public key:' "$AGE_KEY_FILE" | cut -d' ' -f4 || true)}"
  [ -n "$PUBKEY" ] || die "لم أستخرج المفتاح العمومي من الملف — مرره في متغير AGE_PUBKEY"
  log "المفتاح مقبول. موقع النسخة الاحتياطية المصرَّح به (غير قابل للتحقق آليًا): $AGE_KEY_BACKUP_LOCATION"
else
  [ -n "$GPG_RECIPIENT" ] || die "GPG_RECIPIENT فارغ — مسار GPG لا يفحص حراسة المفتاح الخاص"
fi

# بوابة swap: محتوى tmpfs قد يُكتب على القرص عبر swap غير مشفَّر
SWAP_BAD=""
while IFS= read -r swp; do
  [ -n "$swp" ] || continue
  case "$swp" in /dev/zram*) ;; *) SWAP_BAD="$SWAP_BAD $swp" ;; esac
done < <(swapon --show --noheadings --raw | awk '{print $1}')
if [ -n "$SWAP_BAD" ]; then
  [ "$MC_SWAP_ENCRYPTED" = "yes" ] || die "يوجد swap غير zram:$SWAP_BAD — قد تُكتب بيانات tmpfs على القرص. إما swapoff مؤقتًا أو تشفير swap ثم MC_SWAP_ENCRYPTED=yes"
  log "تصريح منك: swap مشفَّر (غير قابل للتحقق آليًا):$SWAP_BAD"
fi

# 1) مساحة العمل (tmpfs) والفخاخ قبل أي بيانات، ثم فحص السعة قبل الاستنساخ
make_workspace
DATA="$WS/data"
mkdir "$DATA"
REPO_SIZE_KB="$(repo_size_kb)" || exit 1
need_space "$WS" $(( REPO_SIZE_KB * 1024 * MC_SPACE_FACTOR )) "استنساخ المرآة" || exit 1

# 2) المرآة الكاملة + تسجيل refs/heads/main صراحةً + سلامة بـpipefail + لقطة المراجع
GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone --mirror "$REPO_URL" "$DATA/manjaro-care.git"
MAIN_SHA="$(git -C "$DATA/manjaro-care.git" rev-parse refs/heads/main)"
is_sha40 "$MAIN_SHA" || die "SHA رأس main غير صالح: $MAIN_SHA"
echo "$MAIN_SHA" > "$DATA/main_head.sha"
log "SHA رأس main = $MAIN_SHA"
git -C "$DATA/manjaro-care.git" fsck --full 2>&1 | tee "$DATA/fsck.log"   # pipefail: أي فشل fsck يوقف كل شيء
MIRROR_REFS="$(git -C "$DATA/manjaro-care.git" for-each-ref --format='%(objectname) %(refname)' | LC_ALL=C sort)"

# 3) تصدير JSON: ناتج الصفحات الخام (--slurp = مصفوفة صفحات) ثم فحص البنية والتسطيح
gh api --paginate --slurp 'repos/DrAbdulmalek/manjaro-care/pulls?state=all&per_page=100'  > "$DATA/mc_pr_pages.json"
gh api --paginate --slurp 'repos/DrAbdulmalek/manjaro-care/issues?state=all&per_page=100' > "$DATA/mc_issue_pages.json"

jq -e 'type == "array" and all(.[]; type == "array")' "$DATA/mc_pr_pages.json"    >/dev/null || die "بنية صفحات PRs غير متوقعة"
jq -e 'type == "array" and all(.[]; type == "array")' "$DATA/mc_issue_pages.json" >/dev/null || die "بنية صفحات issues غير متوقعة"
jq -e '[.[][]]' "$DATA/mc_pr_pages.json"    > "$DATA/mc_prs.json"
jq -e '[.[][]]' "$DATA/mc_issue_pages.json" > "$DATA/mc_issues.json"

jq -e 'type == "array" and length >= 11' "$DATA/mc_prs.json"    >/dev/null || die "mc_prs.json: نوع/عدد غير متوقع"
jq -e 'type == "array" and length > 0'   "$DATA/mc_issues.json" >/dev/null || die "mc_issues.json: نوع/عدد غير متوقع"
# Issues النقية — بعد التسطيح لا قبله:
jq '[.[] | select(.pull_request == null)]' "$DATA/mc_issues.json" > "$DATA/mc_issues_pure.json"
jq -e 'type == "array"' "$DATA/mc_issues_pure.json" >/dev/null || die "mc_issues_pure.json ليس مصفوفة"
log "PRs=$(jq 'length' "$DATA/mc_prs.json") · issues_all=$(jq 'length' "$DATA/mc_issues.json") · issues_pure=$(jq 'length' "$DATA/mc_issues_pure.json")"

# 4) الأرشفة + البصمة المرجعية (في الذاكرة فقط) + التشفير + تحقق آلي منه
MEAS="$(du -sb "$DATA" | cut -f1)"
need_space "$WS" $(( MEAS * MC_SPACE_FACTOR )) "أرشفة وتشفير" || exit 1
tar -czf "$WS/$ARCH" -C "$DATA" manjaro-care.git mc_pr_pages.json mc_issue_pages.json mc_prs.json \
  mc_issues.json mc_issues_pure.json main_head.sha fsck.log
[ -s "$WS/$ARCH" ] || die "الأرشيف فارغ"
RAW_HASH="$(sha256sum "$WS/$ARCH" | awk '{print $1}')"
encrypt_file "$WS/$ARCH" "$WS/$ENC_NAME"
[ -s "$WS/$ENC_NAME" ] || die "ملف التشفير غير موجود أو فارغ"
ENC_HASH="$(sha256sum "$WS/$ENC_NAME" | awk '{print $1}')"      # بصمة ملف التشفير لحظة إنشائه
DEC_HASH="$(decrypt_hash "$WS/$ENC_NAME")"
[ "$DEC_HASH" = "$RAW_HASH" ] || die "بصمة فك التشفير لا تطابق الأصل"

# 5) حذف الأصل غير المشفَّر من tmpfs فور إثبات التطابق (قبل تمرين الاستعادة)
rm -rf -- "$DATA" "$WS/$ARCH"
log "حُذف الأصل غير المشفَّر من مساحة العمل بعد إثبات تطابق فك التشفير"

# 6) تمرين الاستعادة الكامل من الملف المشفَّر — أربع طبقات (إن فشل فالإعادة من GitHub)
need_space "$WS" $(( MEAS * MC_SPACE_FACTOR )) "تمرين الاستعادة" || exit 1
DRILL_WANT_ENC_HASH="$ENC_HASH"; DRILL_WANT_RAW_HASH="$RAW_HASH"
DRILL_WANT_MAIN="$MAIN_SHA";     DRILL_WANT_REFS="$MIRROR_REFS"
restore_drill "$WS/$ENC_NAME" "$WS/drill"

# 7) النشر إلى التخزين الدائم: ملفان فقط، بعد اجتياز الطبقات الأربع
ENC_SIZE="$(stat -c %s -- "$WS/$ENC_NAME")"
mkdir -p "$HOME/mc-backups"
need_space "$HOME/mc-backups" $(( ENC_SIZE * MC_SPACE_FACTOR )) "نشر الأرشيف المشفَّر" || exit 1
mkdir "$FINAL"
FINAL_CREATED="yes"
cp -- "$WS/$ENC_NAME" "$FINAL/$ENC_NAME"
PUB_HASH="$(sha256sum "$FINAL/$ENC_NAME" | awk '{print $1}')"
[ "$PUB_HASH" = "$ENC_HASH" ] || die "بصمة النسخة المنشورة لا تطابق بصمة لحظة الإنشاء"
printf '%s  %s\n' "$ENC_HASH" "$ENC_NAME" > "$FINAL/$ENC_NAME.sha256"
( cd "$FINAL" && sha256sum -c -- "$ENC_NAME.sha256" >/dev/null ) || die "sha256sum -c فشل على النسخة المنشورة"

# 8) فحص النظافة: لا شيء سوى الملفين على القرص الدائم
GOT_LS="$(ls -A "$FINAL" | LC_ALL=C sort)"
WANT_LS="$(printf '%s\n%s\n' "$ENC_NAME" "$ENC_NAME.sha256" | LC_ALL=C sort)"
[ "$GOT_LS" = "$WANT_LS" ] || die "محتوى $FINAL خارج القائمة المسموحة"
PUBLISH_OK="yes"

# 9) الإعلان — بعد الطبقات ①②③④ والنشر والنظافة فقط (انسخ هذه المخرجات إلى سجل التجربة SC8)
log "SUCCESS: الطبقات ①②③④ ناجحة آليًا + نشر ملفين فقط + نظافة"
echo "MAIN_SHA=$MAIN_SHA"
echo "ENC_FILE=$FINAL/$ENC_NAME"
echo "ENC_SHA256=$ENC_HASH"
echo "ENC_SIZE_BYTES=$ENC_SIZE"
echo "انقل الأرشيف المشفَّر إلى وسيطك الآمن وأبقه. المفتاح في موقعه المنفصل."
echo "تنبيه: وجود المفتاح اليوم لا يضمن الاستعادة مستقبلًا — اختبر النسخة الاحتياطية للمفتاح دوريًا باستعادة فعلية منها."
