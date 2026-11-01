# manjaro-care-cli - دليل الاستخدام الشامل

أداة صيانة شاملة لنظام Manjaro Linux، تم تطويرها بناءً على خبرة عملية في حل المشاكل الشائعة.

## 📋 المحتويات

- [المميزات](#المميزات)
- [التثبيت](#التثبيت)
- [الاستخدام](#الاستخدام)
- [الوحدات](#الوحدات)
- [أمثلة عملية](#أمثلة-عملية)
- [حل المشاكل](#حل-المشاكل)

## 🌟 المميزات

### ✅ فحص شامل
- فحص الإقلاع وGRUB
- فحص الحزم والتبعيات
- فحص الخدمات
- فحص الشبكة والواي فاي
- فحص Btrfs وTimeshift
- فحص الأمان والمنافذ
- تحليل السجلات

### ✅ إصلاح تلقائي
- إصلاح مشاكل الإقلاع
- إعادة ضبط الشبكة
- إصلاح تعارضات الخدمات
- تنظيف الحزم اليتيمة
- تنظيف السجلات

### ✅ أمان
- نسخ احتياطية قبل أي تعديل
- إمكانية التراجع
- تقارير مفصلة
- لا يحذف بيانات المستخدم

## 📦 التثبيت

### الطريقة 1: التثبيت المباشر

```bash
# استنساخ المستودع
git clone https://github.com/DrAbdulmalek/manjaro-care.git
cd manjaro-care/manjaro-care-cli

# تعيين الصلاحيات
chmod +x manjaro-care-cli
chmod +x modules/*.sh

# التشغيل المباشر
sudo ./manjaro-care-cli --help
```

### الطريقة 2: التثبيت النظامي

```bash
sudo ./install.sh
```

بعد التثبيت، يمكنك استخدام الأمر من أي مكان:
```bash
sudo mcare doctor
```

## 🚀 الاستخدام

### الأوامر الأساسية

#### 1. فحص شامل (doctor)
```bash
sudo mcare doctor
```
يقوم بفحص جميع جوانب النظام ويعرض تقريراً مفصلاً.

#### 2. إصلاح تلقائي (fix)
```bash
sudo mcare fix
```
يصلح جميع المشاكل المكتشفة تلقائياً.

#### 3. فحص الإقلاع (boot)
```bash
# فحص فقط
sudo mcare boot check

# فحص وإصلاح
sudo mcare boot fix
```

#### 4. إعادة ضبط الشبكة (network)
```bash
# فحص الشبكة
sudo mcare network check

# إعادة ضبط كاملة
sudo mcare network reset

# إصلاح مشاكل الواي فاي فقط
sudo mcare network wifi
```

#### 5. فحص الحزم (packages)
```bash
# فحص الحزم
sudo mcare packages check

# تنظيف الحزم اليتيمة
sudo mcare packages clean

# إعادة بناء حزم AUR
sudo mcare packages rebuild
```

#### 6. فحص الخدمات (services)
```bash
# فحص الخدمات
sudo mcare services check

# إصلاح الخدمات
sudo mcare services fix
```

#### 7. فحص Btrfs (btrfs)
```bash
# فحص Btrfs
sudo mcare btrfs check

# تشغيل scrub
sudo mcare btrfs scrub

# إدارة اللقطات
sudo mcare btrfs snapshots
```

#### 8. فحص الأمان (security)
```bash
# فحص الأمان
sudo mcare security check

# عرض المنافذ
sudo mcare security ports

# إدارة جدار الحماية
sudo mcare security firewall
```

#### 9. تحليل السجلات (logs)
```bash
# تحليل السجلات
sudo mcare logs check

# تنظيف السجلات
sudo mcare logs clean
```

#### 10. تنظيف شامل (clean)
```bash
sudo mcare clean
```
ينظف الحزم اليتيمة، الذاكرة المؤقتة، والسجلات القديمة.

## 📚 الوحدات

### 1. boot-sanity.sh
فحص وإصلاح مشاكل الإقلاع:
- التحقق من مصدر الجذر (هل يعمل من لقطة Timeshift؟)
- فحص grub.cfg
- التحقق من rootflags
- فحص ملفات النواة
- فحص grubenv

### 2. network-reset.sh
إعادة ضبط الشبكة وإصلاح الواي فاي:
- فحص حالة الأجهزة
- التحقق من rfkill
- فحص NetworkManager
- إصلاح ملفات الواي فاي (psk-flags)
- إعادة ضبط كاملة للشبكة

**مشكلة psk-flags:**
عندما تكون كلمة مرور الواي فاي مخزنة في KWallet (psk-flags=1)، يفشل الاتصال التلقائي عند الإقلاع. هذه الوحدة تصلح المشكلة بتعيين psk-flags=0.

### 3. package-check.sh
فحص الحزم والتبعيات:
- التحقق من قاعدة البيانات
- البحث عن ملفات مفقودة
- البحث عن حزم يتيمة
- التحقق من التحديثات المعلقة
- فحص ملفات .pacnew/.pacsave
- فحص حزم AUR المعطوبة

### 4. service-check.sh
فحص الخدمات:
- البحث عن خدمات فاشلة
- التحقق من الخدمات الأساسية
- كشف تعارضات إدارة الطاقة (TLP vs power-profiles-daemon)
- التحقق من الخدمات المعلقة

### 5. btrfs-check.sh
فحص Btrfs وTimeshift:
- التحقق من نظام الملفات
- فحص أخطاء الجهاز
- إدارة لقطات Timeshift
- تشغيل scrub

### 6. security-check.sh
فحص الأمان:
- التحقق من جدار الحماية
- فحص SSH
- كشف المنافذ المفتوحة
- فحص حاويات Docker
- التحقق من LLMNR

### 7. log-analyzer.sh
تحليل السجلات:
- أخطاء الإقلاع الحالي
- أخطاء النواة
- Coredumps
- تنظيف السجلات

## 💡 أمثلة عملية

### المثال 1: بعد تحديث النظام
```bash
# فحص شامل بعد التحديث
sudo mcare doctor

# إذا وجدت مشاكل، أصلحها
sudo mcare fix

# أعد التشغيل
sudo reboot
```

### المثال 2: مشاكل الواي فاي
```bash
# فحص الشبكة
sudo mcare network check

# إذا كانت المشكلة في psk-flags
sudo mcare network wifi

# أو إعادة ضبط كاملة
sudo mcare network reset
```

### المثال 3: بطء الإقلاع
```bash
# فحص الإقلاع
sudo mcare boot check

# إصلاح المشاكل
sudo mcare boot fix

# فحص الخدمات المعلقة
sudo mcare services check

# إصلاح الخدمات
sudo mcare services fix
```

### المثال 4: تنظيف النظام
```bash
# فحص شامل
sudo mcare doctor

# تنظيف شامل
sudo mcare clean

# تنظيف السجلات
sudo mcare logs clean
```

### المثال 5: فحص الأمان
```bash
# فحص الأمان
sudo mcare security check

# عرض المنافذ المفتوحة
sudo mcare security ports

# تفعيل جدار الحماية
sudo mcare security firewall
```

## 🔧 حل المشاكل

### المشكلة: "command not found"
```bash
# تأكد من أن السكريبت قابل للتنفيذ
chmod +x manjaro-care-cli
chmod +x modules/*.sh

# أو استخدم المسار الكامل
sudo ./manjaro-care-cli doctor
```

### المشكلة: "Permission denied"
```bash
# الأداة تتطلب صلاحيات root
sudo mcare doctor
```

### المشكلة: الوحدة غير موجودة
```bash
# تأكد من وجود جميع الملفات
ls -la modules/

# أعد استنساخ المستودع إذا لزم الأمر
git pull
```

### المشكلة: فشل الإصلاح
```bash
# راجع التقرير
cat reports/report-*.txt

# تحقق من النسخ الاحتياطية
ls -la backups/

# يمكنك التراجع يدوياً
sudo cp backups/grub.bak-* /etc/default/grub
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

## 📊 التقارير

تقوم الأداة بإنشاء تقارير مفصلة في مجلد `reports/`:
```bash
# عرض أحدث تقرير
ls -lt reports/ | head -5

# فتح التقرير
cat reports/report-2026-11-01_12-00-00.txt
```

## 🔒 النسخ الاحتياطية

قبل أي تعديل، تقوم الأداة بإنشاء نسخ احتياطية في `backups/`:
```bash
# عرض النسخ الاحتياطية
ls -lt backups/

# التراجع عن تعديل
sudo cp backups/grub.bak-2026-11-01_12-00-00 /etc/default/grub
```

## 🤝 المساهمة

المساهمات مرحب بها! يرجى:
1. Fork المستودع
2. إنشاء فرع جديد (`git checkout -b feature/amazing-feature`)
3. Commit التغييرات (`git commit -m 'Add amazing feature'`)
4. Push للفرع (`git push origin feature/amazing-feature`)
5. فتح Pull Request

## 📝 الترخيص

MIT License - انظر ملف `LICENSE` للتفاصيل.

## 🙏 شكر خاص

تم تطوير هذه الأداة بناءً على خبرة عملية في حل مشاكل نظام Manjaro، وخاصة:
- مشاكل الإقلاع من لقطات Timeshift
- تعارضات إدارة الطاقة
- مشاكل الواي فاي وpsk-flags
- حزم AUR المعطوبة بعد تحديث المكتبات
- خدمات systemd المعلقة

## 📞 الدعم

للمساعدة أو الإبلاغ عن مشاكل:
- افتح issue في GitHub
- راجع ملف README.md بالإنجليزية
- تحقق من التقارير والنسخ الاحتياطية

---

**ملاحظة هامة:** هذه الأداة تقوم بتعديلات على النظام. رغم وجود نسخ احتياطية، يُنصح بإنشاء لقطة Timeshift قبل الاستخدام.
