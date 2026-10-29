#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/update.sh  — أمر update
# فحوصات مسبقة (مساحة، قفل، pamac) → pacman -Syu → معالجة ما بعد التحديث:
# .pacnew، تحديث النواة (تنبيه reboot/DKMS)، وتعطيل مؤقت لهوك timeshift
# في الوضع غير التفاعلي كي لا تتجمد المعاملة عند سؤال "Select backup device".
# =============================================================================

cmd_update() {
  start_report "update"
  if ! require_sudo; then
    err "update needs sudo — aborting"
    return 1
  fi
  local rc=0

  # ---------------------------------------------------------- pre-flight ----
  section "update: pre-flight checks"
  sum_h2 "Update"
  local free
  free="$(free_gb_root)"
  if [ "$free" -lt 3 ]; then
    err "low disk space: ${free}G free (<3G) — update aborted"
    sum_line "**aborted**: low disk space (${free}G)"
    return 1
  fi
  ok "disk space: ${free}G free"
  sum_line "disk free before: ${free}G"

  if [ -e /var/lib/pacman/db.lck ]; then
    err "pacman lock exists — run 'manjaro-care fix' first"
    sum_line "**aborted**: pacman db.lck present"
    return 1
  fi
  ok "no pacman lock"

  stop_pamac_if_running

  if [ "$MC_MIRRORS" = "1" ]; then
    if have pacman-mirrors; then
      section "update: ranking mirrors (fasttrack 5)"
      if as_root pacman-mirrors --fasttrack 5; then
        as_root pacman -Syy || true
        ok "mirrors ranked"
        sum_line "mirrors: ranked (fasttrack 5)"
      else
        warn "mirror ranking failed — continuing with current mirrors"
      fi
    else
      warn "pacman-mirrors not installed — skipping"
    fi
  fi

  # -------------------------------------------- timeshift-autosnap guard ----
  # ملاحظة من لوجك: --hookdir لا يعطل الهوك الافتراضي؛ الحل الموثوق هو
  # تعطيل الهوك مؤقتاً أثناء المعاملة وإعادته عند الخروج (mc_cleanup).
  local hook="/usr/share/libalpm/hooks/timeshift-autosnap.hook"
  if [ -f "$hook" ]; then
    if [ "$MC_AUTO" = "1" ] || ! is_tty; then
      local ts_out ts_rc
      ts_out="$(sudo timeshift --list --scripted 2>&1 </dev/null)"; ts_rc=$?
      if [ $ts_rc -ne 0 ] || printf '%s' "$ts_out" | grep -q 'Select backup device'; then
        warn "timeshift not usable in scripted mode → autosnap hook temporarily disabled for this transaction"
        if as_root mv "$hook" "${hook}.mc-saved"; then
          MC_TS_HOOK_SAVED="${hook}.mc-saved"
          sum_line "timeshift hook: temporarily disabled during transaction"
        else
          err "could not disable autosnap hook — transaction may hang"
        fi
      else
        ok "timeshift scripted mode works — hook left in place"
      fi
    else
      info "note: timeshift-autosnap hook will run — answer its prompt if it appears"
    fi
  fi

  # ------------------------------------------------------------ upgrade -----
  section "update: pacman -Syu"
  local plen
  plen="$(pacman_log_len)"
  if [ "$MC_AUTO" = "1" ]; then
    as_root pacman -Syu --noconfirm --needed
    rc=$?
  else
    as_root pacman -Syu
    rc=$?
  fi
  if [ $rc -eq 0 ]; then
    ok "pacman -Syu finished"
  else
    err "pacman -Syu exited with code $rc"
    sum_line "**pacman -Syu failed** (exit $rc) — see log.txt"
  fi

  # ---------------------------------------------------------------- post ----
  section "update: post-checks"
  local new_log
  new_log="$(pacman_log_since "$plen")"
  if printf '%s' "$new_log" | grep -qE 'upgraded (linux|linux[0-9]+|linux[0-9]+-[a-z]+)'; then
    warn "kernel package was updated → REBOOT recommended"
    if have dkms; then
      info "DKMS detected — after reboot run: sudo dkms autoinstall"
    fi
    sum_line "**kernel updated** → reboot recommended"
  fi
  if printf '%s' "$new_log" | grep -q 'upgraded openssl\|upgraded glibc\|upgraded systemd'; then
    warn "core library updated (openssl/glibc/systemd) → reboot or restart services recommended"
    sum_line "core libs updated (openssl/glibc/systemd) → restart recommended"
  fi
  # كشف ما إذا كانت إحدى الحزم المُحدَّثة قد كسرت ثنائيات AUR (حالة orthanc)
  local upg_pkgs
  upg_pkgs="$(printf '%s' "$new_log" | grep -oP 'upgraded \K[^ ]+(?= \()' | sort -u || true)"
  if [ -n "$upg_pkgs" ] && printf '%s' "$upg_pkgs" | grep -qE 'jsoncpp|boost|protobuf|icu|openssl'; then
    warn "library upgrades detected (jsoncpp/boost/protobuf/icu/openssl)"
    warn "→ AUR packages linked against them may be broken — run: manjaro-care fix"
    sum_line "lib upgrades: $(printf '%s' "$upg_pkgs" | grep -E 'jsoncpp|boost|protobuf|icu|openssl' | tr '\n' ' ')"
    sum_line "→ run 'manjaro-care fix' to detect broken AUR binaries"
  fi

  local pacnew_list
  pacnew_list="$(find /etc -maxdepth 4 \( -name '*.pacnew' -o -name '*.pacsave' \) 2>/dev/null || true)"
  if [ -n "$pacnew_list" ]; then
    local n_pn
    n_pn="$(printf '%s\n' "$pacnew_list" | wc -l)"
    warn "$n_pn .pacnew/.pacsave file(s) need review:"
    printf '%s\n' "$pacnew_list" | head -15 | sed 's/^/  - /'
    info "review with: sudo pacdiff"
    sum_line ".pacnew files ($n_pn): review with sudo pacdiff"
  else
    ok "no .pacnew files"
  fi

  hr
  if [ $rc -eq 0 ]; then
    ok "update finished successfully"
  fi
  return $rc
}
