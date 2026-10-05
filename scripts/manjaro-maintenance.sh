#!/usr/bin/env bash
set -Eeuo pipefail

LOCK="/var/lib/pacman/db.lck"
PACMAN_CONF="/etc/pacman.conf"
CARE_LOCK="/run/lock/manjaro-care-maintenance.lock"

log(){ printf '%s\n' "$*"; }
fail(){ log "❌ $*"; exit 1; }

exec 9>"$CARE_LOCK"
flock -n 9 || fail "Manjaro Care maintenance is already running."

command -v pacman >/dev/null 2>&1 || fail "pacman غير موجود."
command -v pacman-mirrors >/dev/null 2>&1 || fail "pacman-mirrors غير موجود."
command -v fuser >/dev/null 2>&1 || fail "fuser غير موجود؛ لا يمكن فحص قفل pacman بأمان."

pacman_active(){
    pgrep -x pacman >/dev/null 2>&1 || fuser -s "$LOCK" 2>/dev/null
}

if pacman_active; then
    log "❌ pacman يعمل حالياً؛ لن يُحذف القفل ولن يبدأ تحديث آخر."
    exit 1
fi

if [[ -e "$LOCK" ]]; then
    if fuser -s "$LOCK" 2>/dev/null || pgrep -x pacman >/dev/null 2>&1; then
        fail "قفل pacman نشط؛ لن يتم حذفه."
    fi
    log "⚠️ إزالة قفل pacman عالق: $LOCK"
    sudo rm -f -- "$LOCK"
    [[ ! -e "$LOCK" ]] || fail "تعذر إزالة قفل pacman."
fi

# Repair the exact failure class: an empty [community] section with
# no active Server/Include can make pacman report "no servers configured".
if sudo awk '
    function flush(){ if (section == "community" && !has_server && !has_include) bad=1
                      section=""; has_server=0; has_include=0 }
    /^\[.*\][[:space:]]*$/ { flush(); section=$0; sub(/^\[/,"",section); sub(/\].*$/,"",section); next }
    /^[[:space:]]*(Server|Include)[[:space:]]*=/ { if ($1 ~ /^Server/) has_server=1; if ($1 ~ /^Include/) has_include=1 }
    END { flush(); exit bad ? 0 : 1 }
' "$PACMAN_CONF"; then
    sudo cp -a -- "$PACMAN_CONF" "$PACMAN_CONF.bak.manjaro-care.$(date +%Y%m%d-%H%M%S)"
    sudo sed -i '/^\[community\][[:space:]]*$/s/^/# Manjaro Care disabled empty repository section: /' "$PACMAN_CONF"
    log "✅ تم تعطيل [community] الفارغ فقط، مع إنشاء نسخة احتياطية."
fi

log "🌐 تحديث قائمة المرايا واختيار 5 مرايا سريعة..."
sudo pacman-mirrors --fasttrack 5

log "🔄 مزامنة قواعد البيانات وتحديث النظام..."
sudo pacman -Syu

log "✅ اكتملت صيانة Manjaro Care بنجاح."
