#!/bin/bash
# ============================================
# سكريبت الإصلاح السريع - عند الحاجة
# ============================================

echo "🔧 إصلاح إعدادات السكانر..."

# 1. إعادة تحميل وحدات النواة
sudo modprobe usb_storage
sudo modprobe usblp

# 2. إعادة تحميل قواعد udev
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. إعادة تشغيل خدمة saned
sudo systemctl restart saned.socket

# 4. التحقق من الصلاحيات
sudo setfacl -m u:$USER:rw /dev/bus/usb 2>/dev/null || true

# 5. إلغاء تنشيط conda لتجنب التعارض
conda deactivate 2>/dev/null || true

echo "✅ الإصلاح اكتمل!"
echo "الآن شغّل: ~/test-scanner-tomorrow.sh"
