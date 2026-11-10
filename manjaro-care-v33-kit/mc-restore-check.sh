#!/usr/bin/env bash
# استعادة قراءة فقط من نسخة محفوظة (v3.3) — الطبقات ①②③④ على ملف مشفَّر موجود
# المدخل ENC_FILE: مسار ملف .age (أو .gpg) — القسم 10. لا كتابة فوق أي شيء؛ ولا يُعلَن نجاح قبل الطبقة ④.
set -Eeuo pipefail
trap 'echo "FAIL: سطر $LINENO — الأمر: $BASH_COMMAND" >&2' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-lib.sh
source "$SCRIPT_DIR/mc-lib.sh"

AGE_KEY_FILE="${AGE_KEY_FILE:-$HOME/.config/age/mc-backup-key.txt}"
GPG_RECIPIENT="${GPG_RECIPIENT:-}"
for t in git tar gzip sha256sum stat df mktemp awk sort tr tail grep; do command -v "$t" >/dev/null || die "الأداة $t غير مثبتة"; done
case "$ENC_TOOL" in
  age) command -v age >/dev/null || die "age غير مثبت" ;;
  gpg) command -v gpg >/dev/null || die "gpg غير مثبت" ;;
  *)   die "MC_ENC_TOOL غير مدعومة: $ENC_TOOL" ;;
esac
load_space_factor

[ -n "${ENC_FILE:-}" ] && [ -f "$ENC_FILE" ] || die "ENC_FILE غير موجود: ${ENC_FILE:-فارغ}"
# بصمة ملف التشفير المحفوظة بجانبه (إن وُجدت) تُفحص قبل أي فك تشفير
if [ -f "$ENC_FILE.sha256" ]; then
  ( cd "$(dirname -- "$ENC_FILE")" && sha256sum -c -- "$(basename -- "$ENC_FILE").sha256" >/dev/null ) \
    || die "بصمة ملف التشفير لا تطابق المحفوظة بجانبه"
  DRILL_WANT_ENC_HASH="$(awk '{print $1}' "$ENC_FILE.sha256")"
else
  log "تنبيه: لا ملف بصمة بجانب النسخة — الطبقة ① جزئية"
fi

make_workspace
ENC_SIZE="$(stat -c %s -- "$ENC_FILE")"
need_space "$WS" $(( ENC_SIZE * MC_SPACE_FACTOR )) "تمرين الاستعادة" || exit 1
restore_drill "$ENC_FILE" "$WS/drill"
log "SUCCESS (قراءة فقط): الطبقات ①②③④ ناجحة. أي تنبيه 'جزئية' أعلاه يعني مرجعًا لم يتوفر — اقرأه قبل الاعتماد."
