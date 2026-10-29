#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/clean.sh  — أمر clean
# تنظيف آمن: journal، كاش pacman (مع الاحتفاظ بآخر نسختين)، كاش pamac،
# الحزم اليتيمة، ملفات coredump الكبيرة، وملفات /tmp عبر systemd-tmpfiles.
# =============================================================================

cmd_clean() {
  start_report "clean"
  if ! require_sudo; then
    err "clean needs sudo — aborting"
    return 1
  fi

  local before after freed
  before="$(free_gb_root)"
  info "free space on / before: ${before}G"
  sum_h2 "Cleanup"
  sum_line "free before: ${before}G"

  # 1) journal ---------------------------------------------------------------
  section "clean 1: journal vacuum (max 200M / 30 days)"
  if as_root journalctl --vacuum-size=200M --vacuum-time=30d; then
    ok "journal trimmed"
    sum_line "journal: vacuumed to 200M / 30d"
  else
    warn "journal vacuum failed"
  fi

  # 2) pacman cache ----------------------------------------------------------
  section "clean 2: pacman package cache"
  if have paccache; then
    as_root paccache -rk2 && ok "kept last 2 versions of installed packages"
    as_root paccache -ruk0 && ok "removed caches of uninstalled packages"
    sum_line "pacman cache: paccache -rk2 + -ruk0"
  else
    warn "paccache not found (pacman-contrib)"
    if ask_yes "install pacman-contrib now?" "y"; then
      if as_root pacman -S --needed --noconfirm pacman-contrib; then
        as_root paccache -rk2 && as_root paccache -ruk0
        ok "pacman-contrib installed and cache cleaned"
        sum_line "pacman cache: cleaned (pacman-contrib installed)"
      else
        err "could not install pacman-contrib"
      fi
    else
      sum_line "pacman cache: skipped (paccache missing)"
    fi
  fi

  # 3) pamac cache -----------------------------------------------------------
  section "clean 3: pamac build cache"
  if [ -d "$HOME/.cache/pamac" ]; then
    local ps_size
    ps_size="$(du -sh "$HOME/.cache/pamac" 2>/dev/null | cut -f1)"
    if ask_yes "clear pamac cache (~/.cache/pamac = ${ps_size:-?})?" "y"; then
      rm -rf "$HOME/.cache/pamac/"* 2>/dev/null || true
      ok "pamac cache cleared"
      sum_line "pamac cache: cleared (${ps_size:-?})"
    fi
  else
    ok "no pamac cache"
    sum_line "pamac cache: none"
  fi
  if [ -d /var/cache/pamac ]; then
    if ask_yes "clear system pamac cache (/var/cache/pamac)?" "y"; then
      as_root find /var/cache/pamac -mindepth 1 -maxdepth 2 -type d -exec rm -rf {} + 2>/dev/null || true
      ok "system pamac cache cleared"
      sum_line "pamac system cache: cleared"
    fi
  fi

  # 4) orphans ---------------------------------------------------------------
  section "clean 4: orphan packages"
  local orphans n_orph
  orphans="$(pacman -Qdtq 2>/dev/null || true)"
  if [ -z "$orphans" ]; then
    ok "no orphan packages"
    sum_line "orphans: none"
  else
    n_orph="$(printf '%s\n' "$orphans" | wc -l)"
    warn "$n_orph orphan(s) found:"
    printf '%s\n' "$orphans" | sed 's/^/  - /'
    if ask_yes "remove all $n_orph orphan package(s) (pacman -Rns)?" "y"; then
      # shellcheck disable=SC2086
      if as_root pacman -Rns --noconfirm $orphans; then
        ok "orphans removed"
        sum_line "orphans: **removed** ($n_orph)"
      else
        err "orphan removal failed (some may be needed as dependencies)"
      fi
    else
      sum_line "orphans: kept by user"
    fi
  fi

  # 5) coredumps -------------------------------------------------------------
  section "clean 5: systemd coredumps (anydesk/plasmashell cases)"
  if [ -d /var/lib/systemd/coredump ]; then
    local c_mb
    c_mb="$(as_root du -sm /var/lib/systemd/coredump 2>/dev/null | awk '{print $1}')"
    c_mb="${c_mb:-0}"
    if [ "$c_mb" -gt 100 ]; then
      warn "coredumps occupy ${c_mb}MB (>100MB)"
      if ask_yes "delete coredumps older than 7 days?" "y"; then
        as_root find /var/lib/systemd/coredump -type f -mtime +7 -delete 2>/dev/null || true
        ok "old coredumps deleted"
        sum_line "coredumps: cleaned (${c_mb}MB before)"
      fi
    else
      ok "coredumps small (${c_mb}MB) — left as is"
      sum_line "coredumps: ${c_mb}MB (small)"
    fi
  else
    ok "no coredump storage"
    sum_line "coredumps: none"
  fi

  # 6) /tmp ------------------------------------------------------------------
  section "clean 6: systemd-tmpfiles"
  if as_root systemd-tmpfiles --clean; then
    ok "systemd-tmpfiles cleanup done"
    sum_line "tmp: systemd-tmpfiles --clean"
  fi

  # result -------------------------------------------------------------------
  after="$(free_gb_root)"
  freed=$(( after - before ))
  hr
  if [ "$freed" -gt 0 ]; then
    ok "freed approximately ${freed}G on /"
    sum_line "**freed: ~${freed}G** (after: ${after}G)"
  else
    info "finished (free after: ${after}G)"
    sum_line "free after: ${after}G"
  fi
  return 0
}
