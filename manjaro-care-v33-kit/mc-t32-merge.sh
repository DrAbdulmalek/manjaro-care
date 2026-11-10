#!/usr/bin/env bash
# T3.2 (v3.3) — دمج PR #16 — لا يُشغَّل إلا بعد موافقة T3.2 المستقلة وبتوكن G3-W في GH_TOKEN
# المدخلات CHECKED_HEAD_SHA وOLD_MAIN_SHA: القيمتان اللتان طبعهما mc-t32-precheck.sh (القسم 10)
set -Eeuo pipefail
trap 'echo "FAIL: سطر $LINENO — الأمر: $BASH_COMMAND" >&2' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-lib.sh
source "$SCRIPT_DIR/mc-lib.sh"

for t in git gh jq awk; do command -v "$t" >/dev/null || die "الأداة $t غير مثبتة"; done
[ -n "${GH_TOKEN:-}" ] || die "GH_TOKEN (توكن G3-W) غير مُعرَّف في هذه الجلسة"
is_sha40 "${CHECKED_HEAD_SHA:-}" || die "CHECKED_HEAD_SHA ليس SHA كاملًا من 40 خانة"
is_sha40 "${OLD_MAIN_SHA:-}" || die "OLD_MAIN_SHA ليس SHA كاملًا من 40 خانة (من مخرجات mc-t32-precheck.sh)"

LIVE_HEAD_SHA="$(live_ref "refs/heads/$PR_BRANCH")" || die "تعذرت قراءة رأس الفرع حيًا"
[ "$LIVE_HEAD_SHA" = "$CHECKED_HEAD_SHA" ] || die "الرأس الحي ($LIVE_HEAD_SHA) تغيّر بعد فحوص ما قبل الدمج — توقف وأعد الفحوص"
LIVE_MAIN_SHA="$(live_ref refs/heads/main)" || die "تعذرت قراءة رأس main حيًا"
[ "$LIVE_MAIN_SHA" = "$OLD_MAIN_SHA" ] || die "main الحية ($LIVE_MAIN_SHA) تحركت عن OLD_MAIN_SHA ($OLD_MAIN_SHA) بعد موافقة T3.2 — الدمج لم يقع؛ أعد الفحص المسبق واعرض الحالة"
log "الحارس قبل الدمج: الرأس الحي = CHECKED_HEAD_SHA وmain الحية = OLD_MAIN_SHA"

gh pr merge 16 --repo DrAbdulmalek/manjaro-care --squash --delete-branch --match-head-commit "$CHECKED_HEAD_SHA"

# التوثيق الفوري
PRV="$(gh pr view 16 --repo DrAbdulmalek/manjaro-care --json state,mergeCommit)"
PR_STATE="$(jq -r '.state' <<<"$PRV")"
MERGE_SHA="$(jq -r '.mergeCommit.oid // ""' <<<"$PRV")"
[ "$PR_STATE" = "MERGED" ] || die "حالة PR بعد الأمر: $PR_STATE (المتوقع MERGED)"
is_sha40 "$MERGE_SHA" || die "merge SHA غير صالح: $MERGE_SHA"
MAIN_NOW="$(live_ref refs/heads/main)" || MAIN_NOW=""
echo "----- انسخ إلى سجل التجربة (SC4) -----"
echo "STATE=$PR_STATE"
echo "MERGE_SHA=$MERGE_SHA"
echo "MAIN_NOW=$MAIN_NOW"
[ "$MAIN_NOW" = "$MERGE_SHA" ] || echo "تنبيه: رأس main الحي لا يطابق MERGE_SHA الآن — يحسمه T4"
echo "بعد ذلك: T4 ثم إبطال G3-W فورًا."
