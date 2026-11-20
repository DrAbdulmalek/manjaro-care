#!/bin/bash
#
# سكريبت اختبار manjaro-care-cli
#

set -e

echo "═══════════════════════════════════════"
echo "  اختبار manjaro-care-cli"
echo "═══════════════════════════════════════"

# التحقق من الصلاحيات
if [[ $EUID -ne 0 ]]; then
    echo "❌ هذا السكريبت يتطلب صلاحيات root"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# اختبار 1: المساعدة
echo ""
echo "📝 اختبار 1: عرض المساعدة"
./manjaro-care-cli --help || { echo "❌ فشل"; exit 1; }
echo "✅ نجح"

# اختبار 2: الإصدار
echo ""
echo "📝 اختبار 2: عرض الإصدار"
./manjaro-care-cli --version || { echo "❌ فشل"; exit 1; }
echo "✅ نجح"

# اختبار 3: فحص الإقلاع
echo ""
echo "📝 اختبار 3: فحص الإقلاع"
./manjaro-care-cli boot check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 4: فحص الشبكة
echo ""
echo "📝 اختبار 4: فحص الشبكة"
./manjaro-care-cli network check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 5: فحص الحزم
echo ""
echo "📝 اختبار 5: فحص الحزم"
./manjaro-care-cli packages check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 6: فحص الخدمات
echo ""
echo "📝 اختبار 6: فحص الخدمات"
./manjaro-care-cli services check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 7: فحص Btrfs
echo ""
echo "📝 اختبار 7: فحص Btrfs"
./manjaro-care-cli btrfs check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 8: فحص الأمان
echo ""
echo "📝 اختبار 8: فحص الأمان"
./manjaro-care-cli security check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 9: تحليل السجلات
echo ""
echo "📝 اختبار 9: تحليل السجلات"
./manjaro-care-cli logs check || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

# اختبار 10: فحص شامل
echo ""
echo "📝 اختبار 10: فحص شامل"
./manjaro-care-cli doctor || echo "⚠️  تم اكتشاف مشاكل (متوقع)"

echo ""
echo "═══════════════════════════════════════"
echo "✅ اكتملت جميع الاختبارات"
echo "═══════════════════════════════════════"
