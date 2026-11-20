#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/fix.sh  — أمر fix
# إصلاحات المشاكل الشائعة في مانجارو:
#   1) القفل اليتيم لقاعدة pacman (من pamac أو انهيار سابق)
#   2) الوحدات الفاشلة (reset-failed يزيل start-limit-hit أيضاً)
#   3) الحزم الناقصة الملفات (إعادة تثبيت)
#   4) المكتبات المفقودة في حزم AUR (حالة Orthanc: jsoncpp/boost/protobuf)
#   5) هوك timeshift-autosnap الذي يجمّد معاملات pacman
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
      # shellcheck disable=SC2034  # تُقرأ في lib/common.sh (التنظيف النهائي)
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
  local bad foreign p repo_bad="" foreign_bad=""
  # pacman يكتب "1 missing file" بالمفرد، فلا نعتمد على "files" فقط
  bad="$(pacman -Qk 2>/dev/null | grep -E ', [1-9][0-9]* missing files?$' | awk -F: '{print $1}' | awk '{print $1}' || true)"
  if [ -z "$bad" ]; then
    ok "all packages complete"
    sum_line "missing files: none"
    return 0
  fi
  foreign="$(pacman -Qmq 2>/dev/null || true)"
  for p in $bad; do
    if printf '%s\n' "$foreign" | grep -qx -- "$p"; then foreign_bad="$foreign_bad $p"; else repo_bad="$repo_bad $p"; fi
  done
  repo_bad="${repo_bad# }"; foreign_bad="${foreign_bad# }"
  warn "packages with missing files — repo: ${repo_bad:-none} | AUR/foreign: ${foreign_bad:-none}"
  sum_line "missing files — repo: ${repo_bad:-none}; foreign (rebuild manually): ${foreign_bad:-none}"
  [ -n "$foreign_bad" ] && info "foreign packages are not in the repos; rebuild them (e.g. paru -S --rebuild $foreign_bad)"
  if [ -n "$repo_bad" ] && ask_risky "reinstall repo packages: $repo_bad ?" "y"; then
    # بدون --needed: وإلا يتخطى pacman الحزم المثبّتة والمحدّثة ولا يعيد تثبيتها
    # shellcheck disable=SC2086
    if as_root pacman -S --noconfirm $repo_bad; then
      ok "reinstalled: $repo_bad"
      sum_line "reinstalled: $repo_bad"
    else
      err "reinstall failed for: $repo_bad"
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
  local hook
  if ! hook="$(find_ts_hook)"; then
    ok "autosnap hook not installed — nothing to do"
    sum_line "timeshift autosnap: not installed"
    return 0
  fi
  info "autosnap hook: $hook"

  local ts_out ts_rc
  ts_out="$(root_sh 'timeshift --list --scripted 2>&1' </dev/null)"; ts_rc=$?
  if [ $ts_rc -eq 0 ] && ! printf '%s' "$ts_out" | grep -q 'Select backup device'; then
    ok "timeshift scripted mode works — autosnap is safe"
    sum_line "timeshift autosnap: OK"
    return 0
  fi

  warn "timeshift cannot pick a backup device non-interactively (btrfs case)"
  warn "→ pacman runs hooks without a keyboard: 'Enter device name or number' x3 then abort"

  local conf="/etc/timeshift-autosnap.conf"
  if [ -f "$conf" ] && grep -Eq '^[[:space:]]*skipAutosnap[[:space:]]*=[[:space:]]*true' "$conf"; then
    ok "autosnap already skipped in $conf"
    sum_line "timeshift autosnap: already disabled"
    return 0
  fi
  if [ -f "$conf" ] && grep -Eq '^[[:space:]]*skipAutosnap[[:space:]]*=' "$conf"; then
    if ask_risky "set skipAutosnap=true in $conf (backup of the file is kept)?" "y"; then
      as_root cp -a "$conf" "${conf}.bak.$(date +%Y%m%d%H%M%S)" && ok "backup of old config saved"
      as_root sed -i -E 's/^[[:space:]]*skipAutosnap[[:space:]]*=.*/skipAutosnap=true/' "$conf"
      ok "autosnap skipped. Take snapshots manually: sudo timeshift --create --comments 'manual'"
      sum_line "timeshift autosnap: **skipAutosnap=true** written to $conf"
    else
      sum_line "timeshift autosnap: left enabled (user declined)"
    fi
  else
    warn "format of $conf not recognized (no skipAutosnap key) — NOT modifying it"
    info "options: (a) 'manjaro-care-cli update' guards the hook per transaction; (b) configure Timeshift's btrfs device so 'sudo timeshift --list --scripted' works"
    sum_line "timeshift autosnap: broken in scripted mode; config not modified (unknown format) — use update guard"
  fi
  return 0
}

