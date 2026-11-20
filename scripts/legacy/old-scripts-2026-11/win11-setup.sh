#!/bin/bash
# ============================================================================
# مانجارو ← تجربة ويندوز 11 متكاملة (نسخة نهائية)
# ============================================================================

set -e

echo "🪟 جاري تحويل مانجارو إلى تجربة ويندوز 11..."
echo "=============================================="

# ----------------------------------------------------------------------------
# 1. تحديث النظام وتمكين multilib
# ----------------------------------------------------------------------------
echo "🔄 تحديث النظام..."
sudo pacman -Syu --noconfirm

if ! grep -q "^\[multilib\]" /etc/pacman.conf; then
    echo -e "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist" | sudo tee -a /etc/pacman.conf
    sudo pacman -Syy --noconfirm
fi

# ----------------------------------------------------------------------------
# 2. أدوات النظام الأساسية (مدير المهام، جدار ناري، نسخ احتياطي، ...)
# ----------------------------------------------------------------------------
echo "📦 تثبيت أدوات النظام..."
sudo pacman -S --noconfirm btop htop gnome-system-monitor
sudo pacman -S --noconfirm systemd-manager grub-customizer
sudo pacman -S --noconfirm ufw gufw timeshift bleachbit
sudo pacman -S --noconfirm nethogs iftop net-tools
sudo pacman -S --noconfirm ttf-ms-fonts ttf-dejavu ttf-liberation wqy-zenhei
sudo pacman -S --noconfirm p7zip zip unzip unrar tar gzip
sudo pacman -S --noconfirm ripgrep fzf fd curl wget git tree neofetch

# ----------------------------------------------------------------------------
# 3. واجهة شبيهة بويندوز (شريط مهام، قائمة ابدأ، إشعارات، لقطات، حافظة)
# ----------------------------------------------------------------------------
echo "🎨 تثبيت واجهة ويندوز..."
sudo pacman -S --noconfirm latte-dock plank dunst libnotify flameshot copyq
yay -S --noconfirm ulauncher 2>/dev/null || sudo pacman -S --noconfirm rofi rofi-calc

# ----------------------------------------------------------------------------
# 4. محررات النصوص (KWrite, NotepadQQ, VS Code)
# ----------------------------------------------------------------------------
echo "✏️  تثبيت المحررات..."
sudo pacman -S --noconfirm kwrite kate
yay -S --noconfirm notepadqq 2>/dev/null || true

# VS Code عبر مستودع Microsoft
if [ ! -f /etc/pacman.d/microsoft-vscode.conf ]; then
    sudo mkdir -p /etc/pacman.d/gpg.d
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/pacman.d/gpg.d/microsoft.gpg > /dev/null
    echo -e "[visual-studio-code]\nServer = https://packages.microsoft.com/yumrepos/vscode\nSigLevel = Never" | sudo tee /etc/pacman.d/microsoft-vscode.conf
fi
sudo pacman -Syy --noconfirm
sudo pacman -S --noconfirm code

# ----------------------------------------------------------------------------
# 5. Wine + Wine-GE (تشغيل برامج ويندوز)
# ----------------------------------------------------------------------------
echo "🍷 تثبيت Wine..."
sudo pacman -S --noconfirm wine wine-mono wine-gecko winetricks
sudo pacman -S --noconfirm lib32-libpng lib32-gnutls lib32-openal lib32-libpulse
yay -S --noconfirm wine-ge-custom 2>/dev/null || true
winecfg -v win10 2>/dev/null || true

# ----------------------------------------------------------------------------
# 6. أدوات الألعاب وتحسين الأداء
# ----------------------------------------------------------------------------
echo "🎮 تثبيت تحسينات الألعاب..."
sudo pacman -S --noconfirm gamemode lib32-gamemode mangohud lib32-mangohud
sudo pacman -S --noconfirm vulkan-icd-loader lib32-vulkan-icd-loader
sudo pacman -S --noconfirm steam lutris 2>/dev/null || true
sudo systemctl enable --now gamemoded 2>/dev/null || true

# ----------------------------------------------------------------------------
# 7. السحابة والتكامل مع الهاتف
# ----------------------------------------------------------------------------
echo "☁️  تثبيت السحابة والهاتف..."
sudo pacman -S --noconfirm rclone
yay -S --noconfirm onedrive 2>/dev/null || true
sudo pacman -S --noconfirm kdeconnect

# ----------------------------------------------------------------------------
# 8. أدوات التيرمينال المتقدمة
# ----------------------------------------------------------------------------
echo "⚡ تثبيت تحسينات التيرمينال..."
sudo pacman -S --noconfirm zsh-autosuggestions zsh-syntax-highlighting
sudo pacman -S --noconfirm lnav visidata helix micro
sudo pacman -S --noconfirm asciinema tmux bat exa

