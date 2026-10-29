#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/health.sh  — أمر doctor
# فحص صحي شامل للنظام للقراءة فقط: أقراص، خدمات فاشلة، سلامة حزم pacman،
# مكتبات مفقودة، كاش، timeshift، تعارض الطاقة، libvirtd، الشبكة.
# =============================================================================

cmd_doctor() {
  start_report "doctor"

  section "1/11 system info"
  sum_h2 "System"
  local pretty
  pretty="$(grep -E '^PRETTY_NAME' /etc/os-release 2>/dev/null | cut -d'"' -f2)"
  info "OS      : ${pretty:-unknown} $([ "$(is_manjaro)" ] || echo '  (not Manjaro!)')"
  info "kernel  : $(uname -r)"
  info "uptime  : $(uptime -p 2>/dev/null | sed 's/up //' || echo '?')"
  sum_line "OS: ${pretty:-unknown}, kernel $(uname -r)"

  section "2/11 disk usage"
  sum_h2 "Disks"
  capture df -h -x tmpfs -x devtmpfs -x efivarfs -x iso9660 -x overlay
  local dsk
  dsk="$(df -BM --output=source,pcent,target -x tmpfs -x devtmpfs -x efivarfs -x iso9660 -x overlay 2>/dev/null | awk 'NR>1 && ($2+0) >= 85')"
  if [ -n "$dsk" ]; then
    while IFS= read -r d; do warn "disk usage >= 85%: $d"; sum_line "**LOW SPACE**: $d"; done <<< "$dsk"
  else
    ok "no filesystem above 85%"
    sum_line "no filesystem above 85%"
  fi

  section "3/11 failed systemd units"
  sum_h2 "Failed units"
  local failed
  failed="$(systemctl --failed --no-legend --plain 2>/dev/null | awk 'NF' || true)"
  if [ -n "$failed" ]; then
    warn "there are failed units:"
    printf '%s\n' "$failed"
    while IFS= read -r u; do
      [ -n "$u" ] && sum_line "failed unit: \`$(printf '%s' "$u" | awk '{print $1}')\`"
    done <<< "$failed"
  else
    ok "no failed units"
    sum_line "none"
  fi

  section "4/11 journal errors (current boot, last 60)"
  sum_h2 "Journal errors (current boot)"
  if sudo -n true 2>/dev/null || [ "$(id -u)" = "0" ]; then
    capture sudo journalctl -p 3 -b --no-pager -n 60 || true
  else
    info "(running without sudo → user-visible journal only)"
    capture journalctl -p 3 -b --no-pager -n 60 || true
  fi

  section "5/11 pacman health"
  sum_h2 "Pacman"
  if [ -e /var/lib/pacman/db.lck ]; then
    warn "pacman db.lck exists (possible stale lock) → run: manjaro-care fix"
    sum_line "**db.lck exists** — stale lock likely (run fix)"
  else
    ok "no pacman database lock"
    sum_line "no db lock"
  fi

  local orphans
  orphans="$(pacman -Qdtq 2>/dev/null || true)"
  if [ -n "$orphans" ]; then
    local n_orph; n_orph="$(printf '%s\n' "$orphans" | wc -l)"
    warn "$n_orph orphan package(s)"
    sum_line "orphans ($n_orph): ${orphans//$'\n'/, }"
    printf '%s\n' "$orphans" | head -20 | sed 's/^/  - /'
  else
    ok "no orphan packages"
    sum_line "orphans: none"
  fi

  local foreign
  foreign="$(pacman -Qm 2>/dev/null || true)"
  local n_for; n_for="$(printf '%s' "$foreign" | grep -c . || true)"
  info "foreign/AUR packages: $n_for"
  sum_line "foreign/AUR packages: $n_for"
  if [ "$n_for" -gt 0 ]; then
    printf '%s\n' "$foreign" | head -15 | sed 's/^/  - /'
  fi

  info "checking package files integrity (pacman -Qk — may take a minute)..."
  local bad_files
  bad_files="$(pacman -Qk 2>/dev/null | grep 'missing files' | grep -v ': 0 missing files' | head -30 || true)"
  if [ -n "$bad_files" ]; then
    warn "packages with missing files:"
    printf '%s\n' "$bad_files"
    sum_line "**missing files**: $(printf '%s' "$bad_files" | awk -F: '{print $1}' | awk '{printf "%s ", $1}')"
  else
    ok "all packages complete (pacman -Qk)"
    sum_line "package files: complete"
  fi

  section "6/11 broken shared libraries (foreign packages)"
  sum_h2 "Broken shared libraries"
  scan_foreign_broken_bins
  if [ -n "$MC_SCAN_RESULTS" ]; then
    warn "foreign binaries with missing libraries (typical after lib upgrades):"
    printf '%s' "$MC_SCAN_RESULTS" | awk -F'|' '{printf "  %s → %s (%s)\n", $1, $2, $3}'
    printf '%s' "$MC_SCAN_RESULTS" | awk -F'|' '{print $1}' | sort -u | tr '\n' ' ' | \
      { read -r pkgs; warn "affected: $pkgs"; sum_line "**broken libs** in: $pkgs"; }
    if have checkrebuild; then
      info "checkrebuild says:"
      capture checkrebuild || true
    else
      info "tip: install rebuild-detector (sudo pacman -S rebuild-detector) then run checkrebuild"
    fi
  else
    ok "no broken binaries detected in foreign packages"
    sum_line "broken libs: none detected"
  fi

  section "7/11 caches"
  sum_h2 "Caches"
  local s
  if [ -d /var/cache/pacman/pkg ]; then
    s="$(du -sh /var/cache/pacman/pkg 2>/dev/null | cut -f1)"; info "pacman cache : ${s:-?}"; sum_line "pacman cache: ${s:-?}"
  fi
  if [ -d "$HOME/.cache/pamac" ]; then
    s="$(du -sh "$HOME/.cache/pamac" 2>/dev/null | cut -f1)"; info "pamac cache  : ${s:-?}"; sum_line "pamac cache: ${s:-?}"
  fi
  s="$(journalctl --disk-usage 2>/dev/null | head -1)"; [ -n "$s" ] && { info "journal      : $s"; sum_line "$s"; }
  if sudo -n true 2>/dev/null && [ -d /var/lib/systemd/coredump ]; then
    s="$(sudo du -sh /var/lib/systemd/coredump 2>/dev/null | cut -f1)"; info "coredumps    : ${s:-0}"; sum_line "coredumps: ${s:-0}"
  fi

  section "8/11 timeshift"
  sum_h2 "Timeshift"
  if have timeshift; then
    local hook="/usr/share/libalpm/hooks/timeshift-autosnap.hook"
    if [ -f "$hook" ]; then
      info "timeshift-autosnap hook is installed"
      sum_line "autosnap hook: installed"
    fi
    if sudo -n true 2>/dev/null || [ "$(id -u)" = "0" ]; then
      local ts_out ts_rc
      ts_out="$(sudo timeshift --list --scripted 2>&1 </dev/null)"; ts_rc=$?
      if [ $ts_rc -eq 0 ] && ! printf '%s' "$ts_out" | grep -q 'Select backup device'; then
        ok "timeshift configuration is fine (scripted mode works)"
        sum_line "timeshift: OK ($(printf '%s' "$ts_out" | grep -c '^[A-Z]>') snapshot(s) listed)"
      else
        warn "timeshift CANNOT determine backup device non-interactively"
        warn "→ every pacman transaction with autosnap will HANG (your orthanc install hit this)"
        sum_line "**timeshift broken in scripted mode** → pacman hangs on autosnap; run: manjaro-care fix"
      fi
    else
      info "sudo not cached — skipping timeshift scripted check"
    fi
    if [ -f /etc/timeshift-autosnap.conf ]; then
      capture cat /etc/timeshift-autosnap.conf
    fi
  else
    ok "timeshift not installed"
    sum_line "timeshift: not installed"
  fi

  section "9/11 pamac & power"
  sum_h2 "Pamac & power"
  local st
  st="$(systemctl is-active pamac-daemon.service 2>/dev/null || echo inactive)"
  info "pamac-daemon: $st"
  if pgrep -f pamac-tray >/dev/null 2>&1; then info "pamac tray applet: running"; fi
  sum_line "pamac-daemon: $st"

  local tlp ppd
  tlp="$(systemctl is-active tlp.service 2>/dev/null || true)"
  ppd="$(systemctl is-active power-profiles-daemon.service 2>/dev/null || true)"
  info "tlp=$tlp power-profiles-daemon=$ppd"
  if [ "$tlp" = "active" ] && [ "$ppd" = "active" ]; then
    warn "TLP and power-profiles-daemon are BOTH active → power settings conflict"
    sum_line "**power conflict**: TLP + power-profiles-daemon both active (run: manjaro-care fix)"
  else
    ok "no power-management conflict"
    sum_line "power: no conflict"
  fi

  section "10/11 libvirtd"
  sum_h2 "libvirtd"
  local lv
  lv="$(systemctl is-active libvirtd.service 2>/dev/null || true)"
  if [ -z "$lv" ]; then
    info "libvirtd: not installed / systemd unavailable — skipping"
    sum_line "libvirtd: not present"
    return 0
  fi
  info "libvirtd: $lv"
  if [ "$lv" != "active" ]; then
    if [ ! -f /var/lib/systemd/credential.secret ]; then
      if sudo -n true 2>/dev/null; then :; fi
      local secret_ok=0
      sudo -n test -f /var/lib/systemd/credential.secret 2>/dev/null && secret_ok=1
      if [ "$secret_ok" = "0" ]; then
        warn "libvirtd not running and /var/lib/systemd/credential.secret missing"
        warn "→ known issue: status=243/CREDENTIALS — fix available: manjaro-care fix"
        sum_line "**libvirtd**: stopped + credential.secret missing (run: manjaro-care fix)"
      fi
    else
      info "libvirtd stopped but credentials exist (maybe simply disabled)"
      sum_line "libvirtd: stopped (credentials present)"
    fi
  else
    ok "libvirtd running"
    sum_line "libvirtd: running"
  fi

  section "11/11 network & updates"
  sum_h2 "Network & updates"
  local code
  code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' https://github.com 2>/dev/null || echo 000)"
  if [ "$code" = "200" ] || [ "$code" = "301" ]; then
    ok "github.com reachable (HTTP $code)"
    sum_line "github.com: reachable"
  else
    err "github.com NOT reachable (HTTP $code) → report sync will fail"
    sum_line "**github.com unreachable** (HTTP $code)"
  fi
  if have checkupdates; then
    local n_up
    n_up="$(checkupdates 2>/dev/null | wc -l)"
    info "available updates: $n_up"
    sum_line "available updates: $n_up"
  else
    info "checkupdates not found (install pacman-contrib for update counting)"
  fi
  local pacnew
  pacnew="$(find /etc -maxdepth 4 \( -name '*.pacnew' -o -name '*.pacsave' \) 2>/dev/null | wc -l)"
  info ".pacnew/.pacnew files under /etc (user-visible subset): $pacnew"
  if [ "$pacnew" -gt 0 ]; then
    warn "run 'sudo pacdiff' to review merged config differences"
    sum_line ".pacnew files to review: $pacnew (sudo pacdiff)"
  fi

  hr
  if [ "$MC_WARNINGS" -gt 0 ]; then
    warn "doctor finished with $MC_WARNINGS warning(s) — see summary above"
  else
    ok "doctor finished clean — no warnings"
  fi
  return 0
}
