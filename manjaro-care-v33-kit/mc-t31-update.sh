#!/usr/bin/env bash
# T3.1 (v3.3) — تحديث فرع PR #16 — لا يُشغَّل إلا بعد موافقة G5 المستقلة وبتوكن G3-W في GH_TOKEN
# المدخلان APPROVED_HEAD_SHA وAPPROVED_BASE_SHA: القيمتان الكاملتان من جدول الموافقة (القسم 10)
set -Eeuo pipefail
trap 'echo "FAIL: سطر $LINENO — الأمر: $BASH_COMMAND" >&2' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-lib.sh
source "$SCRIPT_DIR/mc-lib.sh"

for t in git gh awk sleep; do command -v "$t" >/dev/null || die "الأداة $t غير مثبتة"; done
[ -n "${GH_TOKEN:-}" ] || die "GH_TOKEN (توكن G3-W) غير مُعرَّف في هذه الجلسة"
is_sha40 "${APPROVED_HEAD_SHA:-}" || die "APPROVED_HEAD_SHA ليس SHA كاملًا من 40 خانة"
is_sha40 "${APPROVED_BASE_SHA:-}" || die "APPROVED_BASE_SHA ليس SHA كاملًا من 40 خانة"

# قراءة حية لحظة التنفيذ (دون توكن) ثم مقارنة بالموافق عليه
LIVE_HEAD_SHA="$(live_ref "refs/heads/$PR_BRANCH")" || die "تعذرت قراءة رأس الفرع حيًا"
LIVE_BASE_SHA="$(live_ref refs/heads/main)" || die "تعذرت قراءة رأس main حيًا"
log "الحي: head=$LIVE_HEAD_SHA base=$LIVE_BASE_SHA"
[ "$LIVE_HEAD_SHA" = "$APPROVED_HEAD_SHA" ] || die "رأس الفرع الحي ≠ الموافق عليه — توقف؛ أعد القياس وارجع إلى المالك"
[ "$LIVE_BASE_SHA" = "$APPROVED_BASE_SHA" ] || die "رأس main الحي ≠ الموافق عليه — توقف؛ أعد القياس وارجع إلى المالك"

EXPECTED_HEAD_SHA="$LIVE_HEAD_SHA"
gh api -X PUT repos/DrAbdulmalek/manjaro-care/pulls/16/update-branch \
  -f expected_head_sha="$EXPECTED_HEAD_SHA" || die "رفض GitHub التحديث — توقف فورًا، لا حلول قسرية، والقرار لك"

# الاستجابة غير متزامنة (202): انتظار محدود (12 × 5 ثوانٍ) ثم قراءة الرأس الجديد
NEW_HEAD_SHA=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 5
  NEW_HEAD_SHA="$(live_ref "refs/heads/$PR_BRANCH")" || NEW_HEAD_SHA=""
  [ -n "$NEW_HEAD_SHA" ] && [ "$NEW_HEAD_SHA" != "$EXPECTED_HEAD_SHA" ] && break
done
if [ -z "$NEW_HEAD_SHA" ] || [ "$NEW_HEAD_SHA" = "$EXPECTED_HEAD_SHA" ]; then
  die "لم يتغير رأس الفرع خلال 60 ثانية — لا تُعد المحاولة آليًا؛ أعد القياس وارجع إلى المالك"
fi
log "SC4: المصدر=$EXPECTED_HEAD_SHA الوجهة=$NEW_HEAD_SHA"
gh pr view 16 --repo DrAbdulmalek/manjaro-care --json mergeable,mergeStateStatus,headRefOid
echo "المتوقع: mergeStateStatus = CLEAN [بحاجة لتثبيت حي]. إن ظهر UNKNOWN فالحساب لم يكتمل: أعد القراءة بعد ثوانٍ."
echo "T3.1 لا يُحسب مكتملًا إلا بعد قراءتك للناتج أعلاه وقرارك."
