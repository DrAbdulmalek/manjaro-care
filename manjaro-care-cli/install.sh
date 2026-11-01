#!/usr/bin/env bash
# Safe installer: never recursively deletes an existing installation or user data.
set -Eeuo pipefail

INSTALLER_LANG="${APP_LANG:-ar}"
if [[ "$INSTALLER_LANG" == "en" ]]; then
    TITLE="manjaro-care-cli Safe Installer"
    MSG_ROOT="This script must run as root (sudo)."
    MSG_GIT="Installing prerequisite git..."
    MSG_GIT_FAIL="Failed to install git."
    MSG_NO_PM="Package manager not found; install git manually."
    MSG_CLONE="Cloning repository into %s ..."
    MSG_UPDATE="Updating existing installation at %s ..."
    MSG_PULL_FAIL="Update failed. Existing installation was left untouched."
    MSG_UNSAFE="Refusing to use a non-empty directory that is not this Git installation: %s"
    MSG_PATH="Install and binary paths must be absolute, non-root paths."
    MSG_BIN="Refusing to replace an existing non-symlink command: %s"
    MSG_DONE="Installation completed."
    MSG_USAGE="Usage: sudo mcare doctor | sudo mcare --help"
else
    TITLE="المثبت الآمن لـ manjaro-care-cli"
    MSG_ROOT="يجب تشغيل المثبت بصلاحيات root (sudo)."
    MSG_GIT="تثبيت المتطلب git..."
    MSG_GIT_FAIL="فشل تثبيت git."
    MSG_NO_PM="لم يُعثر على مدير الحزم؛ ثبّت git يدوياً."
    MSG_CLONE="استنساخ المستودع إلى %s ..."
    MSG_UPDATE="تحديث التثبيت الموجود في %s ..."
    MSG_PULL_FAIL="فشل التحديث؛ تُرك التثبيت الحالي دون تغيير."
    MSG_UNSAFE="رفض استخدام مجلد غير فارغ ليس مستودع التثبيت المتوقع: %s"
    MSG_PATH="يجب أن تكون مسارات التثبيت والأوامر مطلقة وليست الجذر."
    MSG_BIN="رفض استبدال أمر موجود ليس رابطاً رمزياً: %s"
    MSG_DONE="اكتمل التثبيت."
    MSG_USAGE="الاستخدام: sudo mcare doctor أو sudo mcare --help"
fi

if [[ $EUID -ne 0 ]]; then
    printf '✗ %s\n' "$MSG_ROOT" >&2
    exit 1
fi

INSTALL_DIR="${MCARE_INSTALL_DIR:-/opt/manjaro-care-cli}"
BIN_DIR="${MCARE_BIN_DIR:-/usr/local/bin}"
REPO_URL="${MCARE_REPO_URL:-https://github.com/DrAbdulmalek/manjaro-care.git}"
CLI_SUBDIR="manjaro-care-cli"

if [[ "$INSTALL_DIR" != /* || "$BIN_DIR" != /* || "$INSTALL_DIR" == "/" || "$BIN_DIR" == "/" ]]; then
    printf '✗ %s\n' "$MSG_PATH" >&2
    exit 1
fi

INSTALL_DIR="$(realpath -m -- "$INSTALL_DIR")"
BIN_DIR="$(realpath -m -- "$BIN_DIR")"
case "$INSTALL_DIR" in
    /|/usr|/etc|/var|/home|/boot) printf '✗ %s\n' "$MSG_PATH" >&2; exit 1 ;;
esac

printf '═══════════════════════════════════════\n  %s\n═══════════════════════════════════════\n' "$TITLE"
printf '📦 %s\n' "$MSG_GIT"
if ! command -v git >/dev/null 2>&1; then
    if command -v pacman >/dev/null 2>&1; then
        pacman -S --needed git || { printf '✗ %s\n' "$MSG_GIT_FAIL" >&2; exit 1; }
    else
        printf '✗ %s\n' "$MSG_NO_PM" >&2
        exit 1
    fi
fi

PARENT_DIR="$(dirname -- "$INSTALL_DIR")"
mkdir -p -- "$PARENT_DIR"
if [[ -L "$INSTALL_DIR" ]]; then
    printf '✗ %s\n' "$(printf "$MSG_UNSAFE" "$INSTALL_DIR")" >&2
    exit 1
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    printf '📥 %s\n' "$(printf "$MSG_UPDATE" "$INSTALL_DIR")"
    if ! git -C "$INSTALL_DIR" pull --ff-only origin main; then
        printf '✗ %s\n' "$MSG_PULL_FAIL" >&2
        exit 1
    fi
elif [[ -e "$INSTALL_DIR" ]]; then
    if [[ -d "$INSTALL_DIR" ]] && [[ -z "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
        rmdir -- "$INSTALL_DIR"
    else
        printf '✗ %s\n' "$(printf "$MSG_UNSAFE" "$INSTALL_DIR")" >&2
        exit 1
    fi
fi

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    printf '📥 %s\n' "$(printf "$MSG_CLONE" "$INSTALL_DIR")"
    TMP_PARENT="$(mktemp -d "$PARENT_DIR/.mcare-install.XXXXXX")"
    cleanup() { [[ -n "${TMP_PARENT:-}" && -d "$TMP_PARENT" ]] && rm -rf -- "$TMP_PARENT"; }
    trap cleanup EXIT
    git clone --depth 1 "$REPO_URL" "$TMP_PARENT/repository"
    [[ -f "$TMP_PARENT/repository/$CLI_SUBDIR/manjaro-care-cli" && -d "$TMP_PARENT/repository/$CLI_SUBDIR/modules" ]] || {
        printf '✗ Invalid repository layout.\n' >&2
        exit 1
    }
    if [[ -e "$INSTALL_DIR" ]]; then
        printf '✗ %s\n' "$(printf "$MSG_UNSAFE" "$INSTALL_DIR")" >&2
        exit 1
    fi
    mv -- "$TMP_PARENT/repository" "$INSTALL_DIR"
    rmdir -- "$TMP_PARENT"
    TMP_PARENT=""
    trap - EXIT
fi

APP_DIR="$INSTALL_DIR/$CLI_SUBDIR"
if [[ ! -f "$APP_DIR/manjaro-care-cli" || ! -d "$APP_DIR/modules" ]]; then
    printf '✗ Invalid installation layout at %s\n' "$APP_DIR" >&2
    exit 1
fi

chmod +x "$APP_DIR/manjaro-care-cli"
find "$APP_DIR/modules" -maxdepth 1 -type f -name '*.sh' -exec chmod +x {} +

mkdir -p -- "$BIN_DIR"
MC_BIN="$BIN_DIR/mcare"
if [[ -e "$MC_BIN" && ! -L "$MC_BIN" ]]; then
    printf '✗ %s\n' "$(printf "$MSG_BIN" "$MC_BIN")" >&2
    exit 1
fi
if [[ -L "$MC_BIN" ]]; then
    OLD_TARGET="$(readlink -f -- "$MC_BIN" 2>/dev/null || true)"
    case "$OLD_TARGET" in
        "$INSTALL_DIR"/*) ;;
        *) printf '✗ %s\n' "$(printf "$MSG_BIN" "$MC_BIN")" >&2; exit 1 ;;
    esac
fi
ln -sfn -- "$APP_DIR/manjaro-care-cli" "$MC_BIN"

mkdir -p -- "$APP_DIR/reports" "$APP_DIR/backups"
printf '✓ %s\n%s\n%s\n' "$MSG_DONE" "$MSG_USAGE" "$INSTALL_DIR"
