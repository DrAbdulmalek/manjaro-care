# البداية السريعة - manjaro-care-cli

## 🚀 البدء في 3 خطوات

### 1. التثبيت
```bash
git clone https://github.com/DrAbdulmalek/manjaro-care.git
cd manjaro-care/manjaro-care-cli
chmod +x manjaro-care-cli modules/*.sh
```

### 2. الفحص
```bash
sudo ./manjaro-care-cli doctor
```

### 3. الإصلاح
```bash
sudo ./manjaro-care-cli fix
```

## 📋 الأوامر الأكثر استخداماً

```bash
# فحص شامل
sudo ./manjaro-care-cli doctor

# إصلاح تلقائي
sudo ./manjaro-care-cli fix

# إعادة ضبط الشبكة
sudo ./manjaro-care-cli network reset

# فحص الإقلاع
sudo ./manjaro-care-cli boot check

# تنظيف النظام
sudo ./manjaro-care-cli clean
```

## 🎯 حل المشاكل الشائعة

### المشكلة: النظام يقلع ببطء
```bash
sudo ./manjaro-care-cli boot check
sudo ./manjaro-care-cli boot fix
```

### المشكلة: الواي فاي لا يتصل تلقائياً
```bash
sudo ./manjaro-care-cli network wifi
```

### المشكلة: خدمات فاشلة
```bash
sudo ./manjaro-care-cli services check
sudo ./manjaro-care-cli services fix
```

### المشكلة: حزم معطوبة
```bash
sudo ./manjaro-care-cli packages check
sudo ./manjaro-care-cli packages clean
```

## 📚 للمزيد من المعلومات

```bash
# عرض المساعدة الكاملة
sudo ./manjaro-care-cli --help

# قراءة التوثيق الشامل
cat README_AR.md
```

## ✅ بعد الإصلاح

1. راجع التقرير: `cat reports/report-*.txt`
2. تحقق من النسخ الاحتياطية: `ls backups/`
3. أعد التشغيل: `sudo reboot`

---

**هذا كل شيء!** 🎉
