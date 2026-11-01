# manjaro-care-cli

أداة صيانة شاملة لنظام Manjaro Linux

## المميزات

- ✅ فحص شامل للنظام (الإقلاع، الحزم، الخدمات، الشبكة، الأمان)
- ✅ إصلاح تلقائي للمشاكل الشائعة
- ✅ إعادة ضبط الشبكة (مع إصلاح مشاكل الواي فاي)
- ✅ فحص وإصلاح Btrfs وTimeshift
- ✅ تحليل السجلات والأخطاء
- ✅ تنظيف النظام (حزم يتيمة، ذاكرة مخبأة)
- ✅ تقارير مفصلة
- ✅ نسخ احتياطية قبل أي تعديل

## التثبيت

```bash
git clone https://github.com/DrAbdulmalek/manjaro-care.git
cd manjaro-care/manjaro-care-cli
chmod +x manjaro-care-cli
```

## الاستخدام

### فحص شامل
```bash
sudo ./manjaro-care-cli doctor
```

### إصلاح المشاكل
```bash
sudo ./manjaro-care-cli fix
```

### إعادة ضبط الشبكة
```bash
sudo ./manjaro-care-cli network reset
```

### فحص الإقلاع
```bash
sudo ./manjaro-care-cli boot check
sudo ./manjaro-care-cli boot fix
```

## الوحدات

- **boot-sanity**: فحص وإصلاح مشاكل الإقلاع
- **network-reset**: إعادة ضبط الشبكة وإصلاح الواي فاي
- **package-check**: فحص الحزم والتبعيات
- **service-check**: فحص الخدمات
- **btrfs-check**: فحص Btrfs وTimeshift
- **security-check**: فحص الأمان والمنافذ
- **log-analyzer**: تحليل السجلات

## المساهمة

المساهمات مرحب بها! يرجى فتح issue أو pull request.

## الترخيص

MIT License
