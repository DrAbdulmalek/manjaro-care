#!/usr/bin/env bash
# T4 (v3.3) — التحقق بعد التغيير (قراءة فقط) — توكن G3-R في GH_TOKEN
# المدخلات: MERGE_SHA وOLD_MAIN_SHA وبصمات G4 الثلاث (القسم 10)
set -Eeuo pipefail
trap 'echo "FAIL: سطر $LINENO — الأمر: $BASH_COMMAND" >&2' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-lib.sh
source "$SCRIPT_DIR/mc-lib.sh"

for t in git gh jq awk sha256sum stat df mktemp tr tail sort; do command -v "$t" >/dev/null || die "الأداة $t غير مثبتة"; done
[ -n "${GH_TOKEN:-}" ] || die "GH_TOKEN (توكن G3-R) غير مُعرَّف في هذه الجلسة"
is_sha40 "${MERGE_SHA:-}"    || die "MERGE_SHA ليس SHA كاملًا من 40 خانة"
is_sha40 "${OLD_MAIN_SHA:-}" || die "OLD_MAIN_SHA ليس SHA كاملًا من 40 خانة"
load_space_factor

# 1) حالة PR
PRV="$(gh pr view 16 --repo DrAbdulmalek/manjaro-care --json state,mergeCommit)"
[ "$(jq -r '.state' <<<"$PRV")" = "MERGED" ] || die "حالة PR ليست MERGED"
[ "$(jq -r '.mergeCommit.oid // ""' <<<"$PRV")" = "$MERGE_SHA" ] || die "merge SHA في PR لا يطابق MERGE_SHA"
log "حالة PR: MERGED و merge SHA مطابق"

# 2) رأس main يطابق merge SHA تمامًا
MAIN_NOW="$(live_ref refs/heads/main)" || die "تعذرت قراءة رأس main"
[ "$MAIN_NOW" = "$MERGE_SHA" ] || die "رأس main ($MAIN_NOW) لا يطابق MERGE_SHA"
log "رأس main = MERGE_SHA"

# 3) فرع الحملة محذوف
ref_absent "refs/heads/$PR_BRANCH" || die "فرع $PR_BRANCH ما زال موجودًا أو تعذر الفحص"
log "فرع الحملة غير موجود"

# 4) استنساخ جديد للقراءة فقط في tmpfs (لا مرآة T1)
make_workspace
REPO_SIZE_KB="$(repo_size_kb)" || exit 1
need_space "$WS" $(( REPO_SIZE_KB * 1024 * MC_SPACE_FACTOR )) "جلب main" || exit 1
CLONE="$WS/repo.git"
git init -q --bare "$CLONE"
GIT_TERMINAL_PROMPT=0 git -c credential.helper= -C "$CLONE" fetch -q --no-tags "$REPO_URL" "+refs/heads/main:refs/mc/main"
[ "$(git -C "$CLONE" rev-parse refs/mc/main)" = "$MERGE_SHA" ] || die "main المجلوبة لا تطابق MERGE_SHA"

# 5) المحتوى بايت-ببايت مقابل G4
check_g4 "$CLONE" "$MERGE_SHA" || die "مطابقة G4 على main فشلت"
log "الملفات الثلاثة على main مطابقة لبصمات G4"

# 6) شجرة main: أب واحد، كومِت واحد، والملفات المتغيرة = القائمة البيضاء تمامًا
git -C "$CLONE" merge-base --is-ancestor "$OLD_MAIN_SHA" "$MERGE_SHA" || die "OLD_MAIN_SHA ليس سلفًا لـMERGE_SHA"
COUNT="$(git -C "$CLONE" rev-list --count "$OLD_MAIN_SHA..$MERGE_SHA")"
[ "$COUNT" = "1" ] || die "عدد الكومِتات بين القديم والجديد = $COUNT (المتوقع 1 بعد squash) — يُحال إليك (SC5)"
check_whitelist "$CLONE" "$OLD_MAIN_SHA" "$MERGE_SHA" || die "شجرة main تغيرت خارج القائمة البيضاء"
log "شجرة القديم: $(git -C "$CLONE" rev-parse "$OLD_MAIN_SHA^{tree}")"
log "شجرة الجديد: $(git -C "$CLONE" rev-parse "$MERGE_SHA^{tree}")"

# 7) CI — توثيق فقط بحدوده المعروفة (انظر SC6)
gh run list --repo DrAbdulmalek/manjaro-care --limit 10
echo "T4: الفحوص الآلية 1–6 اجتازت؛ سجّل مخرجات CI أعلاه (غياب تشغيلات push على main متوقع وفق عطل branches: [ain])."
echo "التالي: إبطال G3-W فورًا ثم بوابة «إغلاق G3-W»."
