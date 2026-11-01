#!/bin/bash
#
# سكريبت رفع المشروع إلى GitHub
#

set -e

echo "═══════════════════════════════════════"
echo "  رفع manjaro-care-cli إلى GitHub"
echo "═══════════════════════════════════════"

# التحقق من Git
if ! command -v git &>/dev/null; then
    echo "❌ Git غير مثبت"
    exit 1
fi

# التحقق من التهيئة
if [[ ! -d ".git" ]]; then
    echo "⚠️  المستودع غير مهيأ. جاري التهيئة..."
    ./setup-git.sh
fi

# التحقق من remote
if ! git remote get-url origin &>/dev/null; then
    echo ""
    echo "❌ لم يتم إعداد remote"
    echo ""
    echo "الخطوات:"
    echo "1. أنشئ مستودعاً جديداً على GitHub"
    echo "2. انسخ رابط المستودع"
    echo "3. شغّل:"
    echo "   git remote add origin <الرابط>"
    echo ""
    read -p "أدخل رابط المستودع الآن (أو اتركه فارغاً للخروج): " repo_url
    
    if [[ -z "$repo_url" ]]; then
        echo "تم الإلغاء"
        exit 0
    fi
    
    git remote add origin "$repo_url"
fi

# عرض الحالة
echo ""
echo "📊 حالة المستودع:"
git status --short

# إضافة التغييرات
echo ""
echo "📝 إضافة التغييرات..."
git add .

# إنشاء commit
echo ""
echo "💾 إنشاء commit..."
read -p "رسالة commit (أو اتركه فارغاً للرسالة الافتراضية): " commit_msg

if [[ -z "$commit_msg" ]]; then
    commit_msg="تحديث: تحسينات وإصلاحات - $(date +%Y-%m-%d)"
fi

git commit -m "$commit_msg"

# الدفع
echo ""
echo "🚀 الدفع إلى GitHub..."
branch=$(git branch --show-current)

if [[ -z "$branch" ]]; then
    branch="main"
    git branch -M main
fi

echo "الفرع: $branch"
read -p "متابعة الدفع؟ (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push -u origin "$branch"
    echo ""
    echo "✅ تم الرفع بنجاح!"
    echo ""
    repo_url=$(git remote get-url origin)
    echo "🌐 رابط المستودع: $repo_url"
else
    echo "تم الإلغاء"
fi

echo ""
echo "═══════════════════════════════════════"
echo "✅ اكتملت العملية"
echo "═══════════════════════════════════════"
