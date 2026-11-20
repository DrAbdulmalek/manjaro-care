#!/bin/bash
# ============================================
# Sublime Text Package Installer
# ============================================

echo "🔧 إعداد Sublime Text..."

# 1. تحقق من التثبيت
if ! command -v subl &> /dev/null; then
    echo "❌ Sublime Text غير مثبت!"
    echo "   ثبّته: yay -S sublime-text-4"
    exit 1
fi
echo "✅ Sublime Text مثبت"

# 2. اعرف مسار Packages
if [ -d ~/.config/sublime-text/Packages ]; then
    PACKAGE_PATH=~/.config/sublime-text/Packages
elif [ -d ~/.config/sublime-text-3/Packages ]; then
    PACKAGE_PATH=~/.config/sublime-text-3/Packages
else
    echo "⚠️ لم يُعثر على مجلد Packages، سأستخدم الافتراضي"
    PACKAGE_PATH=~/.config/sublime-text/Packages
fi

echo "📁 مسار Packages: $PACKAGE_PATH"

# 3. أنشئ المجلد
mkdir -p "$PACKAGE_PATH"

# 4. ثبّت Package Control (إذا لم يكن موجوداً)
if [ ! -d "$PACKAGE_PATH/Package Control" ]; then
    echo "📦 تثبيت Package Control..."
    cd "$PACKAGE_PATH"
    git clone https://github.com/wbond/package_control.git "Package Control"
else
    echo "✅ Package Control موجود"
fi

# 5. ثبّت الإضافات
echo ""
echo "🔌 تثبيت الإضافات..."

cd "$PACKAGE_PATH"

declare -A packages=(
    ["Emmet"]="https://github.com/emmetio/sublime-text-plugin.git"
    ["GitGutter"]="https://github.com/jisaacks/GitGutter.git"
    ["SideBarEnhancements"]="https://github.com/SideBarEnhancements-org/SideBarEnhancements.git"
    ["AdvancedNewFile"]="https://github.com/skuroda/Sublime-AdvancedNewFile.git"
    ["FindKeyConflicts"]="https://github.com/facelessuser/FindKeyConflicts.git"
)

for pkg_name in "${!packages[@]}"; do
    pkg_url="${packages[$pkg_name]}"
    if [ -d "$pkg_name" ]; then
        echo "  ✅ $pkg_name (مثبت مسبقاً)"
    else
        echo "  📥 تثبيت $pkg_name..."
        git clone "$pkg_url" "$pkg_name"
    fi
done

# 6. إعادة تشغيل Sublime Text
echo ""
echo "✅ اكتمل التثبيت!"
echo "🔄 أعد تشغيل Sublime Text لتفعيل الإضافات"
echo ""
echo "📋 الإضافات المثبتة:"
ls -d */ | grep -E "Emmet|GitGutter|SideBar|AdvancedNewFile|FindKey"

