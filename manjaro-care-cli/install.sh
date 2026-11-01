#!/bin/bash
#
# سكريبت تثبيت manjaro-care-cli
# (مُصحّح: اسم الأمر المثبّت `mcare` — الاسم القديم `manjaro-care`
#  يتعارض مع واجهة GUI المثبتة في /usr/bin/manjaro-care، وكان
#  /usr/local/bin يظللها)
#

set -e

echo "═══════════════════════════════════════"
echo "  تثبيت manjaro-care-cli"
echo "═══════════════════════════════════════"

# التحقق من الصلاحيات
if [[ $EUID -ne 0 ]]; then
    echo "❌ هذا السكريبت يتطلب صلاحيات root"
    echo "   شغّله عبر: sudo ./install.sh"
    exit 1
fi

INSTALL_DIR="/opt/manjaro-care-cli"
BIN_DIR="/usr/local/bin"

# إنشاء مجلد التثبيت
echo "📦 إنشاء مجلد التثبيت..."
mkdir -p "$INSTALL_DIR"

# نسخ الملفات
echo "📋 نسخ الملفات..."
cp -r ./* "$INSTALL_DIR/"

# تعيين الصلاحيات
echo "🔐 تعيين الصلاحيات..."
chmod +x "$INSTALL_DIR/manjaro-care-cli"
chmod +x "$INSTALL_DIR/modules/"*.sh

# إنشاء رابط رمزي
# ملاحظة: الأمر `manjaro-care` محجوز لواجهة GUI — لهذا يُسمى هذا CLI‏ `mcare`
echo "🔗 إنشاء رابط رمزي..."
ln -sf "$INSTALL_DIR/manjaro-care-cli" "$BIN_DIR/mcare"

# إنشاء مجلدات العمل
echo "📁 إنشاء مجلدات العمل..."
mkdir -p "$INSTALL_DIR/reports"
mkdir -p "$INSTALL_DIR/backups"

echo ""
echo "═══════════════════════════════════════"
echo "✅ اكتمل التثبيت"
echo "═══════════════════════════════════════"
echo ""
echo "الاستخدام:"
echo "  sudo mcare doctor    # فحص شامل"
echo "  sudo mcare fix       # إصلاح تلقائي"
echo "  sudo mcare --help    # المساعدة"
echo ""
echo "مجلد التثبيت: $INSTALL_DIR"
echo ""
