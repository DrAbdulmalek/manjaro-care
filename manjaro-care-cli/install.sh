#!/usr/bin/env bash
#
# manjaro-care-cli — مثبّت تلقائي (يدعم التثبيت بضغطة واحدة عبر curl)
#
# التثبيت المباشر:
#   curl -sSL https://raw.githubusercontent.com/DrAbdulmalek/manjaro-care/main/manjaro-care-cli/install.sh | sudo bash
#
# أو يدوياً بعد الاستنساخ:
#   git clone https://github.com/DrAbdulmalek/manjaro-care.git
#   sudo ./manjaro-care/install.sh
#
# ملاحظات (تصحيحات على نمط المثبتات الشائعة):
#  - اسم المستودع الصحيح manjaro-care (وليس manjaro-care-cli) — والسكريبت
#    يعيش داخل المجلد الفرعي manjaro-care-cli/ فيه.
#  - أمر التثبيت `mcare` كي لا يظلل واجهة GUI المثبتة في /usr/bin/manjaro-care.
#  - مسارات التثبيت قابلة للتجاوز بمتغيرات البيئة (MCARE_INSTALL_DIR /
#    MCARE_BIN_DIR) — مفيد للاختبار والتثبيتات المخصصة.
#  - عند piping عبر curl لا يوجد طرفية تفاعلية: لذلك لا read هنا إطلاقاً.
#

set -eu

INSTALLER_LANG="${APP_LANG:-ar}"

if [[ "$INSTALLER_LANG" == "en" ]]; then
    TITLE="manjaro-care-cli Auto-Installer"
    MSG_ROOT="This script must run as root (sudo)."
    MSG_USAGE="   Usage: curl -sSL https://raw.githubusercontent.com/DrAbdulmalek/manjaro-care/main/manjaro-care-cli/install.sh | sudo bash"
    MSG_GIT="Installing prerequisites (git)..."
    MSG_GIT_FAIL="Failed to install git"
    MSG_NO_PM="Package manager not found. Please install git manually."
    MSG_CLONE="Cloning repository to %s ..."
    MSG_UPDATE="Directory %s already exists — updating..."
    MSG_PULL_FAIL="Update failed — re-cloning..."
    MSG_PERMS="Setting permissions..."
    MSG_SYMLINK="Creating symlink 'mcare' in %s ..."
    MSG_DIRS="Creating work directories (reports, backups)..."
    MSG_DONE="Installation complete!"
    MSG_DIR="Install directory: %s"
    MSG_USAGE_APP="Usage:"
    MSG_LANG_HINT="To switch language, run:"
    MSG_LANG_CMD="  export APP_LANG=en   # or: export APP_LANG=ar"
else
    TITLE="المثبت التلقائي لـ manjaro-care-cli"
    MSG_ROOT="يجب تشغيل هذا السكريبت بصلاحيات root (sudo)."
    MSG_USAGE="   الاستخدام: curl -sSL https://raw.githubusercontent.com/DrAbdulmalek/manjaro-care/main/manjaro-care-cli/install.sh | sudo bash"
    MSG_GIT="تثبيت المتطلبات الأساسية (git)..."
    MSG_GIT_FAIL="فشل تثبيت git"
    MSG_NO_PM="لم يُعثر على مدير الحزم. ثبّت git يدوياً ثم أعد المحاولة."
    MSG_CLONE="تنزيل المستودع إلى %s ..."
    MSG_UPDATE="المجلد %s موجود مسبقاً — جاري التحديث..."
    MSG_PULL_FAIL="فشل التحديث — إعادة التنزيل..."
    MSG_PERMS="تعيين الصلاحيات..."
    MSG_SYMLINK="إنشاء الرابط الرمزي 'mcare' في %s ..."
    MSG_DIRS="إنشاء مجلدات العمل (reports, backups)..."
    MSG_DONE="اكتمل التثبيت بنجاح!"
    MSG_DIR="مجلد التثبيت: %s"
    MSG_USAGE_APP="الاستخدام:"
    MSG_LANG_HINT="لتغيير اللغة، شغّل:"
    MSG_LANG_CMD="  export APP_LANG=en   # أو: export APP_LANG=ar"
fi

if [[ $EUID -ne 0 ]]; then
    echo "❌ $MSG_ROOT"
    echo "$MSG_USAGE"
    exit 1
fi

# مسارات قابلة للتجاوز (الافتراضي كالوثائق)
INSTALL_DIR="${MCARE_INSTALL_DIR:-/opt/manjaro-care-cli}"
BIN_DIR="${MCARE_BIN_DIR:-/usr/local/bin}"
REPO_URL="${MCARE_REPO_URL:-https://github.com/DrAbdulmalek/manjaro-care.git}"
CLI_SUBDIR="manjaro-care-cli"   # موقع الأداة داخل المستودع

echo "═══════════════════════════════════════"
echo "  $TITLE"
echo "═══════════════════════════════════════"

# 1) المتطلبات
echo "📦 $MSG_GIT"
if ! command -v git &>/dev/null; then
    if command -v pacman &>/dev/null; then
        pacman -S --noconfirm --needed git || { echo "❌ $MSG_GIT_FAIL"; exit 1; }
    else
        echo "❌ $MSG_NO_PM"
        exit 1
    fi
fi

# 2) التنزيل (أو التحديث إن وُجد)
APP_DIR="$INSTALL_DIR/$CLI_SUBDIR"
if [[ -d "$APP_DIR/.git" ]]; then
    echo "📥 $(printf "$MSG_UPDATE" "$INSTALL_DIR")"
    if ! git -C "$APP_DIR" pull --ff-only origin main; then
        echo "⚠️  $MSG_PULL_FAIL"
        rm -rf "$INSTALL_DIR"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    fi
else
    echo "📥 $(printf "$MSG_CLONE" "$INSTALL_DIR")"
    rm -rf "$INSTALL_DIR"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# 3) الصلاحيات
echo "🔐 $MSG_PERMS"
chmod +x "$APP_DIR/manjaro-care-cli"
chmod +x "$APP_DIR/modules/"*.sh 2>/dev/null || true

# 4) الرابط الرمزي (الاسم mcare — لا يتعارض مع GUI)
echo "🔗 $(printf "$MSG_SYMLINK" "$BIN_DIR")"
mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/manjaro-care-cli" "$BIN_DIR/mcare"

# 5) مجلدات العمل
echo "📁 $MSG_DIRS"
mkdir -p "$APP_DIR/reports" "$APP_DIR/backups"

echo ""
echo "═══════════════════════════════════════"
echo "✅ $MSG_DONE"
echo "═══════════════════════════════════════"
echo ""
echo "$MSG_USAGE_APP"
echo "  sudo mcare doctor        # فحص شامل / full check"
echo "  sudo mcare network reset # إعادة ضبط الشبكة / reset network"
echo "  sudo mcare --help        # المساعدة / help"
echo ""
echo "$(printf "$MSG_DIR" "$INSTALL_DIR")"
echo ""
echo "$MSG_LANG_HINT"
echo "$MSG_LANG_CMD"
echo ""
