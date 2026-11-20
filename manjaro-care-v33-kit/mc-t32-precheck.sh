#!/usr/bin/env bash
# T3.2 (v3.3) — فحوص ما قبل الدمج (قراءة فقط) — توكن G3-R في GH_TOKEN (لا G3-W)
# المدخلات: بصمات G4 الثلاث (القسم 10). المخرجات: CHECKED_HEAD_SHA وOLD_MAIN_SHA تُنسخ إلى سجل التجربة.
set -Eeuo pipefail
trap 'echo "FAIL: سطر $LINENO — الأمر: $BASH_COMMAND" >&2' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-lib.sh
source "$SCRIPT_DIR/mc-lib.sh"

for t in git gh jq awk sha256sum stat df mktemp tr tail sort; do command -v "$t" >/dev/null || die "الأداة $t غير مثبتة"; done
[ -n "${GH_TOKEN:-}" ] || die "GH_TOKEN (توكن G3-R) غير مُعرَّف في هذه الجلسة"
load_space_factor

CHECKED_HEAD_SHA="$(live_ref "refs/heads/$PR_BRANCH")" || die "تعذرت قراءة رأس الفرع حيًا"
OLD_MAIN_SHA="$(live_ref refs/heads/main)" || die "تعذرت قراءة رأس main حيًا"
log "CHECKED_HEAD_SHA=$CHECKED_HEAD_SHA"
log "OLD_MAIN_SHA=$OLD_MAIN_SHA"

make_workspace
REPO_SIZE_KB="$(repo_size_kb)" || exit 1
need_space "$WS" $(( REPO_SIZE_KB * 1024 * MC_SPACE_FACTOR )) "جلب main والفرع" || exit 1

CLONE="$WS/repo.git"
git init -q --bare "$CLONE"
GIT_TERMINAL_PROMPT=0 git -c credential.helper= -C "$CLONE" fetch -q --no-tags "$REPO_URL" \
  "+refs/heads/main:refs/mc/main" "+refs/heads/${PR_BRANCH}:refs/mc/pr"
[ "$(git -C "$CLONE" rev-parse refs/mc/pr)" = "$CHECKED_HEAD_SHA" ]  || die "الفرع تحرك بين القياس والجلب"
[ "$(git -C "$CLONE" rev-parse refs/mc/main)" = "$OLD_MAIN_SHA" ]    || die "main تحركت بين القياس والجلب"

# الشرط 1: الحارس الأخير — بصمات الملفات الثلاثة مقابل G4
check_g4 "$CLONE" "$CHECKED_HEAD_SHA" || die "الشرط 1: مطابقة G4 فشلت"
log "الشرط 1: الملفات الثلاثة مطابقة بايت-ببايت لـG4"

# الشرط 7: قائمة الملفات المتغيرة مقابل القائمة البيضاء (الاسم + الحالة)
MERGE_BASE="$(git -C "$CLONE" merge-base refs/mc/main refs/mc/pr)" || die "لا merge-base بين main والفرع"
check_whitelist "$CLONE" "$MERGE_BASE" "$CHECKED_HEAD_SHA" || die "الشرط 7: الملفات المتغيرة خارج القائمة البيضاء"
log "الشرط 7: الملفات المتغيرة = القائمة البيضاء تمامًا (MERGE_BASE=$MERGE_BASE)"

# الشرطان 2 و6: حالة الدمج وحالة CI على رأس الفرع الحي
gh pr view 16 --repo DrAbdulmalek/manjaro-care --json headRefOid,mergeStateStatus,statusCheckRollup > "$WS/pr.json"
PR_HEAD="$(jq -r '.headRefOid' "$WS/pr.json")"
[ "$PR_HEAD" = "$CHECKED_HEAD_SHA" ] || die "headRefOid ($PR_HEAD) ≠ رأس الفرع الحي"
MSS="$(jq -r '.mergeStateStatus // "ABSENT"' "$WS/pr.json" | tr '[:lower:]' '[:upper:]')"
[ "$MSS" = "CLEAN" ] || die "الشرط 2: mergeStateStatus=$MSS (المتوقع CLEAN [بحاجة لتثبيت حي])"
log "الشرط 2: mergeStateStatus=CLEAN"

CI_JQ='
if (.statusCheckRollup | type) != "array" then "UNDETERMINED"
elif (.statusCheckRollup | length) == 0 then "NO_RUNS"
else
  [ .statusCheckRollup[] |
    ( if has("status") or has("conclusion") then
        ( if .status == "COMPLETED" then
            ( if (.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED") then "ok" else "fail" end )
          elif (.status == "IN_PROGRESS" or .status == "QUEUED" or .status == "PENDING" or .status == "WAITING" or .status == "REQUESTED") then "pending"
          else "unk" end )
      elif has("state") then
        ( if .state == "SUCCESS" then "ok"
          elif (.state == "PENDING" or .state == "EXPECTED") then "pending"
          elif (.state == "FAILURE" or .state == "ERROR") then "fail"
          else "unk" end )
      else "unk" end )
  ] as $c
  | if ([$c[] | select(. == "fail")] | length) > 0 then "FAIL"
    elif ([$c[] | select(. == "pending")] | length) > 0 then "PENDING"
    elif ([$c[] | select(. == "unk")] | length) > 0 then "UNDETERMINED"
    else "OK" end
end'
CI_CLASS="$(jq -r "$CI_JQ" "$WS/pr.json")"
case "$CI_CLASS" in
  OK)      log "الشرط 6: CI=OK" ;;
  NO_RUNS) log "الشرط 6: CI=NO_RUNS — لا تشغيلات: يجب أن تسمّيه موافقة T3.2 صراحةً" ;;
  FAIL|PENDING|UNDETERMINED) die "الشرط 6: CI=$CI_CLASS — توقف" ;;
  *) die "تصنيف CI غير متوقع: $CI_CLASS" ;;
esac

echo "----- انسخ إلى سجل التجربة (SC8) -----"
echo "CHECKED_HEAD_SHA=$CHECKED_HEAD_SHA"
echo "OLD_MAIN_SHA=$OLD_MAIN_SHA"
echo "MERGE_BASE=$MERGE_BASE"
echo "MERGE_STATE_STATUS=$MSS"
echo "CI=$CI_CLASS"
echo "يدويًا: الشرط 3 (سجل G-T1 مكتمل) · الشرط 4 (تشغيلات CI للـPR موثقة) · الشرط 5 (أمر التراجع بعد الدمج مدوّن في القسم 7)"
