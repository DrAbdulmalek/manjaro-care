#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/manjaro-care-cli/install.sh"
BOOT="$ROOT/manjaro-care-cli/modules/boot-sanity.sh"
PACKAGES="$ROOT/manjaro-care-cli/modules/package-check.sh"
CLI="$ROOT/manjaro-care-cli/manjaro-care-cli"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
pass() { printf 'PASS: %s\n' "$1"; }

if grep -Fq 'rm -rf "$INSTALL_DIR"' "$INSTALLER"; then
    fail "installer contains recursive deletion of INSTALL_DIR"
fi
grep -Fq 'git pull --ff-only origin main' "$INSTALLER" || fail "fast-forward-only update missing"
grep -Fq 'Existing installation was left untouched' "$INSTALLER" || fail "failed update must preserve existing install"
pass "installer refuses destructive reinstall"

if grep -Eq 'rm -f /boot/grub/grubenv|GRUB_CMDLINE_LINUX_DEFAULT=.*quiet splash' "$BOOT"; then
    fail "unsafe grubenv or command-line replacement remains"
fi
grep -Fq 'fs_root' "$BOOT" || fail "Btrfs subvolume preflight missing"
grep -Fq 'rootflags=subvol=@' "$BOOT" || fail "safe rootflags append missing"
grep -Fq 'kernel_series' "$BOOT" || fail "Manjaro kernel naming detection missing"
pass "boot repair is guarded and preserves existing arguments"

if grep -Eq 'find .*\.pacnew.*-delete|find .*\.pacsave.*-delete' "$PACKAGES"; then
    fail "automatic pacnew/pacsave deletion remains"
fi
grep -Fq 'pacman -Rns --' "$PACKAGES" || fail "orphan removal must use an argument array"
pass "package cleanup preserves administrator configuration"

grep -Fq 'run_full_suite >&2' "$CLI" || fail "JSON diagnostic redirection missing"
grep -Fq '_log_message()' "$CLI" && grep -Fq 'echo -e "$1" >&2' "$CLI" || fail "JSON log output is not routed to stderr"
pass "JSON mode keeps diagnostics on stderr"

source "$PACKAGES"
log_section() { :; }
log_info() { :; }
log_ok() { :; }
log_warn() { :; }
log_err() { :; }
paccache() { :; }
PACMAN_REMOVE_CALLED=0
pacman() {
    if [[ "$1" == "-Qdtq" ]]; then
        printf 'dummy-orphan-package\n'
    elif [[ "$1" == "-Rns" ]]; then
        PACMAN_REMOVE_CALLED=1
    fi
}
if package_clean; then
    fail "non-interactive cleanup unexpectedly succeeded with orphan packages"
fi
[[ "$PACMAN_REMOVE_CALLED" -eq 0 ]] || fail "orphan packages were removed without a TTY"
pass "non-interactive cleanup cannot remove orphan packages"

printf '\nAll safety regression tests passed.\n'
