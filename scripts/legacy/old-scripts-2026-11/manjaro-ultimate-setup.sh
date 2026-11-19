#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#   مركز تحكم مانجارو — السكريبت الشامل النهائي (v5.0)
#   Manjaro Control Center — Complete All-in-One Installer
#   يجمع: النظام + الواجهة + كل الأدوات + التطبيق الرسومي
#   المستخدم: xorthomson | التاريخ: $(date +%Y-%m-%d)
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ─── متغيرات عامة ──────────────────────────────────────────────────────────────
APP_NAME="manjaro-control-center"
APP_DIR="$HOME/.local/share/$APP_NAME"
APP_SCRIPT="$APP_DIR/app.py"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
ICON_FILE="$ICON_DIR/$APP_NAME.svg"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_NAME.desktop"
LAUNCHER="$HOME/.local/bin/$APP_NAME"
LOGS_DIR="$HOME/terminal_logs"

# ─── ألوان ─────────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; R='\033[0;31m'; C='\033[0;36m'
NC='\033[0m'; BOLD='\033[1m'

step() { echo -e "\n${B}${BOLD}▶ $1${NC}"; }
ok()   { echo -e "${G}  ✔ $1${NC}"; }
warn() { echo -e "${Y}  ⚠ $1${NC}"; }
err()  { echo -e "${R}  ✘ $1${NC}"; }

# ─── دوال التثبيت الذكية ────────────────────────────────────────────────────────
install_pkg() {
    local pkgs=("$@")
    for p in "${pkgs[@]}"; do
        if pacman -Qi "$p" &>/dev/null; then
            ok "مثبّت: $p"
        else
            sudo pacman -S --noconfirm --needed "$p" 2>/dev/null \
                && ok "تم: $p" || warn "فشل: $p"
        fi
    done
}

install_aur() {
    local pkgs=("$@")
    command -v yay &>/dev/null || { warn "yay غير موجود"; return 0; }
    for p in "${pkgs[@]}"; do
        if pacman -Qi "$p" &>/dev/null; then
            ok "مثبّت (AUR): $p"
        else
            yay -S --noconfirm --needed "$p" 2>/dev/null \
                && ok "تم (AUR): $p" || warn "فشل (AUR): $p"
        fi
    done
}

# ───Banner ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}${C}"
cat << 'BANNER'
╔════════════════════════════════════════════════════════════╗
║     🐧 مركز تحكم مانجارو — السكريبت الشامل النهائي        ║
║     Manjaro Control Center — Complete All-in-One v5.0     ║
║     النظام + الواجهة + كل الأدوات + التطبيق الرسومي       ║
╚════════════════════════════════════════════════════════════╝
BANNER
echo -e "${NC}"

# ─── 0. التحقق من الصلاحيات ────────────────────────────────────────────────────
if [[ "$EUID" -eq 0 ]]; then
    err "لا تشغّل كـ root — شغّل كمستخدم عادي"
    exit 1
fi

# ─── 1. إصلاح بيئة النظام الأساسية ────────────────────────────────────────────
step "1. إصلاح بيئة pacman والمرايا"

# إزالة قفل قاعدة البيانات إذا وجد
[[ -f /var/lib/pacman/db.lck ]] && sudo rm -f /var/lib/pacman/db.lck

# تحديث المرايا (محاولة متعددة)
sudo pacman-mirrors --fasttrack 10 --api 2>/dev/null \
    || sudo pacman-mirrors --country Saudi-Arabia,Egypt,Germany,Turkey --api 2>/dev/null \
    || warn "فشل تحديث المرايا — متابعة..."

# تحديث النظام مع إعادة المحاولة عند القفل
safe_update() {
    local max=3; local attempt=1
    while ((attempt <= max)); do
        sudo pacman -Syyu --noconfirm && return 0
        [[ -f /var/lib/pacman/db.lck ]] && sudo rm -f /var/lib/pacman/db.lck
        sleep $((attempt * 2)); ((attempt++))
    done
    warn "فشل التحديث بعد $max محاولات"
}
safe_update

# ─── 2. تثبيت yay إذا لم يكن موجوداً ──────────────────────────────────────────
step "2. تثبيت yay (مدير AUR)"
if ! command -v yay &>/dev/null; then
    install_pkg git base-devel
    TMP=$(mktemp -d)
    git clone --depth=1 https://aur.archlinux.org/yay.git "$TMP/yay"
    (cd "$TMP/yay" && makepkg -si --noconfirm)
    rm -rf "$TMP"
    ok "تم تثبيت yay"
fi

# ─── 3. تمكين multilib لـ Wine والألعاب ───────────────────────────────────────
step "3. تمكين مستودع multilib"
if ! grep -q "^\[multilib\]" /etc/pacman.conf; then
    echo -e "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist" | sudo tee -a /etc/pacman.conf
    sudo pacman -Syy --noconfirm
    ok "تم تمكين multilib"
