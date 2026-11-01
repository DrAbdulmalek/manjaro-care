#!/usr/bin/env bash
# =============================================================================
# manjaro-care-cli :: install.sh
#   1) يتحقق من المتطلبات
#   2) يستخدم نسخة المستودع التي يوجد فيها هذا السكربت (لا يستنسخ شيئاً ثانياً)
#   3) يربط الأمر manjaro-care-cli في ~/.local/bin
#   4) اختياري: إعداد رفع التقارير إلى مستودع GitHub *خاص* (توكن يُقرأ بإخفاء
#      ولا يُقبل كوسيط سطر أوامر كي لا يُحفظ في تاريخ الطرفية)
# =============================================================================
set -u

HERE="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
CFG_DIR="${HOME}/.config/manjaro-care-cli"

G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; B=$'\033[1m'; N=$'\033[0m'
step()  { printf '\n%s== %s ==%s\n' "$B" "$1" "$N"; }
good()  { printf '%s[ok]%s %s\n' "$G" "$N" "$1"; }
warnp() { printf '%s[warn]%s %s\n' "$Y" "$N" "$1"; }
die()   { printf '%s[ERROR]%s %s\n' "$R" "$N" "$1"; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }

[ -f "$HERE/manjaro-care" ] && [ -f "$HERE/lib/common.sh" ] || die "run install.sh from inside the bash-tool directory of the repo"
if [ -n "${1:-}" ]; then
  die "do not pass a token as an argument (it would land in your shell history and ps). Run without arguments."
fi

echo
echo "${B}manjaro-care-cli installer${N} — source: $HERE"

step "1/4 requirements"
have git  || die "git is required (sudo pacman -S git)"
have curl || die "curl is required (sudo pacman -S curl)"
grep -qi manjaro /etc/os-release 2>/dev/null || warnp "this does not look like Manjaro — continuing anyway"
good "requirements satisfied"

step "2/4 command symlink"
mkdir -p "$HOME/.local/bin"
chmod +x "$HERE/manjaro-care"
ln -sf "$HERE/manjaro-care" "$HOME/.local/bin/manjaro-care-cli"
good "linked: $HOME/.local/bin/manjaro-care-cli → $HERE/manjaro-care"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) good "\$HOME/.local/bin already in PATH" ;;
  *) warnp "\$HOME/.local/bin is not in PATH — add: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

step "3/4 optional: report upload to a PRIVATE GitHub repo"
mkdir -p "$CFG_DIR"; chmod 700 "$CFG_DIR"
GH_USER="DrAbdulmalek"; GH_REPO="manjaro-care-reports"
if [ ! -f "$CFG_DIR/config" ]; then
  printf 'MC_GH_USER=%s\nMC_GH_REPO=%s\nMC_GH_BRANCH=main\nMC_KEEP_REPORTS=150\nMC_PUSH=0\n' "$GH_USER" "$GH_REPO" > "$CFG_DIR/config"
  chmod 600 "$CFG_DIR/config"
  good "config created: $CFG_DIR/config (push is OFF by default; reports stay local)"
else
  good "existing config kept: $CFG_DIR/config"
fi
echo "Reports contain host details. To enable upload: create a PRIVATE repo '$GH_USER/$GH_REPO',"
echo "a fine-grained token limited to it, then run: manjaro-care-cli config   and set MC_PUSH=1 in the config."

step "4/4 smoke test"
"$HERE/manjaro-care" --version </dev/null || die "smoke test failed"
"$HOME/.local/bin/manjaro-care-cli" --version </dev/null >/dev/null || die "symlink smoke test failed"

cat <<EOT

${G}installation complete.${N}
  manjaro-care-cli            interactive menu
  manjaro-care-cli doctor     read-only health check
  manjaro-care-cli fix        repair common problems (asks before risky steps)
  manjaro-care-cli update     system upgrade with checks (guards the timeshift hook)

Reports stay in: ~/.local/share/manjaro-care-cli/reports
EOT
