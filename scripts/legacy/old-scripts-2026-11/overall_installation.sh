#!/bin/bash
# === Wine Complete Installer for Manjaro ===
# ⚠️  شغّل بدون sudo (سيطلب الصلاحيات عند الحاجة)

set -e

echo "🍷🎮 Wine Complete Setup for Manjaro"
echo "====================================="

# 1. تمكين multilib
echo -e "\n🔧 تمكين multilib..."
if ! grep -q "^\[multilib\]" /etc/pacman.conf; then
    echo -e "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist" | sudo tee -a /etc/pacman.conf
    sudo pacman -Syy --noconfirm
fi

# 2. تثبيت الحزم الأساسية
echo -e "\n📦 تثبيت الحزم الأساسية..."
sudo pacman -S --noconfirm \
    wine wine-mono wine-gecko winetricks \
    lib32-libpng lib32-libxslt lib32-gnutls lib32-mpg123 \
    lib32-openal lib32-v4l-utils lib32-libpulse \
    lib32-alsa-plugins lib32-alsa-lib lib32-libjpeg-turbo \
    lib32-libxcomposite lib32-libxinerama lib32-libxrandr \
    lib32-libxi lib32-libxcursor lib32-libxxf86vm \
    lib32-libxfixes lib32-gst-plugins-base-libs \
    lib32-flac lib32-libogg lib32-faudio \
    dxvk-bin lib32-dxvk-bin vkd3d-proton lib32-vkd3d-proton \
    mangohud lib32-mangohud gamescope lib32-gamescope \
    gamemode lib32-gamemode \
    pipewire-pulse pipewire-alsa lib32-pipewire \
    ttf-ms-fonts ttf-dejavu ttf-liberation \
    bottles lutris protonup-qt

# 3. تثبيت Wine-GE من AUR
echo -e "\n🥚 تثبيت Wine-GE..."
yay -S --noconfirm wine-ge-custom 2>/dev/null || echo "⚠️  تخطي Wine-GE"

# 4. تهيئة Wine
echo -e "\n⚙️ تهيئة Wine..."
winecfg -v win10 2>/dev/null || true
winetricks corefonts -q 2>/dev/null || true

# 5. تفعيل الخدمات
echo -e "\n🔧 تفعيل الخدمات..."
sudo systemctl enable --now gamemoded 2>/dev/null || true

# 6. إنشاء اختصارات مفيدة
echo -e "\n🔗 إنشاء اختصارات..."
cat > ~/.local/bin/wine-run << 'RUNEOF'
#!/bin/bash
# تشغيل برنامج مع تحسينات Wine
export WINEESYNC=1 WINEFSYNC=1 WINE_LARGE_ADDRESS_AWARE=1
export PULSE_LATENCY_MSEC=60
gamemoderun wine "$@"
RUNEOF
chmod +x ~/.local/bin/wine-run

cat > ~/.local/bin/wine-ge-run << 'GEEOF'
#!/bin/bash
# تشغيل برنامج مع Wine-GE
export WINE=/opt/wine-ge-custom/bin/wine
export WINEESYNC=1 WINEFSYNC=1
gamemoderun "$WINE" "$@"
GEEOF
chmod +x ~/.local/bin/wine-ge-run

# 7. إضافة لـ .zshrc
echo -e "\n📝 إضافة لـ ~/.zshrc..."
cat >> ~/.zshrc << 'ZSHEOF'

# === Wine Shortcuts ===
alias wine-run='~/.local/bin/wine-run'
alias wine-ge='~/.local/bin/wine-ge-run'
alias bottles='bottles'
alias lutris='lutris'
alias protonup='protonup-qt'

# Wine environment helper
wine-env() {
    export WINEESYNC=1 WINEFSYNC=1 WINE_LARGE_ADDRESS_AWARE=1
    export PULSE_LATENCY_MSEC=60
    echo "✅ بيئة Wine محسّنة مفعّلة"
}
ZSHEOF

source ~/.zshrc 2>/dev/null || true

# 8. عرض التعليمات
echo -e "\n✅ ✅ ✅ اكتمل التثبيت بنجاح! ✅ ✅ ✅"
echo ""
echo "📌 الأوامر المفيدة:"
echo "   wine program.exe          # تشغيل بـ Wine الرسمي"
echo "   wine-run program.exe      # تشغيل مع تحسينات"
echo "   wine-ge program.exe       # تشغيل بـ Wine-GE"
echo "   bottles                   # مدير التطبيقات (واجهة رسومية)"
echo "   lutris                    # مدير الألعاب (واجهة رسومية)"
echo "   protonup                  # إدارة إصدارات Proton-GE"
echo "   winetricks <package>      # تثبيت مكونات ويندوز إضافية"
echo ""
echo "🎮 للألعاب في Steam:"
echo "   1. افتح Steam → Settings → Compatibility"
echo "   2. فعّل 'Enable Steam Play'"
echo "   3. اختر 'GE-Proton' من القائمة"
echo ""
echo "🔧 لتحسين أداء لعبة محددة:"
echo "   1. في Lutris: اختر اللعبة → Configure → System options"
echo "   2. فعّل: Gamemode, DXVK, Esync"
echo ""
echo "🐛 لاستكشاف الأخطاء:"
echo "   WINEDEBUG=+timestamp,+pid wine program.exe 2>&1 | tee wine.log"
echo ""
echo "🍷 استمتع بتشغيل برامج ويندوز على مانجارو!"