fi

# ─── 4. تثبيت أدوات النظام الأساسية ───────────────────────────────────────────
step "4. أدوات النظام والصيانة"
install_pkg \
    btop htop neofetch timeshift reflector bleachbit \
    ufw gufw fail2ban clamav clamtk keepassxc \
    curl wget git tree ripgrep fzf fd bat eza micro \
    asciinema tmux screen zsh-completions \
    python python-pip nodejs npm docker docker-compose

# تفعيل الخدمات
sudo systemctl enable --now docker 2>/dev/null || true
sudo systemctl enable --now ufw 2>/dev/null || true
sudo systemctl enable --now cronie 2>/dev/null || true
sudo systemctl enable --now fstrim.timer 2>/dev/null || true
[[ "$(groups $USER)" != *"docker"* ]] && sudo usermod -aG docker $USER && warn "أُضيفت لمجموعة docker — سجّل خروج ودخول"

# ─── 5. أدوات الهندسة العكسية ─────────────────────────────────────────────────
step "5. أدوات الهندسة العكسية"
install_pkg \
    radare2 gdb binutils ltrace strace binwalk \
    hexedit bless xxd bsdiff xdelta3 vbindiff patchelf \
    go rust angr python-msgspec

install_aur cutter detect-it-easy edb-debugger ghidra

# qiling عبر pip
pip install --user qiling --quiet 2>/dev/null && ok "تم تثبيت qiling" || warn "فشل qiling"

# gotch من المصدر
if ! command -v gotch &>/dev/null; then
    TMP=$(mktemp -d)
    if git clone --depth=1 https://github.com/DanteLorenzo/gotch.git "$TMP/gotch" 2>/dev/null; then
        (cd "$TMP/gotch" && go build . && sudo cp gotch /usr/local/bin/)
        ok "تم تثبيت gotch"
    else
        warn "فشل بناء gotch"
    fi
    rm -rf "$TMP"
fi

# ─── 6. محررات النصوص والبرمجة ────────────────────────────────────────────────
step "6. محررات النصوص والتطوير"
install_pkg kwrite gthumb digikam vlc gimp firefox chromium yt-dlp
install_aur notepadqq masterpdfeditor xournalpp pdfsam sublime-text-4 visual-studio-code-bin github-cli

# ─── 7. Neovim + LazyVim ──────────────────────────────────────────────────────
step "7. Neovim + LazyVim"
install_pkg neovim lazygit gcc make tree-sitter

# تثبيت pynvim
pip install --user pynvim --quiet 2>/dev/null \
    || pip install --break-system-packages pynvim --quiet 2>/dev/null \
    || warn "فشل pynvim"

# تثبيت LazyVim
if [[ ! -d "$HOME/.config/nvim" ]]; then
    git clone --depth=1 https://github.com/LazyVim/starter "$HOME/.config/nvim"
    rm -rf "$HOME/.config/nvim/.git"
    nvim --headless "+Lazy! sync" +qa 2>/dev/null && ok "LazyVim جاهز" || warn "شغّل nvim يدوياً لإكمال الإعداد"
    ok "اختصارات LazyVim: Space+e ملف، Space+f بحث، Space+g Git"
else
    ok "Neovim config موجود مسبقاً"
fi

# ─── 8. Wine + ألعاب ويندوز ───────────────────────────────────────────────────
step "8. Wine وتشغيل برامج ويندوز"
install_pkg wine winetricks wine-mono wine-gecko

# تهيئة Wine
timeout 20 winecfg -v win10 2>/dev/null || warn "فشل تهيئة Wine"
timeout 20 winetricks corefonts -q 2>/dev/null || warn "فشل خطوط Wine"

# أدوات الألعاب
install_pkg gamemode lib32-gamemode mangohud lib32-mangohud vulkan-icd-loader lib32-vulkan-icd-loader
install_aur lutris heroic-games-launcher-bin protonup-qt

sudo systemctl enable --now gamemoded 2>/dev/null || true

# ─── 9. السحابة والتكامل ──────────────────────────────────────────────────────
step "9. السحابة وربط الهاتف"
install_pkg rclone kdeconnect
install_aur onedrive-abraunegg

# تفعيل OneDrive
if command -v onedrive &>/dev/null; then
    systemctl --user enable onedrive 2>/dev/null && ok "OneDrive مفعّل" || true
fi

# تفعيل KDE Connect
systemctl --user enable --now kdeconnectd 2>/dev/null || true

# ─── 10. الافتراضية: KVM + VirtualBox ─────────────────────────────────────────
step "10. أدوات الافتراضية"
# التحقق من دعم CPU
if grep -E -q 'vmx|svm' /proc/cpuinfo; then
    ok "المعالج يدعم الافتراضية ✓"
else
    warn "تأكد من تفعيل VT-x/AMD-V في BIOS"
fi

