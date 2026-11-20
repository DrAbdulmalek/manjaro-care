#!/usr/bin/env bash

set -u

LOCK="/var/lib/pacman/db.lck"

echo "========================================"
echo "   Manjaro Maintenance"
echo "========================================"
echo

# 1. فحص pacman
echo "[1/4] فحص pacman..."

if ! command -v pacman >/dev/null 2>&1; then
    echo "❌ pacman غير موجود."
    exit 1
fi

if pgrep -x pacman >/dev/null 2>&1; then
    echo "❌ pacman يعمل حالياً."
    echo "   لن يتم حذف القفل أو تشغيل تحديث آخر."
    echo
    pgrep -a -x pacman
    exit 1
fi

echo "✅ لا يوجد pacman نشط."
echo

# 2. فحص وإزالة القفل العالق فقط
echo "[2/4] فحص قفل قاعدة بيانات pacman..."

if [[ -e "$LOCK" ]]; then
    echo "⚠️ وُجد القفل:"
    echo "   $LOCK"
    echo

    # إعادة الفحص مباشرة قبل الحذف
    if pgrep -x pacman >/dev/null 2>&1; then
        echo "❌ ظهر pacman نشطاً أثناء الفحص."
        echo "   لن أحذف القفل."
        exit 1
    fi

    echo "القفل لا يرتبط بعملية pacman نشطة."
    echo "سيتم حذفه باعتباره قفلاً عالقاً."

    sudo rm -f "$LOCK" || {
        echo "❌ فشل حذف القفل."
        exit 1
    }

    if [[ -e "$LOCK" ]]; then
        echo "❌ ما زال القفل موجوداً."
        exit 1
    fi

    echo "✅ تمت إزالة القفل العالق."
else
    echo "✅ لا يوجد قفل عالق."
fi

echo

# 3. مزامنة قواعد البيانات
echo "[3/4] مزامنة قواعد بيانات pacman..."

if ! sudo pacman -Syy; then
    echo
    echo "❌ فشلت مزامنة قواعد البيانات."
    exit 1
fi

echo "✅ تمت المزامنة بنجاح."
echo

# 4. تحديث النظام
echo "[4/4] تحديث النظام..."
echo

if ! sudo pacman -Syu; then
    echo
    echo "❌ فشل تحديث النظام."
    exit 1
fi

echo
echo "========================================"
echo "✅ اكتملت صيانة Manjaro بنجاح"
echo "========================================"
