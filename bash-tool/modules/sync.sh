#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/sync.sh  — أمر sync
# التقارير تُحفظ محلياً في ~/.local/share/manjaro-care-cli/reports (مستودع git
# مستقل عن كود الأداة). الرفع اختياري، ويتم فقط إلى مستودع GitHub **خاص**:
#   - MC_PUSH=1 في الإعدادات لرفع تلقائي بعد كل تشغيل، أو الأمر sync صراحةً.
#   - يُتحقق عبر API أن المستودع private وإلا يُرفض الرفع.
#   - التوكن عبر GIT_ASKPASS (لا يظهر في ps ولا في .git/config).
# =============================================================================

rgit() { git -C "$MC_REPORTS_DIR" "$@"; }

ensure_reports_repo() {
  mkdir -p "$MC_REPORTS_DIR"
  if [ ! -d "$MC_REPORTS_DIR/.git" ]; then
    git -C "$MC_REPORTS_DIR" init -q -b "$MC_GH_BRANCH" 2>/dev/null \
      || { git -C "$MC_REPORTS_DIR" init -q && rgit checkout -q -b "$MC_GH_BRANCH"; }
  fi
  rgit config user.name  >/dev/null 2>&1 || rgit config user.name  "$MC_GH_USER"
  rgit config user.email >/dev/null 2>&1 || rgit config user.email "${MC_GH_USER}@users.noreply.github.com"
  if rgit remote get-url origin >/dev/null 2>&1; then
    rgit remote set-url origin "$(gh_clean_url)"
  else
    rgit remote add origin "$(gh_clean_url)"
  fi
}

prune_old_reports() {
  local total del keep="$MC_KEEP_REPORTS"
  [ -d "$MC_REPORTS_DIR" ] || return 0
  total="$(find "$MC_REPORTS_DIR" -mindepth 2 -maxdepth 2 -type d -not -path '*/.git/*' 2>/dev/null | wc -l)"
  [ "$total" -le "$keep" ] && return 0
  del=$(( total - keep ))
  find "$MC_REPORTS_DIR" -mindepth 2 -maxdepth 2 -type d -not -path '*/.git/*' -printf '%T@ %p\n' 2>/dev/null \
    | sort -n | head -n "$del" | cut -d' ' -f2- \
    | while IFS= read -r d; do rm -rf -- "$d"; done
  info "pruned $del old report dir(s) (keeping last $keep)"
}

commit_reports() {
  ensure_reports_repo
  prune_old_reports
  rgit add -A
  if rgit diff --cached --quiet; then return 1; fi
  rgit commit -q -m "care: ${MC_TASK} $(date '+%F %H:%M')" >/dev/null 2>&1
}

sync_push() {
  # $1 = auto (بعد كل تشغيل: يحترم MC_PUSH) | force (أمر sync الصريح)
  local mode="${1:-auto}"
  [ -d "$MC_REPORTS_DIR" ] || return 0
  if [ "$MC_NO_PUSH" = "1" ]; then
    info "push disabled (--no-push) — reports kept locally"; return 0
  fi
  if [ "$mode" = "auto" ] && [ "$MC_PUSH" != "1" ]; then
    info "reports kept locally in $MC_REPORTS_DIR (push is off; enable with MC_PUSH=1 or run: manjaro-care-cli sync)"
    return 0
  fi
  if [ -z "$MC_TOKEN" ]; then
    warn "no GitHub token at $MC_TOKEN_FILE → run: manjaro-care-cli config"; return 1
  fi
  if [ "${MC_ALLOW_PUBLIC:-0}" != "1" ] && ! gh_repo_is_private; then
    err "github.com/$MC_GH_USER/$MC_GH_REPO is not a PRIVATE repository (or unreachable) — push refused"
    warn "reports contain system details; create a private repo, or set MC_ALLOW_PUBLIC=1 knowingly"
    return 1
  fi
  commit_reports || { info "nothing new to push"; return 0; }

  gh_askpass_setup || { err "could not prepare credentials helper"; return 1; }
  export GIT_ASKPASS="$MC_ASKPASS" GIT_TERMINAL_PROMPT=0
  capture rgit pull --rebase --autostash origin "$MC_GH_BRANCH" >/dev/null || true
  local rc=0
  if capture rgit push origin "HEAD:$MC_GH_BRANCH"; then
    ok "pushed → github.com/$MC_GH_USER/$MC_GH_REPO ($MC_GH_BRANCH)"
  else
    warn "push failed (offline?) — commits kept locally, will go with next successful sync"
    rc=0
  fi
  unset GIT_ASKPASS GIT_TERMINAL_PROMPT
  rm -f "$MC_ASKPASS"; MC_ASKPASS=""
  return $rc
}

cmd_sync() {
  start_report "sync"
  sum_h2 "Sync"
  sync_push force
  local rc=$?
  [ $rc -eq 0 ] && ok "sync finished"
  return $rc
}