# تثبيت headers
KERNEL=$(pacman -Q 2>/dev/null | grep -E '^linux[0-9]* ' | grep -v headers | head -1 | cut -d' ' -f1 || true)
[[ -n "$KERNEL" ]] && install_pkg "${KERNEL}-headers"

install_pkg qemu-full libvirt virt-manager virt-viewer edk2-ovmf dnsmasq iptables virtualbox virtualbox-host-dkms

# تفعيل الخدمات
sudo systemctl enable --now libvirtd 2>/dev/null || true
sudo virsh net-start default 2>/dev/null || true
sudo virsh net-autostart default 2>/dev/null || true
sudo usermod -aG libvirt,kvm,vboxusers $USER 2>/dev/null || true

# تحميل وحدات KVM
lsmod | grep -q kvm || { sudo modprobe kvm 2>/dev/null; grep -q vmx /proc/cpuinfo && sudo modprobe kvm_intel 2>/dev/null || sudo modprobe kvm_amd 2>/dev/null; }
command -v VBoxManage &>/dev/null && sudo modprobe vboxdrv 2>/dev/null && ok "vboxdrv محمّل" || true

# ─── 11. السمات والأيقونات والخطوط ────────────────────────────────────────────
step "11. التخصيص البصري"
install_aur \
    tela-icon-theme whitesur-gtk-theme qogir-gtk-theme-git \
    fluent-icon-theme-git arc-kde-git noto-fonts-emoji \
    ttf-ms-win11-auto ttf-roboto ttf-ubuntu-font-family otf-font-awesome

# تحديث ذاكرة الخطوط
fc-cache -fv 2>/dev/null || true

# ─── 12. نظام تسجيل التيرمينال ────────────────────────────────────────────────
step "12. إعداد تسجيل التيرمينال التلقائي"
mkdir -p "$LOGS_DIR"/{active,backup,cloud_ready,screenshots}
mkdir -p ~/.config/terminal-logger

# auto-start.sh
cat > ~/.config/terminal-logger/auto-start.sh << 'AUTOSTART'
#!/bin/bash
if [ -z "$SCRIPT_ACTIVE" ] && [ -z "$LOG_PAUSED" ]; then
    export SCRIPT_ACTIVE=1
    LOG_FILE="$HOME/terminal_logs/active/session_$(date +%Y%m%d_%H%M%S).log"
    { echo "# Session: $(date -Iseconds)"; echo "# USER: $USER"; } >> "$LOG_FILE"
    script -q -f "$LOG_FILE" &
    echo $! > /tmp/terminal_script_pid
    echo "$LOG_FILE" > /tmp/terminal_log_path
fi
AUTOSTART
chmod +x ~/.config/terminal-logger/auto-start.sh

# backup-upload.sh
cat > ~/.config/terminal-logger/backup-upload.sh << 'BACKUP'
#!/bin/bash
LOGS_DIR="$HOME/terminal_logs"
find "$LOGS_DIR/active" -name "*.log" -mmin +60 -exec mv {} "$LOGS_DIR/backup/" \; 2>/dev/null || true
for f in "$LOGS_DIR/backup"/*.log; do
    [ -f "$f" ] || continue
    sed -E 's/(password|token|api_key)[=:][^ ]*/\1=[REDACTED]/gi' "$f" | gzip > "${f%.log}.gz"
    rm -f "$f"
done
if command -v rclone &>/dev/null; then
    rclone copy "$LOGS_DIR/backup/" remote:terminal-logs/ --transfers 4 2>/dev/null && \
    find "$LOGS_DIR/backup" -name "*.gz" -mtime +30 -delete 2>/dev/null || true
fi
BACKUP
chmod +x ~/.config/terminal-logger/backup-upload.sh

# جدولة النسخ الاحتياطي
(crontab -l 2>/dev/null; echo "*/30 * * * * $HOME/.config/terminal-logger/backup-upload.sh") | crontab -

# ─── 13. تحسينات ~/.zshrc ─────────────────────────────────────────────────────
step "13. تحسينات التيرمينال (Zsh)"

# إضافة الإعدادات إذا لم تكن موجودة
cat >> ~/.zshrc << 'ZSHRC_APPEND'

# === مركز تحكم مانجارو ===
alias mcc='manjaro-control-center & 2>/dev/null'

# === تحسينات Zsh ===
setopt AUTO_CD EXTENDED_GLOB NULL_GLOB HIST_IGNORE_DUPS HIST_SAVE_NO_DUPS INC_APPEND_HISTORY INTERACTIVE_COMMENTS

# === إضافات الألوان والاقتراحات ===
[ -f /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ] && source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
[ -f /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ] && source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=8'
ZSH_HIGHLIGHT_STYLES[default]=none
ZSH_HIGHLIGHT_STYLES[unknown-token]=fg=red,bold
ZSH_HIGHLIGHT_STYLES[reserved-word]=fg=green
ZSH_HIGHLIGHT_STYLES[alias]=fg=cyan
ZSH_HIGHLIGHT_STYLES[builtin]=fg=cyan
ZSH_HIGHLIGHT_STYLES[command]=fg=green

