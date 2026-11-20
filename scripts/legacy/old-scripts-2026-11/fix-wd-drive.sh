#!/bin/bash
echo "🔍 تشخيص قرص WD_Portable..."
echo "=============================="

# 1. التحقق من وجود القرص
if [ ! -b /dev/sdb3 ]; then
    echo "❌ القرص /dev/sdb3 غير موجود!"
    exit 1
fi
echo "✅ القرص موجود"

# 2. نوع نظام الملفات
FS_TYPE=$(lsblk -no FSTYPE /dev/sdb3)
echo "📁 نوع نظام الملفات: $FS_TYPE"

# 3. التحقق من ntfs-3g
if ! command -v ntfs-3g &> /dev/null; then
    echo "⚠️ ntfs-3g غير مثبت، جاري التثبيت..."
    sudo pacman -S ntfs-3g --noconfirm
fi

# 4. محاولة ntfsfix
echo "🔧 جاري إصلاح سجلات NTFS..."
sudo ntfsfix /dev/sdb3

# 5. محاولة التركيب
echo "📦 جاري تركيب القرص..."
sudo mkdir -p /run/media/xorthomson/WD_Portable
sudo mount -t ntfs-3g /dev/sdb3 /run/media/xorthomson/WD_Portable

if [ $? -eq 0 ]; then
    echo "✅ تم التركيب بنجاح!"
    echo "📍 الموقع: /run/media/xorthomson/WD_Portable"
else
    echo "❌ فشل التركيب، راجع السجل أعلاه"
fi