# ----------------------------------------------------------------------------
# 9. نظام تسجيل التيرمينال التلقائي (جلسات + نسخ احتياطي + رفع للسحابة)
# ----------------------------------------------------------------------------
echo "📝 إعداد نظام التسجيل..."
mkdir -p ~/terminal_logs/{active,backup,cloud_ready,screenshots}
mkdir -p ~/.config/terminal-logger

# سكريبت بدء التسجيل التلقائي
cat > ~/.config/terminal-logger/auto-start.sh << 'EOF'
#!/bin/bash
if [ -z "$SCRIPT_ACTIVE" ] && [ -z "$LOG_PAUSED" ]; then
    export SCRIPT_ACTIVE=1
    LOG_FILE="$HOME/terminal_logs/active/session_$(date +%Y%m%d_%H%M%S).log"
    { echo "# Session started: $(date -Iseconds)"; echo "# USER: $USER"; } >> "$LOG_FILE"
    script -q -f "$LOG_FILE" &
    echo $! > /tmp/terminal_script_pid
    echo "$LOG_FILE" > /tmp/terminal_log_path
fi
EOF
chmod +x ~/.config/terminal-logger/auto-start.sh

# سكريبت النسخ الاحتياطي والرفع
cat > ~/.config/terminal-logger/backup-upload.sh << 'EOF'
#!/bin/bash
find "$HOME/terminal_logs/active" -name "*.log" -mmin +60 -exec mv {} "$HOME/terminal_logs/backup/" \; 2>/dev/null
for f in "$HOME/terminal_logs/backup"/*.log; do
    [ -f "$f" ] || continue
    sed -E 's/(password|token|api_key)[=:][^ ]*/\1=[REDACTED]/gi' "$f" | gzip > "${f%.log}.gz"
    rm -f "$f"
done
if command -v rclone &>/dev/null; then
    rclone copy "$HOME/terminal_logs/backup/" remote:terminal-logs/ --transfers 4 2>/dev/null
    find "$HOME/terminal_logs/backup" -name "*.gz" -mtime +30 -delete 2>/dev/null
fi
EOF
chmod +x ~/.config/terminal-logger/backup-upload.sh

# جدولة النسخ كل 30 دقيقة
(crontab -l 2>/dev/null; echo "*/30 * * * * $HOME/.config/terminal-logger/backup-upload.sh") | crontab -
sudo systemctl enable --now cronie 2>/dev/null || true

# ----------------------------------------------------------------------------
# 10. ملف ~/.zshrc النهائي (الدمج المثالي)
# ----------------------------------------------------------------------------
echo "⚙️  تطبيق إعدادات التيرمينال النهائية..."

# نسخة احتياطية
cp ~/.zshrc ~/.zshrc.backup.final 2>/dev/null || true

# كتابة الملف الجديد
cat > ~/.zshrc << 'ZSHRC'
# ~/.zshrc - تجربة ويندوز 11 على مانجارو (النسخة النهائية)
# ============================================================================

# إعدادات أساسية
export HISTFILE=~/.zsh_history
export HISTSIZE=50000
export SAVEHIST=100000
setopt AUTO_CD EXTENDED_GLOB NULL_GLOB HIST_IGNORE_DUPS HIST_SAVE_NO_DUPS INC_APPEND_HISTORY INTERACTIVE_COMMENTS

# إضافات الألوان والاقتراحات
[ -f /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ] && source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
[ -f /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ] && source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=8'
ZSH_HIGHLIGHT_STYLES[default]=none
ZSH_HIGHLIGHT_STYLES[unknown-token]=fg=red,bold
ZSH_HIGHLIGHT_STYLES[reserved-word]=fg=green
ZSH_HIGHLIGHT_STYLES[alias]=fg=cyan
ZSH_HIGHLIGHT_STYLES[builtin]=fg=cyan
ZSH_HIGHLIGHT_STYLES[function]=fg=cyan
ZSH_HIGHLIGHT_STYLES[command]=fg=green
ZSH_HIGHLIGHT_STYLES[precommand]=fg=green

# متغيرات البيئة
export EDITOR="kwrite"
export VISUAL="kwrite"
export PATH="$HOME/.local/bin:$PATH"
export WINEESYNC=1 WINEFSYNC=1 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# ==================== Aliases ====================
alias update="sudo pacman -Syu --noconfirm"
alias install="sudo pacman -S --noconfirm"
alias remove="sudo pacman -Rns --noconfirm"
alias clean="sudo pacman -Sc --noconfirm"
alias ll="ls -lah"
alias la="ls -A"
alias ..="cd .."
alias ...="cd ../.."
alias cls="clear"

alias gs="git status"
alias ga="git add"
alias gc="git commit"
alias gp="git push"
alias gl="git log --oneline"

alias code="code --disable-gpu-sandbox 2>/dev/null"
alias c="code ."