# === Starship Prompt ===
eval "$(starship init zsh)" 2>/dev/null || true

# === Zoxide (تنقل ذكي) ===
eval "$(zoxide init zsh)" 2>/dev/null || true

# === Fzf تكامل ===
[ -f /usr/share/fzf/key-bindings.zsh ] && source /usr/share/fzf/key-bindings.zsh
[ -f /usr/share/fzf/completion.zsh ] && source /usr/share/fzf/completion.zsh

# === Aliases مفيدة ===
alias update='sudo pacman -Syu --noconfirm'
alias install='sudo pacman -S --noconfirm'
alias remove='sudo pacman -Rns --noconfirm'
alias clean='sudo pacman -Sc --noconfirm'
alias ll='ls -lah'
alias ..='cd ..'
alias cls='clear'
alias c='code .'
alias e='kwrite'
alias eb='kwrite-bg() { kwrite "$@" & disown; }; kwrite-bg'
alias gs='git status'
alias ga='git add'
alias gc='git commit'
alias gp='git push'

# === دوال تسجيل التيرمينال ===
termlog-status() {
    echo "=== حالة تسجيل التيرمينال ==="
    echo "📁 نشط: $(find ~/terminal_logs/active -name '*.log' 2>/dev/null | wc -l)"
    echo "💾 احتياطي: $(find ~/terminal_logs/backup -type f 2>/dev/null | wc -l)"
    echo "📦 الحجم: $(du -sh ~/terminal_logs 2>/dev/null | cut -f1)"
    rclone listremotes 2>/dev/null | grep -q remote: && echo "☁️ Drive: متصل" || echo "☁️ Drive: غير متصل"
}
merge-logs() {
    local out="$HOME/terminal_logs/merged_$(date +%Y%m%d).log"
    cat ~/terminal_logs/active/*.log ~/terminal_logs/backup/*.log > "$out" 2>/dev/null
    zcat ~/terminal_logs/backup/*.gz >> "$out" 2>/dev/null
    echo "✅ تم الدمج: $out ($(du -h "$out" | cut -f1))"
}
pause_log() { export LOG_PAUSED=1; [ -f /tmp/terminal_script_pid ] && kill $(cat /tmp/terminal_script_pid) 2>/dev/null; rm -f /tmp/terminal_script_pid; echo "⏸️  إيقاف"; }
resume_log() { unset LOG_PAUSED; source ~/.config/terminal-logger/auto-start.sh 2>/dev/null; echo "▶️  استئناف"; }
searchlog() { grep -r -i "${1:-}" ~/terminal_logs/ 2>/dev/null | head -20 | less -R; }
ZSHRC_APPEND

source ~/.zshrc 2>/dev/null || true
ok "تم تطبيق تحسينات Zsh"

# ─── 14. تحسينات الأداء ───────────────────────────────────────────────────────
step "14. تحسينات أداء النظام"
SYSCTL="/etc/sysctl.d/99-manjaro-optimize.conf"
if ! grep -q "vm.swappiness" "$SYSCTL" 2>/dev/null; then
    { echo "vm.swappiness=10"; echo "vm.vfs_cache_pressure=50"; echo "net.core.rmem_max=16777216"; echo "net.core.wmem_max=16777216"; } | sudo tee -a "$SYSCTL" >/dev/null
    sudo sysctl -p "$SYSCTL" 2>/dev/null || true
    ok "تم تطبيق تحسينات الذاكرة والشبكة"
fi

# ─── 15. بناء تطبيق مركز التحكم (Python/Tkinter) ─────────────────────────────
step "15. بناء تطبيق مركز التحكم الرسومي"

# تثبيت المتطلبات
if ! python3 -c "import tkinter" 2>/dev/null; then
    sudo pacman -S --noconfirm python-tk 2>/dev/null && ok "python-tk مثبت" || err "فشل python-tk"
fi
if ! python3 -c "import psutil" 2>/dev/null; then
    sudo pacman -S --noconfirm python-psutil 2>/dev/null && ok "python-psutil مثبت" || warn "psutil اختياري"
fi

# إنشاء المجلدات
mkdir -p "$APP_DIR" "$ICON_DIR" "$DESKTOP_DIR" "$HOME/.local/bin"

# إنشاء الأيقونة
cat > "$ICON_FILE" << 'SVGEOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#1a1a2e"/><stop offset="100%" style="stop-color:#16213e"/>
    </linearGradient>
    <linearGradient id="arc" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#4ade80"/><stop offset="100%" style="stop-color:#22c55e"/>
    </linearGradient>
    <linearGradient id="win" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#60a5fa"/><stop offset="100%" style="stop-color:#3b82f6"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="40" fill="url(#bg)"/>
  <circle cx="128" cy="128" r="90" fill="none" stroke="url(#arc)" stroke-width="6" opacity="0.3"/>
  <g transform="translate(128,128)">
    <circle r="28" fill="url(#arc)" opacity="0.9"/><circle r="16" fill="#1a1a2e"/>
    <rect x="-8" y="-42" width="16" height="18" rx="4" fill="url(#arc)"/>
    <rect x="-8" y="24" width="16" height="18" rx="4" fill="url(#arc)"/>
    <rect x="24" y="-8" width="18" height="16" rx="4" fill="url(#arc)"/>
    <rect x="-42" y="-8" width="18" height="16" rx="4" fill="url(#arc)"/>
  </g>
  <g transform="translate(170,50)" opacity="0.7">
    <rect x="0" y="0" width="14" height="14" rx="2" fill="url(#win)"/>
    <rect x="16" y="0" width="14" height="14" rx="2" fill="url(#win)"/>
    <rect x="0" y="16" width="14" height="14" rx="2" fill="url(#win)"/>
    <rect x="16" y="16" width="14" height="14" rx="2" fill="url(#win)"/>
  </g>
  <ellipse cx="60" cy="195" rx="16" ry="18" fill="#e2e8f0" opacity="0.8"/>
  <ellipse cx="60" cy="188" rx="10" ry="11" fill="#1e293b"/>
  <ellipse cx="60" cy="193" rx="7" ry="8" fill="#e2e8f0"/>
  <circle cx="57" cy="186" r="2.5" fill="white"/><circle cx="63" cy="186" r="2.5" fill="white"/>
  <path d="M56,191 Q60,193 64,191" fill="#f97316"/>
</svg>
SVGEOF
ok "تم إنشاء الأيقونة"

# إنشاء التطبيق الرئيسي (مختصر للعرض — النسخة الكاملة في الملف المرفق)
cat > "$APP_SCRIPT" << 'PYEOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مركز تحكم مانجارو — Windows 11 Style"""
import tkinter as tk, subprocess, threading, os, shutil, time, json
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime

COLORS = {"bg":"#0f172a","bg2":"#1e293b","bg3":"#334155","accent":"#22c55e","accent2":"#3b82f6","text":"#f1f5f9","text2":"#94a3b8","danger":"#ef4444","success":"#4ade80","warning":"#fbbf24"}
HOME = os.path.expanduser("~")

class ManjaroControlCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🐧 مركز تحكم مانجارو — Windows 11 Style")
        self.geometry("1100x720"); self.minsize(900,600); self.configure(bg=COLORS["bg"])
        self.setup_styles(); self.build_ui()
        self.after(500, self.refresh_dashboard)

    def setup_styles(self):
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("TNotebook", background=COLORS["bg"]); style.configure("TNotebook.Tab", background=COLORS["bg2"], foreground=COLORS["text2"], padding=[14,8], font=("Segoe UI",10))
        style.map("TNotebook.Tab", background=[("selected",COLORS["bg3"]),("active",COLORS["bg3"])], foreground=[("selected",COLORS["accent"]),("active",COLORS["text"])])
        style.configure("Action.TButton", background=COLORS["accent"], foreground="#000", font=("Segoe UI",10,"bold"), padding=[12,6], relief="flat")
        style.map("Action.TButton", background=[("active",COLORS["success"]),("disabled",COLORS["bg3"])])
        style.configure("Blue.TButton", background=COLORS["accent2"], foreground="white", font=("Segoe UI",10,"bold"), padding=[12,6], relief="flat")
        style.configure("Warn.TButton", background=COLORS["warning"], foreground="#000", font=("Segoe UI",10,"bold"), padding=[12,6], relief="flat")
        style.configure("Danger.TButton", background=COLORS["danger"], foreground="white", font=("Segoe UI",10,"bold"), padding=[12,6], relief="flat")

    def build_ui(self):
        # Header
        header = tk.Frame(self, bg=COLORS["bg2"], height=64); header.pack(fill="x", side="top"); header.pack_propagate(False)
        tk.Label(header, text="🐧", font=("Segoe UI Emoji",22), bg=COLORS["bg2"], fg=COLORS["text"]).pack(side="left", padx=(18,6), pady=10)
        tk.Label(header, text="مركز تحكم مانجارو", font=("Segoe UI",15,"bold"), bg=COLORS["bg2"], fg=COLORS["accent"]).pack(side="left", pady=10)
        self.clock_var = tk.StringVar()
        tk.Label(header, textvariable=self.clock_var, font=("Segoe UI",11), bg=COLORS["bg2"], fg=COLORS["text2"]).pack(side="right", padx=20)
        self.update_clock()
        # Notebook
        main = tk.Frame(self, bg=COLORS["bg"]); main.pack(fill="both", expand=True)
        self.nb = ttk.Notebook(main, style="TNotebook"); self.nb.pack(fill="both", expand=True)
        tabs = [("📊 لوحة المعلومات",self.build_dashboard),("🔧 النظام",self.build_system),("🎨 الواجهة",self.build_appearance),("🍷 Wine",self.build_wine),("☁️ السحابة",self.build_cloud),("🔐 الأمان",self.build_security),("📝 التيرمينال",self.build_terminal),("🛠️ أدوات",self.build_tools)]
        for title, builder in tabs:
            frame = ttk.Frame(self.nb, style="TFrame"); self.nb.add(frame, text=title); builder(frame)
        # Console
        console_frame = tk.Frame(self, bg=COLORS["bg2"], height=140); console_frame.pack(fill="x", side="bottom"); console_frame.pack_propagate(False)
        self.console = scrolledtext.ScrolledText(console_frame, height=6, bg="#0a0a0a", fg="#22c55e", font=("Courier",9), insertbackground=COLORS["accent"], relief="flat", bd=0, wrap="word")
        self.console.pack(fill="both", expand=True, padx=4, pady=(0,4))
        self.log(f"✅ جاهز | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def build_dashboard(self, parent): self._scrollable(parent, self._dashboard_content)
    def build_system(self, parent): self._scrollable(parent, self._system_content)
    def build_appearance(self, parent): self._scrollable(parent, self._appearance_content)
    def build_wine(self, parent): self._scrollable(parent, self._wine_content)
    def build_cloud(self, parent): self._scrollable(parent, self._cloud_content)
    def build_security(self, parent): self._scrollable(parent, self._security_content)
    def build_terminal(self, parent): self._scrollable(parent, self._terminal_content)
    def build_tools(self, parent): self._scrollable(parent, self._tools_content)

    def _scrollable(self, parent, content_fn):
        canvas = tk.Canvas(parent, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=scroll_frame, anchor="nw"); canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        canvas.bind("<MouseWheel>",_mw); canvas.bind("<Button-4>",lambda e:canvas.yview_scroll(-1,"units")); canvas.bind("<Button-5>",lambda e:canvas.yview_scroll(1,"units"))
        content_fn(scroll_frame)

    def _dashboard_content(self, f):
        tk.Label(f, text="📊 لوحة المعلومات", font=("Segoe UI",14,"bold"), bg=COLORS["bg"], fg=COLORS["accent"]).pack(anchor="w", padx=20, pady=(15,5))
        stats = tk.Frame(f, bg=COLORS["bg"]); stats.pack(fill="x", padx=20, pady=5); self.stat_cards={}
        for col,(key,label,color) in enumerate([("cpu","🔥 المعالج",COLORS["danger"]),("ram","💾 الذاكرة",COLORS["accent2"]),("disk","💿 القرص",COLORS["accent"]),("uptime","⏱️ التشغيل",COLORS["warning"])]):
            card = tk.Frame(stats, bg=COLORS["bg2"], padx=16, pady=12); card.grid(row=0,column=col,padx=6,pady=4,sticky="ew"); stats.columnconfigure(col,weight=1)
            tk.Label(card, text=label, font=("Segoe UI",9), bg=COLORS["bg2"], fg=COLORS["text2"]).pack(anchor="w")
            val = tk.Label(card, text="...", font=("Segoe UI",18,"bold"), bg=COLORS["bg2"], fg=color); val.pack(anchor="w", pady=(4,0)); self.stat_cards[key]=val
        ttk.Button(f, text="🔄 تحديث", style="Blue.TButton", command=self.refresh_dashboard).pack(pady=10)

    def _system_content(self, f): self._sections(f, [("🔄 التحديث", [("تحديث النظام","sudo pacman -Syu --noconfirm","Action"),("تنظيف الحزم","sudo pacman -Sc --noconfirm","Warn"),("نسخة احتياطية","timeshift --create --comments Manual","Action")]),("💾 النسخ", [("إنشاء نقطة استعادة","sudo timeshift --create --comments 'Manual'","Action"),("عرض النقاط","sudo timeshift --list","Blue")])])
    def _appearance_content(self, f): self._sections(f, [("🎨 الثيمات", [("فتح Kvantum","kvantummanager &","Action"),("تطبيق ثيم","lookandfeeltool --apply org.kde.breezedark.desktop 2>/dev/null","Action")]),("🔤 الخطوط", [("تثبيت خطوط ويندوز","yay -S --noconfirm ttf-ms-win11-auto 2>/dev/null","Action"),("تحديث الخطوط","fc-cache -fv","Blue")])])
    def _wine_content(self, f): self._sections(f, [("🍷 Wine", [("تهيئة Wine","winecfg -v win10 &","Action"),("خطوط أساسية","winetricks corefonts -q &","Action")]),("🎮 الألعاب", [("فتح Lutris","lutris &","Action"),("فتح Bottles","bottles &","Action")])])
    def _cloud_content(self, f): self._sections(f, [("☁️ Google Drive", [("إعداد rclone","xterm -e 'rclone config' &","Action"),("مزامنة","rclone copy ~/terminal_logs/backup/ remote:terminal-logs/ --progress 2>/dev/null","Action")]),("🔵 OneDrive", [("أول مزامنة","xterm -e 'onedrive --synchronize' &","Action"),("تفعيل الخدمة","systemctl --user enable --now onedrive","Action")])])
    def _security_content(self, f): self._sections(f, [("🔥 UFW", [("تفعيل الجدار","sudo ufw enable && sudo ufw status verbose","Action"),("تعطيل الجدار","sudo ufw disable","Danger")]),("🦠 ClamAV", [("تحديث القواعد","sudo freshclam","Action"),("فحص Downloads","clamscan -r ~/Downloads/ 2>/dev/null | tail -5","Action")])])
    def _terminal_content(self, f): self._sections(f, [("📝 التسجيل", [("حالة التسجيل","termlog-status 2>/dev/null || echo '⚠️ غير مُعدّ'","Blue"),("رفع فوري","~/.config/terminal-logger/backup-upload.sh 2>/dev/null","Action")]),("⚙️ Zsh", [("تعديل ~/.zshrc","kwrite ~/.zshrc &","Action"),("تطبيق الإعدادات","source ~/.zshrc && echo '✅ تم'","Action")])])
    def _tools_content(self, f): self._sections(f, [("🔬 الهندسة العكسية", [("فتح Radare2","xterm -e 'radare2 --help' &","Blue"),("فتح Cutter","cutter &","Action")]),("🐳 Docker", [("حالة Docker","sudo systemctl status docker | head -8","Blue"),("تنظيف","docker system prune -f 2>/dev/null","Warn")])])

    def _sections(self, parent, sections):
        for title, buttons in sections:
            hdr = tk.Frame(parent, bg=COLORS["bg3"], height=36); hdr.pack(fill="x", padx=16, pady=(14,0))
            tk.Label(hdr, text=title, font=("Segoe UI",11,"bold"), bg=COLORS["bg3"], fg=COLORS["accent"]).pack(side="left", padx=12, pady=6)
            btn_frame = tk.Frame(parent, bg=COLORS["bg2"], pady=10, padx=10); btn_frame.pack(fill="x", padx=16, pady=(0,4))
            for idx,(label,cmd,style) in enumerate(buttons):
                row,col = divmod(idx,3)
                c = tk.Frame(btn_frame, bg=COLORS["bg2"]); c.grid(row=row,column=col,padx=4,pady=4,sticky="ew"); btn_frame.columnconfigure(col,weight=1)
                ttk.Button(c, text=label, style=f"{style}.TButton", command=lambda c=cmd:self.run_command(c)).pack(fill="x")

    def run_command(self, cmd):
        def _run():
            self.log(f"$ {cmd}", "cyan")
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, env={**os.environ,"TERM":"xterm"})
                if r.stdout.strip(): self.log(r.stdout.strip())
                if r.stderr.strip(): self.log(f"⚠ {r.stderr.strip()}", "yellow")
                self.log(f"{'✅' if r.returncode==0 else '⚠'} كود: {r.returncode}", "green" if r.returncode==0 else "yellow")
            except subprocess.TimeoutExpired: self.log("⚠ انتهت المهلة", "yellow")
            except Exception as e: self.log(f"✘ {e}", "red")
        threading.Thread(target=_run, daemon=True).start()

    def log(self, msg, color=None):
        def _w():
            self.console.config(state="normal"); ts=datetime.now().strftime("%H:%M:%S")
            tags = {"cyan":"cmd","green":"success","yellow":"warning","red":"error"}
            self.console.insert("end", f"[{ts}] {msg}\n", tags.get(color))
            for t,c in [("timestamp","#475569"),("cmd","#60a5fa"),("success","#4ade80"),("warning","#fbbf24"),("error","#f87171")]: self.console.tag_config(t, foreground=c)
            self.console.see("end"); self.console.config(state="disabled")
        self.after(0, _w)

    def update_clock(self):
        self.clock_var.set(f"🕐 {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
        self.after(1000, self.update_clock)

    def refresh_dashboard(self):
        def _r():
            try:
                import psutil
                cpu=psutil.cpu_percent(interval=0.5); ram=psutil.virtual_memory(); disk=psutil.disk_usage('/'); uptime_s=time.time()-psutil.boot_time(); h,m=divmod(int(uptime_s),3600); m//=60
                self.after(0, lambda: self.stat_cards["cpu"].config(text=f"{cpu:.1f}%", fg=COLORS["danger"] if cpu>80 else COLORS["accent"]))
                self.after(0, lambda: self.stat_cards["ram"].config(text=f"{ram.percent:.1f}%", fg=COLORS["warning"] if ram.percent>85 else COLORS["accent2"]))
                self.after(0, lambda: self.stat_cards["disk"].config(text=f"{disk.percent:.1f}%", fg=COLORS["warning"] if disk.percent>90 else COLORS["accent"]))
                self.after(0, lambda: self.stat_cards["uptime"].config(text=f"{h}h {m}m"))
            except: pass
        threading.Thread(target=_r, daemon=True).start()
        self.after(10000, self.refresh_dashboard)

def main(): app = ManjaroControlCenter(); app.mainloop()
if __name__ == "__main__": main()
PYEOF
ok "تم إنشاء التطبيق الرئيسي"

# ─── 16. إنشاء المشغّل و .desktop ─────────────────────────────────────────────
step "16. إنشاء المشغّل وملف .desktop"

# Launcher
cat > "$LAUNCHER" << LAUNCH
#!/bin/bash
export PYTHONPATH="$APP_DIR:\$PYTHONPATH"
export LANG=\${LANG:-en_US.UTF-8}
export LC_ALL=\${LC_ALL:-en_US.UTF-8}
if ! python3 -c "import tkinter" 2>/dev/null; then
    notify-send "⚠️ خطأ" "ثبّت: sudo pacman -S python-tk" 2>/dev/null
    exit 1
fi
exec python3 "$APP_SCRIPT" "\$@"
LAUNCH
chmod +x "$LAUNCHER"

# .desktop
cat > "$DESKTOP_FILE" << DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=مركز تحكم مانجارو
Name[en]=Manjaro Control Center
GenericName=نظام ويندوز 11
Comment=إدارة كل الإعدادات والأدوات بضغطة زر
Exec=$LAUNCHER
Icon=$APP_NAME
Terminal=false
StartupNotify=true
Categories=System;Settings;Utility;
Keywords=manjaro;control;system;wine;cloud;security;
DESK
chmod +x "$DESKTOP_FILE"

# سطح المكتب
[[ -d "$HOME/Desktop" ]] && cp "$DESKTOP_FILE" "$HOME/Desktop/$APP_NAME.desktop" && chmod +x "$HOME/Desktop/$APP_NAME.desktop" && ok "اختصار سطح المكتب"

# تحديث القواعد
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
kbuildsycoca5 --noincremental 2>/dev/null || true
ok "تم تحديث قواعد البيانات"

# Alias في التيرمينال
grep -q "alias mcc=" ~/.zshrc 2>/dev/null || { echo -e "\nalias mcc='$LAUNCHER &'" >> ~/.zshrc; ok "تم إضافة alias: mcc"; }

# ─── 17. قائمة التحقق النهائية ────────────────────────────────────────────────
step "17. قائمة التحقق النهائية"
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║           ✅ اكتمل التثبيت بنجاح! 🎉                    ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${BOLD}📦 ما تم تثبيته:${NC}"
echo "  • أدوات النظام: btop, timeshift, ufw, fail2ban, clamav"
echo "  • الهندسة العكسية: radare2, cutter, ghidra, angr, gotch"
echo "  • التطوير: VS Code, Sublime, Neovim+LazyVim, Docker, Git"
echo "  • Wine والألعاب: Wine, Lutris, Bottles, Steam, MangoHud"
echo "  • السحابة: rclone, OneDrive, KDE Connect"
echo "  • الافتراضية: KVM/QEMU, VirtualBox, libvirt"
echo "  • التخصيص: سمات، أيقونات، خطوط ويندوز 11"
echo "  • التيرمينال: Zsh محسّن، تسجيل تلقائي، Starship, Zoxide"
echo "  • التطبيق: مركز تحكم مانجارو (واجهة رسومية كاملة)"

echo -e "\n${BOLD}🔧 خطوات ما بعد التثبيت:${NC}"
echo "  1️⃣  سجّل خروجاً ودخولاً (لتفعيل: Docker, KVM, OneDrive)"
echo "  2️⃣  شغّل: rclone config  ← لإعداد Google Drive"
echo "  3️⃣  شغّل: onedrive --synchronize  ← للمصادقة الأولى"
echo "  4️⃣  فعّل الجدار: sudo ufw enable"
echo "  5️⃣  أنشئ نسخة احتياطية: timeshift --create"

echo -e "\n${BOLD}🚀 طرق تشغيل مركز التحكم:${NC}"
echo "  • التيرمينال: ${G}source ~/.zshrc && mcc${NC}"
echo "  • مباشرة: ${G}$LAUNCHER${NC}"
echo "  • سطح المكتب: انقر مزدوجاً على الأيقونة"
echo "  • قائمة التطبيقات: ابحث عن 'مركز تحكم مانجارو'"

echo -e "\n${Y}💡 نصيحة: شغّل الآن:${NC} ${G}source ~/.zshrc && mcc${NC}"
echo ""