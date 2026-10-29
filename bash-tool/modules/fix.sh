#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/fix.sh  — أمر fix
# إصلاحات المشاكل الشائعة في مانجارو:
#   1) القفل اليتيم لقاعدة pacman (من pamac أو انهيار سابق)
#   2) الوحدات الفاشلة (reset-failed يزيل start-limit-hit أيضاً)
#   3) الحزم الناقصة الملفات (إعادة تثبيت)
#   4) المكتبات المفقودة في حزم AUR (حالة Orthanc: jsoncpp/boost/protobuf)
#   5) هوك timeshift-autosnap الذي يجمّد معاملات pacman (مشكلتك في اللوج)
#   6) بيانات اعتماد libvirtd (credential.secret)
#   7) تعارض TLP مع power-profiles-daemon
# =============================================================================

cmd_fix() {
  start_report "fix"
  sum_h2 "Fixes applied"
  if ! require_sudo; then
    err "fix needs sudo — aborting"
    return 1
  fi

  fix_pacman_lock
  fix_failed_units
  fix_broken_packages
  fix_missing_libs
  fix_timeshift
  fix_libvirt
  fix_power_conflict

  hr
  if [ "$MC_FAILURES" -gt 0 ]; then
    warn "fix finished with $MC_FAILURES error(s) and $MC_WARNINGS warning(s)"
  else
    ok "fix finished — $MC_WARNINGS warning(s)"
  fi
  return 0
}

# --------------------------------------------------------------- 1) lock -----
fix_pacman_lock() {
  section "fix 1: pacman database lock"
  if [ ! -e /var/lib/pacman/db.lck ]; then
    ok "no db.lck — nothing to do"
    sum_line "db.lck: none"
    return 0
  fi

  # قيد تشغيل حي؟ لا نلمس القفل إطلاقاً في هذه الحالة
  if pgrep -x pacman >/dev/null 2>&1; then
    err "a pacman process is running right now — refusing to touch the lock"
    sum_line "db.lck: held by live pacman — skipped"
    return 0
  fi

  # pamac يمسك القفل؟ نوقفه مؤقتاً (يعود تلقائياً عند الخروج)
  if systemctl is-active pamac-daemon.service >/dev/null 2>&1; then
    warn "pamac-daemon is running (it periodically grabs the pacman lock)"
    if ask_yes "stop pamac-daemon so the lock can be cleared?" "y"; then
      as_root systemctl stop pamac-daemon.service && MC_PAMAC_STOPPED=1 && ok "pamac-daemon stopped"
    fi
  fi

  # تحقق نهائي: هل من عملية تمسك القفل فعلاً؟
  local holder=""
  if have fuser; then
    holder="$(as_root fuser /var/lib/pacman/db.lck 2>/dev/null | tr -dc '0-9 ' | xargs || true)"
  fi
  if [ -n "$holder" ]; then
    local pname
    for pid in $holder; do
      pname="$(ps -o comm= -p "$pid" 2>/dev/null || echo '?')"
      err "lock is held by PID $pid ($pname) — not a stale lock, skipping removal"
    done
    sum_line "db.lck: held by $holder — skipped"
    return 0
  fi

  info "no live process holds the lock → stale lock"
  if ask_yes "remove stale /var/lib/pacman/db.lck?" "y"; then
    if as_root rm -f /var/lib/pacman/db.lck; then
      ok "stale lock removed"
      sum_line "db.lck: stale lock **removed**"
    else
      err "failed to remove db.lck"
    fi
  else
    sum_line "db.lck: kept (user declined)"
  fi
  return 0
}

# -------------------------------------------------------- 2) failed units ----
fix_failed_units() {
  section "fix 2: failed systemd units (incl. start-limit-hit)"
  local failed u
  failed="$(systemctl --failed --no-legend --plain 2>/dev/null | awk 'NF' | awk '{print $1}' || true)"
  if [ -z "$failed" ]; then
    ok "no failed units"
    sum_line "failed units: none"
    return 0
  fi
  warn "failed units found:"
  printf '%s\n' "$failed" | sed 's/^/  - /'
  for u in $failed; do
    # reset-failed يصفّر أيضاً عدّاد start-limit-hit (حالة orthanc.service لديك)
    if ask_yes "reset failed state of '$u' (clears start-limit counter)?" "y"; then
      if as_root systemctl reset-failed "$u"; then
        ok "reset-failed: $u"
        sum_line "reset-failed: \`$u\`"
      else
        err "could not reset: $u"
      fi
      if ask_yes "try to start '$u' now?" "n"; then
        if as_root systemctl start "$u"; then
          ok "started: $u"
        else
          warn "still failing: $u — check: journalctl -u $u -n 30"
          sum_line "start failed again: \`$u\`"
        fi
      fi
    fi
  done
  return 0
}