# ----------------------------------------------------------- 6) libvirt ------
LV_KEY="/var/lib/libvirt/secrets/secrets-encryption-key"

lv_key_len() {
  # يطبع عدد بايتات مفتاح libvirt بعد فك تشفيره (المتوقع 32؛ 0 = فشل أو غير موجود)
  root_sh 'test -f "$1" && systemd-creds decrypt "$1" - 2>/dev/null | wc -c || echo 0' _ "$LV_KEY" | tr -dc '0-9'
}

fix_libvirt() {
  section "fix 6: libvirtd credentials (status=243/CREDENTIALS)"
  if ! systemctl cat libvirtd.service >/dev/null 2>&1; then
    info "libvirtd not installed — skipping"; return 0
  fi
  if [ "$(systemctl is-active libvirtd.service 2>/dev/null || true)" = "active" ]; then
    ok "libvirtd running"; sum_line "libvirtd: running"; return 0
  fi
  if ! have systemd-creds; then
    info "libvirtd not active; systemd-creds unavailable — skipping"; return 0
  fi

  local n; n="$(lv_key_len)"
  if [ "${n:-0}" = "32" ]; then
    info "libvirt key decrypts fine — trying plain start"
    as_root systemctl reset-failed libvirtd.service 2>/dev/null || true
    if as_root systemctl start libvirtd.service; then
      ok "libvirtd started"; sum_line "libvirtd: **started**"
    else
      warn "libvirtd still failing — see: journalctl -u libvirtd -n 30"; sum_line "libvirtd: still failing (key OK)"
    fi
    return 0
  fi

  warn "libvirt secrets key is missing or cannot be decrypted (host key lost?)"
  # لا نعيد التوليد إن وُجدت أسرار أخرى مشفّرة بالمفتاح القديم: ستصبح غير قابلة للقراءة
  local others
  others="$(root_sh 'find /var/lib/libvirt/secrets /etc/libvirt/secrets -mindepth 1 -maxdepth 1 ! -name "secrets-encryption-key*" 2>/dev/null' || true)"
  if [ -n "$others" ]; then
    err "other libvirt secrets exist; regenerating the key would orphan them — handle manually:"
    printf '%s\n' "$others" | sed 's/^/  - /'
    sum_line "**libvirtd**: key unusable but other secrets exist — manual action needed"
    return 0
  fi

  if ! ask_risky "regenerate the key (backup to /root first; no other secrets are stored)?" "y"; then
    sum_line "libvirtd: regeneration declined"; return 0
  fi
  local ts; ts="$(date +%Y%m%d%H%M%S)"
  as_root cp -a /var/lib/libvirt/secrets "/root/libvirt-secrets.bak-$ts" || { err "backup failed — aborting"; return 0; }
  ok "backup: /root/libvirt-secrets.bak-$ts"
  if ! root_sh 'test -f /var/lib/systemd/credential.secret'; then
    as_root systemd-creds setup || { err "systemd-creds setup failed"; return 0; }
    ok "host credential key created"
  fi
  root_sh 'test -f "$1" && mv "$1" "$1.old-$2"; true' _ "$LV_KEY" "$ts"
  # الوحدة تتخطى نفسها إن بقي ملف المفتاح (ConditionPathExists=!)، لذلك نقلناه أولاً
  as_root systemctl start virt-secret-init-encryption.service || { err "could not generate new key"; return 0; }
  n="$(lv_key_len)"
  if [ "${n:-0}" != "32" ]; then
    err "new key does not decrypt to 32 bytes (got ${n:-0}) — not starting libvirtd"
    sum_line "libvirtd: new key verification failed"; return 0
  fi
  ok "new key verified (32 bytes)"
  as_root systemctl reset-failed libvirtd.service libvirtd.socket libvirtd-ro.socket libvirtd-admin.socket 2>/dev/null || true
  if as_root systemctl start libvirtd.service; then
    ok "libvirtd started"
    sum_line "libvirtd: key regenerated, **started** (old key: $LV_KEY.old-$ts; backup /root/libvirt-secrets.bak-$ts)"
  else
    warn "libvirtd still failing — see: journalctl -u libvirtd -n 30"
    sum_line "libvirtd: key regenerated but start failed"
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
  if ask_risky "mask power-profiles-daemon and restart TLP? (removes the Plasma power-profile switch)" "y"; then
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
