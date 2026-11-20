#!/bin/bash
# =============================================================================
# MANJARO → WINDOWS 11 EXPERIENCE - النسخة المصححة
# =============================================================================

echo "🪟 جاري تحويل مانجارو إلى تجربة ويندوز 11..."
echo "=============================================="

# -----------------------------------------------------------------------------
# 1. تحديث النظام
# -----------------------------------------------------------------------------
echo "🔄 تحديث النظام..."
sudo pacman -Syu --noconfirm

# تمكين multilib
if ! grep -q "^\[multilib\]" /etc/pacman.conf; then
    echo -e "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist" | sudo tee -a /etc/pacman.conf
    sudo pacman -Syy --noconfirm
fi

# -----------------------------------------------------------------------------
# 2. تثبيت أدوات النظام (مقسم لأجزاء)
# -----------------------------------------------------------------------------
echo "📦 تثبيت أدوات النظام..."

# جزء 1: المراقبة والإدارة
sudo pacman -S --noconfirm btop htop gnome-system-monitor

# جزء 2: إدارة الخدمات والتمهيد
sudo pacman -S --noconfirm systemd-manager grub-customizer

# جزء 3: الأمان
sudo pacman -S --noconfirm ufw gufw

# جزء 4: النسخ الاحتياطي والتنظيف
sudo pacman -S --noconfirm timeshift bleachbit

# جزء 5: الشبكة
sudo pacman -S --noconfirm nethogs iftop net-tools

# جزء 6: الخطوط
sudo pacman -S --noconfirm ttf-ms-fonts ttf-dejavu ttf-liberation wqy-zenhei

# جزء 7: الأرشيف
sudo pacman -S --noconfirm p7zip zip unzip unrar tar gzip

# جزء 8: البحث والأدوات
sudo pacman -S --noconfirm ripgrep fzf fd curl wget git tree neofetch

# -----------------------------------------------------------------------------
# 3. تثبيت واجهة سطح المكتب
# -----------------------------------------------------------------------------
echo "🎨 تثبيت الواجهة..."

sudo pacman -S --noconfirm latte-dock plank dunst libnotify flameshot copyq

# قائمة ابدأ (من AUR)
yay -S --noconfirm ulauncher 2>/dev/null || sudo pacman -S --noconfirm rofi rofi-calc

# -----------------------------------------------------------------------------
# 4. تثبيت المحررات
# -----------------------------------------------------------------------------
echo "✏️  تثبيت المحررات..."

sudo pacman -S --noconfirm kwrite kate notepadqq 2>/dev/null || true

# VS Code
if [ ! -f /etc/pacman.d/microsoft-vscode.conf ]; then
    sudo mkdir -p /etc/pacman.d/gpg.d
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/pacman.d/gpg.d/microsoft.gpg > /dev/null
    echo -e "[visual-studio-code]\nServer = https://packages.microsoft.com/yumrepos/vscode\nSigLevel = Never" | sudo tee /etc/pacman.d/microsoft-vscode.conf
fi
sudo pacman -Syy --noconfirm
sudo pacman -S --noconfirm code

# -----------------------------------------------------------------------------
# 5. تثبيت Wine
# -----------------------------------------------------------------------------
echo "🍷 تثبيت Wine..."

sudo pacman -S --noconfirm wine wine-mono wine-gecko winetricks

# مكتبات 32-بت
sudo pacman -S --noconfirm lib32-libpng lib32-gnutls lib32-openal lib32-libpulse

# Wine-GE (من AUR)
yay -S --noconfirm wine-ge-custom 2>/dev/null || echo "⚠️  تخطي Wine-GE"

# تهيئة Wine
winecfg -v win10 2>/dev/null || true

# -----------------------------------------------------------------------------
# 6. تثبيت أدوات الألعاب
# -----------------------------------------------------------------------------
echo "🎮 تثبيت تحسينات الألعاب..."

sudo pacman -S --noconfirm gamemode lib32-gamemode mangohud lib32-mangohud
sudo pacman -S --noconfirm vulkan-icd-loader lib32-vulkan-icd-loader
sudo pacman -S --noconfirm steam lutris 2>/dev/null || true

sudo systemctl enable --now gamemoded 2>/dev/null || true

# -----------------------------------------------------------------------------
# 7. تثبيت أدوات السحابة
# -----------------------------------------------------------------------------
echo "☁️  تثبيت السحابة..."

sudo pacman -S --noconfirm rclone
yay -S --noconfirm onedrive 2>/dev/null || true
sudo pacman -S --noconfirm kdeconnect

# -----------------------------------------------------------------------------
# 8. تثبيت أدوات التيرمينال
# -----------------------------------------------------------------------------
echo "⚡ تثبيت التيرمينال..."

sudo pacman -S --noconfirm zsh-autosuggestions zsh-syntax-highlighting
sudo pacman -S --noconfirm lnav visidata helix micro
sudo pacman -S --noconfirm asciinema tmux bat exa

# -----------------------------------------------------------------------------
# 9. إعداد مجلدات التسجيل
# -----------------------------------------------------------------------------
echo "📝 إعداد التسجيل..."

mkdir -p ~/terminal_logs/{active,backup,cloud_ready,screenshots}
mkdir -p ~/.config/terminal-logger

# -----------------------------------------------------------------------------
# 10. رسالة النهاية
# -----------------------------------------------------------------------------
echo ""
echo "✅ ✅ ✅ اكتمل التثبيت! ✅ ✅ ✅"
echo ""
echo "📌 الأوامر الأساسية:"
echo "   e file.txt      ← KWrite"
echo "   extract file    ← فك أرشيف"
echo "   termlog-status  ← حالة التسجيل"
echo "   update          ← تحديث النظام"
echo ""
echo "🚀 أغلق التيرمينال وافتح واحداً جديداً!"