# ------------------------------------------------- 3) missing file checks ----
fix_broken_packages() {
  section "fix 3: packages with missing files"
  info "scanning (pacman -Qk)..."
  local bad
  bad="$(pacman -Qk 2>/dev/null | grep 'missing files' | grep -v ': 0 missing files' | awk -F: '{print $1}' | awk '{print $1}' || true)"
  if [ -z "$bad" ]; then
    ok "all packages complete"
    sum_line "missing files: none"
    return 0
  fi
  warn "packages with missing files: $(printf '%s' "$bad" | tr '\n' ' ')"
  sum_line "reinstalled (missing files): $bad"
  if ask_yes "reinstall the listed packages (pacman -S --needed)?" "y"; then
    # shellcheck disable=SC2086
    if as_root pacman -S --needed --noconfirm $bad; then
      ok "reinstalled: $bad"
    else
      err "reinstall failed for: $bad"
    fi
  fi
  return 0
}

# ------------------------------------------------------ 4) broken libs -------
fix_missing_libs() {
  section "fix 4: broken shared libraries in foreign (AUR) packages"
  info "scanning foreign package binaries with ldd..."
  scan_foreign_broken_bins
  if [ -z "$MC_SCAN_RESULTS" ]; then
    ok "no broken binaries detected"
    sum_line "broken libs: none"
    return 0
  fi

  local affected
  affected="$(printf '%s' "$MC_SCAN_RESULTS" | awk -F'|' '{print $1}' | sort -u | tr '\n' ' ' | xargs)"
  warn "binaries with missing libraries:"
  printf '%s' "$MC_SCAN_RESULTS" | awk -F'|' '{printf "  %s → %s (%s)\n", $1, $2, $3}'
  sum_line "**broken libs** in: $affected"
  printf '%s' "$MC_SCAN_RESULTS" | awk -F'|' '{printf "- `%s` → %s (%s)\n", $1, $2, $3}' >> "$MC_SUMMARY"

  if have checkrebuild; then
    info "checkrebuild report:"
    capture checkrebuild || true
  fi

  # إعادة البناء مهمة طويلة → تفاعلية فقط، ولا تُنفذ في --auto
  if [ "$MC_AUTO" = "1" ]; then
    info "auto mode: rebuilding skipped. Run manually, e.g.: paru -S --rebuild $affected"
    return 0
  fi
  local helper=""
  for h in paru yay pikaur trizen; do
    if have "$h"; then helper="$h"; break; fi
  done
  if [ -n "$helper" ]; then
    if ask_yes "rebuild the affected packages with '$helper' now? (can take a long time)" "n"; then
      # shellcheck disable=SC2086
      if capture "$helper" -S --rebuild --needed $affected; then
        ok "rebuild finished"
        sum_line "rebuilt via $helper: $affected"
      else
        err "rebuild failed via $helper"
      fi
    fi
  else
    info "no AUR helper found. Rebuild manually, e.g.: makepkg in each PKGBUILD dir"
  fi
  return 0
}

