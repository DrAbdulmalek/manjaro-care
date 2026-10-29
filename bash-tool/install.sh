#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: install.sh
# مثبّت الأداة:
#   1) يتحقق من المتطلبات (git, curl, sudo)
#   2) يستنسخ المستودع إلى ~/manjaro-care-cli (أو يحدّثه إن كان موجوداً)
#   3) يطلب توكن GitHub ويتحقق منه ويحفظه بصلاحيات 600
#   4) يربط الأمر manjaro-care-cli في ~/.local/bin
# =============================================================================
set -u

GH_USER="DrAbdulmalek"
GH_REPO="manjaro-care"
REPO_URL="https://github.com/${GH_USER}/${GH_REPO}.git"
DEST="${HOME}/manjaro-care-cli"
CFG_DIR="${HOME}/.config/manjaro-care-cli"

G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; B=$'\033[1m'; N=$'\033[0m'

step() { printf '\n%s== %s ==%s\n' "$B" "$1" "$N"; }
good() { printf '%s[ok]%s %s\n' "$G" "$N" "$1"; }
warnp() { printf '%s[warn]%s %s\n' "$Y" "$N" "$1"; }
die() { printf '%s[ERROR]%s %s\n' "$R" "$N" "$1"; exit 1; }

echo
echo "${B}manjaro-care installer${N} — أداة صيانة مانجارو مع أرشفة على GitHub"
echo "repo: $REPO_URL → dest: $DEST"
echo

step "1/5 requirements"
have() { command -v "$1" >/dev/null 2>&1; }
have git   || die "git is required (sudo pacman -S git)"
have curl  || die "curl is required (sudo pacman -S curl)"
grep -qi manjaro /etc/os-release || warnp "this does not look like Manjaro — continuing anyway"
good "requirements satisfied"

step "2/5 clone / update repository"
if [ -d "$DEST/.git" ]; then
  echo "existing clone found at $DEST — updating"
  git -C "$DEST" pull --ff-only || warnp "pull failed (offline?) — using local copy as is"
else
  git clone "$REPO_URL" "$DEST" || die "clone failed — check network/URL"
  good "cloned to $DEST"
fi

step "3/5 GitHub token"
mkdir -p "$CFG_DIR"
TOKEN_FILE="$CFG_DIR/token"
TOKEN=""
if [ -f "$TOKEN_FILE" ]; then
  TOKEN="$(tr -d ' \t\r\n' < "$TOKEN_FILE")"
  warnp "existing token found at $TOKEN_FILE"
fi
if [ -n "${1:-}" ]; then
  TOKEN="$1"
  echo "token supplied via argument"
else
  printf '%s' "GitHub token [press Enter to keep existing]: "
  read -r -s INPUT_TOK || true
  echo
  [ -n "$INPUT_TOK" ] && TOKEN="$INPUT_TOK"
fi
[ -n "$TOKEN" ] || die "no token available — get one at https://github.com/settings/tokens (scope: repo)"

echo "verifying token with GitHub..."
LOGIN="$(curl -s -m 15 -H "Authorization: token $TOKEN" https://api.github.com/user | grep -m1 '"login"' | cut -d'"' -f4)"
[ -n "$LOGIN" ] || die "token verification failed"
good "token OK — account: $LOGIN"

printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
good "token saved: $TOKEN_FILE (mode 600)"

printf 'MC_GH_USER=%s\nMC_GH_REPO=%s\nMC_GH_BRANCH=main\nMC_KEEP_REPORTS=150\n' "$GH_USER" "$GH_REPO" > "$CFG_DIR/config"
chmod 600 "$CFG_DIR/config"
good "config saved: $CFG_DIR/config"

step "4/5 command symlink"
mkdir -p "$HOME/.local/bin"
chmod +x "$DEST/manjaro-care"
ln -sf "$DEST/manjaro-care" "$HOME/.local/bin/manjaro-care-cli"
good "linked: $HOME/.local/bin/manjaro-care-cli"

case ":$PATH:" in
  *":$HOME/.local/bin:"*) good "~/.local/bin already in PATH" ;;
  *)
    warnp "~/.local/bin is not in PATH — adding to shell rc files"
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
      if [ -f "$rc" ] && ! grep -q '.local/bin' "$rc"; then
        printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
      fi
    done
    echo "  → open a new terminal or run: export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

step "5/5 smoke test"
"$DEST/manjaro-care" version || die "smoke test failed"

cat <<EOF

${G}installation complete.${N}
${B}Quick start:${N}
  manjaro-care-cli            interactive menu (القائمة التفاعلية)
  manjaro-care-cli doctor     full health check
  manjaro-care-cli all        full maintenance cycle
  manjaro-care-cli --auto     unattended mode (for systemd timer / cron)

${Y}SECURITY NOTE:${N}
  The token you used was shared in a chat session — treat it as exposed.
  Recommended: create a fresh token with ONLY the 'repo' scope, run
  'manjaro-care-cli config' to replace it, then revoke the old one at
  https://github.com/settings/tokens

Reports land in: $DEST/reports (pushed to GitHub automatically after each run)
EOF