# اختصارات KWrite (روح قديمة)
alias kw="kwrite"
alias edit="kwrite"
alias e="kwrite"
alias e.="kwrite ."
alias nqq="notepadqq"
alias notepad="notepadqq"
kwrite-bg() { kwrite "$@" & disown; }
alias eb="kwrite-bg"

# برامج مفضلة (من ملفك القديم)
alias pdf-master='masterpdfeditor &'
alias pdf-xournal='xournalpp &'
alias photos='gthumb &'
alias download='xdman &'

# دوال الضغط والفك (روح قديمة)
extract() {
    [ -f "$1" ] || { echo "❌ الملف غير موجود"; return 1; }
    case "$1" in
        *.tar.bz2) tar -xjf "$1" ;;
        *.tar.gz) tar -xzf "$1" ;;
        *.tar.xz) tar -xJf "$1" ;;
        *.bz2) bunzip2 "$1" ;;
        *.rar) unrar x "$1" ;;
        *.gz) gunzip "$1" ;;
        *.tar) tar -xf "$1" ;;
        *.zip) unzip "$1" ;;
        *.7z) 7z x "$1" ;;
        *) echo "❌ نوع غير مدعوم" ;;
    esac
}
compress7() { 7z a "$1.7z" "$1"; echo "✅ $1.7z"; }
compresszip() { zip -r "$1.zip" "$1"; echo "✅ $1.zip"; }

# دوال تسجيل التيرمينال (حديثة)
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
termlog-clean() { rm -rf ~/terminal_logs/active/*.log ~/terminal_logs/cloud_ready/*; echo "✅ تم التنظيف"; }

# دوال مساعدة عامة
mkcd() { mkdir -p "$1" && cd "$1"; }
dusum() { du -sh * 2>/dev/null | sort -hr; }
findf() { find . -type f -iname "*$1*" 2>/dev/null; }
sysinfo() {
    echo "🖥️  $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
    echo "🧠 الذاكرة: $(free -h | grep Mem | awk '{print $3"/"$2}')"
    echo "💾 القرص: $(df -h / | tail -1 | awk '{print $5}')"
    echo "⏱️  وقت التشغيل: $(uptime -p)"
}
alias help="echo 'e=محرر، extract=فك، termlog-status=حالة، merge-logs=دمج، searchlog=بحث، update=تحديث، sysinfo=معلومات'"

# ترحيب بسيط
echo ""
echo "👋 أهلاً، $USER! | $(date '+%H:%M')"
echo ""

# مصادر إضافية
[ -f ~/.config/terminal-logger/auto-start.sh ] && source ~/.config/terminal-logger/auto-start.sh 2>/dev/null
ZSHRC

source ~/.zshrc 2>/dev/null || true

# ----------------------------------------------------------------------------
# 11. تحسينات إضافية للنظام (SSD, ذاكرة)
# ----------------------------------------------------------------------------
echo "🔧 تحسينات الأداء..."
if [ -b /dev/sda ]; then
    sudo systemctl enable --now fstrim.timer 2>/dev/null || true
fi
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.d/99-manjaro-optimize.conf 2>/dev/null || true
echo "vm.vfs_cache_pressure=50" | sudo tee -a /etc/sysctl.d/99-manjaro-optimize.conf 2>/dev/null || true
sudo sysctl -p /etc/sysctl.d/99-manjaro-optimize.conf 2>/dev/null || true

# ----------------------------------------------------------------------------
# 12. نهاية التثبيت
# ----------------------------------------------------------------------------
echo ""
echo "✅ ✅ ✅ اكتمل التحويل بنجاح! ✅ ✅ ✅"
echo ""
echo "🪟 الميزات الجديدة:"
echo "   • شريط مهام (Latte Dock / Plank)"
echo "   • قائمة ابدأ (Ulauncher / Rofi)"
echo "   • إشعارات أنيقة (Dunst)"
echo "   • لقطات شاشة (Flameshot - Win+Shift+S)"
echo "   • سجل حافظة (CopyQ - Win+V)"
echo "   • Wine + ألعاب + تحسينات أداء"
echo "   • سحابة (rclone + OneDrive) + ربط الهاتف (KDE Connect)"
echo "   • تيرمينال مع ألوان، اقتراحات، تعليقات بـ #، وتسجيل تلقائي"
echo ""
echo "⌨️  الأوامر الأساسية:"
echo "   e file.txt      ← فتح بـ KWrite"
echo "   extract file.zip ← فك أرشيف"
echo "   termlog-status  ← حالة التسجيل"
echo "   merge-logs      ← دمج الجلسات"
echo "   searchlog كلمة  ← بحث في السجلات"
echo "   update          ← تحديث النظام"
echo "   sysinfo         ← معلومات النظام"
echo "   help            ← مساعدة سريعة"
echo ""
echo "🔐 تفعيل الجدار الناري: sudo ufw enable"
echo "💾 نسخة احتياطية: timeshift --create"
echo ""
echo "🚀 أغلق التيرمينال وافتح واحداً جديداً للاستمتاع!"