# --------------------------------------------------------- 5) timeshift ------
fix_timeshift() {
  section "fix 5: timeshift-autosnap (pacman hangs on 'Select backup device')"
  local hook="/usr/share/libalpm/hooks/timeshift-autosnap.hook"
  if [ ! -f "$hook" ]; then
    ok "autosnap hook not installed — nothing to do"
    sum_line "timeshift autosnap: not installed"
    return 0
  fi
  info "autosnap hook is installed"

  local ts_out ts_rc
  ts_out="$(sudo timeshift --list --scripted 2>&1 </dev/null)"; ts_rc=$?
  if [ $ts_rc -eq 0 ] && ! printf '%s' "$ts_out" | grep -q 'Select backup device'; then
    ok "timeshift scripted mode works — autosnap is safe"
    sum_line "timeshift autosnap: OK"
    return 0
  fi

  warn "timeshift cannot pick a backup device non-interactively (your btrfs case)"
  warn "→ pacman transactions will hang: 'Enter device name or number' x3 then abort"

  local conf="/etc/timeshift-autosnap.conf"
  if [ -f "$conf" ] && grep -Eq '"backup"[[:space:]]*:[[:space:]]*false' "$conf"; then
    ok "autosnap already disabled in $conf"
    sum_line "timeshift autosnap: already disabled"
    return 0
  fi

  if ask_yes "disable autosnap snapshots permanently (write backup:false to $conf)? recommended" "y"; then
    if [ -f "$conf" ]; then
      as_root cp -a "$conf" "${conf}.bak.$(date +%Y%m%d%H%M%S)" && ok "backup of old config saved"
    fi
    printf '{\n  "backup" : false,\n  "snapshots" : true,\n  "maxSnapshots" : 3,\n  "updateGrub" : false\n}\n' | as_root tee "$conf" >/dev/null
    ok "autosnap disabled (backup: false). Take snapshots manually: sudo timeshift --create --comments 'manual'"
    sum_line "timeshift autosnap: **disabled** (backup:false written to $conf)"
  else
    warn "autosnap left enabled — use 'manjaro-care update' which auto-guards the hook during transactions"
    sum_line "timeshift autosnap: left enabled (guard mode available in update)"
  fi
  return 0
}

# ----------------------------------------------------------- 6) libvirt ------
fix_libvirt() {
  section "fix 6: libvirtd credentials (status=243/CREDENTIALS)"
  local lv
  lv="$(systemctl is-active libvirtd.service 2>/dev/null || true)"
  if [ "$lv" = "active" ]; then
    ok "libvirtd running"
    sum_line "libvirtd: running"
    return 0
  fi
  if ! have systemd-creds; then
    info "libvirtd not active; systemd-creds unavailable — skipping"
    return 0
  fi
  local secret_ok=1
  as_root test -f /var/lib/systemd/credential.secret 2>/dev/null && secret_ok=0
  if [ "$secret_ok" = "1" ]; then
    warn "libvirtd is '$lv' and /var/lib/systemd/credential.secret is missing"
    if ask_yes "run 'systemd-creds setup' and start libvirtd?" "y"; then
      if as_root systemd-creds setup; then
        ok "credential.secret created"
        sum_line "libvirtd: systemd-creds setup **done**"
      else
        err "systemd-creds setup failed"
      fi
      as_root systemctl reset-failed libvirtd.service 2>/dev/null || true
      if as_root systemctl start libvirtd.service; then
        ok "libvirtd started"
      else
        warn "libvirtd still failing — check: journalctl -u libvirtd -n 30"
        sum_line "libvirtd: start failed after credential setup"
      fi
    fi
  else
    info "credential.secret exists — trying plain start"
    as_root systemctl reset-failed libvirtd.service 2>/dev/null || true
    if as_root systemctl start libvirtd.service; then
      ok "libvirtd started"
      sum_line "libvirtd: **started**"
    else
      warn "libvirtd still not starting"
      sum_line "libvirtd: still failing"
    fi
  fi
  return 0
}

# -------------------------------------------------------------- 7) TLP -------
fix_power_conflict() {
  section "fix 7: TLP vs power-profiles-daemon"
  local tlp ppd
  tlp="$(systemctl is-active tlp.service 2>/dev/null || true)"
  ppd="$(systemctl is-active power-profiles-daemon.service 2>/dev/null || true)"
  if [ "$tlp" != "active" ]; then
    info "TLP is not active — nothing to do"
    sum_line "power: TLP not active"
    return 0
  fi
  if [ "$ppd" != "active" ] && ! systemctl is-enabled power-profiles-daemon.service >/dev/null 2>&1; then
    ok "no conflict: TLP active, power-profiles-daemon inactive"
    sum_line "power: no conflict"
    return 0
  fi
  warn "conflict: TLP active AND power-profiles-daemon active/enabled"
  if ask_yes "mask power-profiles-daemon and restart TLP?" "y"; then
    if as_root systemctl mask --now power-profiles-daemon.service; then
      ok "power-profiles-daemon masked"
      sum_line "power: power-profiles-daemon **masked**"
    else
      err "could not mask power-profiles-daemon"
    fi
    if as_root systemctl restart tlp.service; then
      ok "TLP restarted"
      sum_line "power: TLP restarted"
    fi
  fi
  return 0
}
