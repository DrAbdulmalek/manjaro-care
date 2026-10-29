#!/usr/bin/env bash
# =============================================================================
# manjaro-care :: modules/sync.sh  — أمر sync
# رفع التقارير إلى مستودع GitHub (DrAbdulmalek/manjaro-care).
# التوكن يُقرأ من ~/.config/manjaro-care/token (صلاحيات 600) ولا يُخزَّن
# أبداً داخل .git/config، ويُحجب من كل مخرجات السجل.
# =============================================================================

gitc() {
  # كل استدعاءات git تمر من هنا (يحمي من مشكلة dubious ownership عند root)
  git -c safe.directory="$MC_ROOT" "$@"
}

prune_old_reports() {
  # الاحتفاظ بآخر MC_KEEP_REPORTS تقرير فقط
  local total del keep="$MC_KEEP_REPORTS"
  [ -d "$MC_REPORTS_DIR" ] || return 0
  total="$(find "$MC_REPORTS_DIR" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l)"
  [ "$total" -le "$keep" ] && return 0
  del=$(( total - keep ))
  find "$MC_REPORTS_DIR" -mindepth 2 -maxdepth 2 -type d -printf '%T@ %p\n' 2>/dev/null \
    | sort -n | head -n "$del" | cut -d' ' -f2- \
    | while IFS= read -r d; do rm -rf "$d"; done
  info "pruned $del old report dir(s) (keeping last $keep)"
}

sync_push() {
  # $1 = رسالة commit اختيارية
  if [ "$MC_NO_PUSH" = "1" ]; then
    info "push disabled (--no-push) — reports kept locally"
    return 0
  fi
  if [ ! -d "$MC_ROOT/.git" ]; then
    warn "tool is not inside a git clone — reports kept locally in reports/"
    warn "→ run install.sh to link the tool with github.com/$MC_GH_USER/$MC_GH_REPO"
    return 1
  fi
  if [ -z "$MC_TOKEN" ]; then
    warn "no GitHub token found at $MC_TOKEN_FILE"
    warn "→ run: manjaro-care config  (and paste a Personal Access Token with repo scope)"
    return 1
  fi

  cd "$MC_ROOT" || return 1

  gitc config user.name  >/dev/null 2>&1 || gitc config user.name  "$MC_GH_USER"
  gitc config user.email >/dev/null 2>&1 || gitc config user.email "${MC_GH_USER}@users.noreply.github.com"

  prune_old_reports
  gitc add -A

  if gitc diff --cached --quiet; then
    info "nothing new to push"
    return 0
  fi

  local msg
  msg="${1:-care: ${MC_TASK} run $(date '+%F %H:%M') @ $(hostname 2>/dev/null || echo host)}"
  if ! capture gitc commit -m "$msg"; then
    warn "commit failed"
    return 1
  fi

  # سحب أولاً لتجنب رفض الرفع عند تعدد الأجهزة
  if ! capture gitc pull --rebase --autostash origin "$MC_GH_BRANCH"; then
    warn "pull failed (offline or empty repo) — trying push anyway"
  fi

  if capture git push "$(gh_push_url)" "HEAD:$MC_GH_BRANCH"; then
    ok "pushed → github.com/$MC_GH_USER/$MC_GH_REPO ($MC_GH_BRANCH)"
    return 0
  else
    warn "push failed (offline?) — commits kept locally, will go with next successful sync"
    return 0
  fi
}

cmd_sync() {
  start_report "sync"
  sum_h2 "Sync"
  sync_push "$@"
  local rc=$?
  if [ $rc -eq 0 ]; then
    ok "sync finished"
  fi
  return $rc
}
