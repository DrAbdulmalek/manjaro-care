#!/bin/bash
#
# سكريبت إعداد مستودع Git
#

echo "═══════════════════════════════════════"
echo "  إعداد مستودع manjaro-care-cli"
echo "═══════════════════════════════════════"

# التحقق من Git
if ! command -v git &>/dev/null; then
    echo "❌ Git غير مثبت. ثبته أولاً:"
    echo "   sudo pacman -S git"
    exit 1
fi

# تهيئة المستودع
echo "📦 تهيئة مستودع Git..."
git init

# إنشاء .gitignore
cat > .gitignore << 'EOF'
# النسخ الاحتياطية
backups/
*.bak
*.backup

# التقارير
reports/
*.log

# الملفات المؤقتة
*.tmp
*.swp
*~

# إعدادات محلية
config.local.conf

# مجلدات النظام
__pycache__/
*.pyc
EOF

# إضافة الملفات
echo "📝 إضافة الملفات..."
git add .

# إنشاء commit
echo "💾 إنشاء commit..."
git commit -m "الإصدار الأولي - manjaro-care-cli v1.0.0

- فحص شامل للنظام (إقلاع، حزم، خدمات، شبكة، أمان)
- إصلاح تلقائي للمشاكل الشائعة
- إعادة ضبط الشبكة مع إصلاح مشاكل الواي فاي
- فحص Btrfs وTimeshift
- تحليل السجلات والأخطاء
- تنظيف النظام

المميزات:
✅ وحدات منفصلة لكل وظيفة
✅ نسخ احتياطية قبل أي تعديل
✅ تقارير مفصلة
✅ دعم JSON للإخراج الآلي
✅ واجهة سطر أوامر واضحة"

# إضافة remote
echo "🌐 إضافة remote..."
read -p "أدخل رابط مستودع GitHub (أو اتركه فارغاً للتخطي): " repo_url

if [[ -n "$repo_url" ]]; then
    git remote add origin "$repo_url"
    echo "✅ تم إضافة remote: $repo_url"
    echo ""
    echo "لرفع المشروع:"
    echo "  git push -u origin main"
else
    echo "⚠️  تم تخطي إضافة remote"
    echo ""
    echo "لإضافة remote لاحقاً:"
    echo "  git remote add origin https://github.com/username/manjaro-care-cli.git"
    echo "  git push -u origin main"
fi

echo ""
echo "═══════════════════════════════════════"
echo "✅ اكتمل إعداد المستودع"
echo "═══════════════════════════════════════"
