# 🛠️ manjaro-care-cli (`mcare`)

أداة صيانة شاملة وآلية لنظام Manjaro Linux من سطر الأوامر، ثنائية اللغة (العربية/الإنجليزية)، مصممة لتشخيص وإصلاح المشاكل الشائعة بأمر واحد.
*A comprehensive and automated command-line maintenance tool for Manjaro Linux, bilingual (Arabic/English), designed to diagnose and fix common issues with a single command.*

[![Version](https://img.shields.io/badge/version-1.1.2-blue.svg)](https://github.com/DrAbdulmalek/manjaro-care/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Bash CI](https://github.com/DrAbdulmalek/manjaro-care/actions/workflows/ci.yml/badge.svg)](../.github/workflows/ci.yml)

---

## 🌟 المميزات / Features

- ⚡ **تثبيت تلقائي بضغطة واحدة** عبر `curl` (One-line automatic installation via `curl`).
- 🌍 **دعم عربي/إنجليزي للواجهة الأساسية ووحدات الإقلاع والشبكة** عبر `APP_LANG`؛ يجري استكمال ترجمة الوحدات الأخرى تدريجياً (core interface, boot and network modules are bilingual; other modules are being translated).
- 🔍 **فحص شامل للنظام**: الإقلاع، الحزم، الخدمات، الشبكة، Btrfs/Timeshift، الأمان، السجلات.
- 🛠️ **إصلاح تلقائي ذكي** مع نسخة احتياطية قبل أي تعديل.
- 📊 **تقارير فعلياً مكتوبة** في مجلد `reports/` + إخراج JSON للمعالجة الآلية (`-j`).
- 🧹 **تنظيف أكثر أماناً**: تأكيد تفاعلي قبل إزالة الحزم اليتيمة، والاحتفاظ بملفات `.pacnew/.pacsave` للمراجعة.
- 🖥️ **وضع هادئ** بدون ألوان ولا تفاصيل (`-q`) — مناسب للسكريبتات.

## 📦 التثبيت / Installation

### الطريقة 1: التثبيت التلقائي (موصى به) / Automatic (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/DrAbdulmalek/manjaro-care/main/manjaro-care-cli/install.sh | sudo bash
```

### الطريقة 2: التثبيت اليدوي / Manual

```bash
git clone https://github.com/DrAbdulmalek/manjaro-care.git
cd manjaro-care/manjaro-care-cli
sudo ./install.sh
```

 > ملاحظة: المثبّت لا يحذف مجلد تثبيت موجوداً عند فشل التحديث؛ يوقف العملية ويترك النسخة الحالية كما هي. كما لا يستبدل أمراً موجوداً غير رابط رمزي. أمر CLI هو **`mcare`** كي لا يتعارض مع واجهة GUI المثبتة في `/usr/bin/manjaro-care`.
> *The installed command is **`mcare`** to avoid shadowing the GUI app installed as `/usr/bin/manjaro-care`.*

## 🚀 الاستخدام / Usage

اللغة الافتراضية عربية؛ للإنجليزية استخدم `APP_LANG=en`.
*Default language is Arabic; for English use `APP_LANG=en`.*

| الوصف / Description | عربي (افتراضي) | English |
| :--- | :--- | :--- |
| فحص شامل / Full check | `sudo mcare doctor` | `sudo APP_LANG=en mcare doctor` |
| إصلاح تلقائي / Auto-fix | `sudo mcare fix` | `sudo APP_LANG=en mcare fix` |
| إعادة ضبط الشبكة / Reset network | `sudo mcare network reset` | `sudo APP_LANG=en mcare network reset` |
| إصلاح الواي فاي / Wi-Fi fix | `sudo mcare network wifi` | `sudo APP_LANG=en mcare network wifi` |
| فحص الإقلاع / Boot check | `sudo mcare boot check` | `sudo APP_LANG=en mcare boot check` |
| تنظيف النظام / Cleanup | `sudo mcare clean` | `sudo APP_LANG=en mcare clean` |
| إخراج JSON / JSON output | `sudo mcare -j doctor` | `sudo APP_LANG=en mcare -j doctor` |
| عرض المساعدة / Help | `mcare --help` | `APP_LANG=en mcare --help` |

> 💡 نصيحة: صدّر اللغة مرة واحدة في الجلسة: `export APP_LANG=en`
> *Tip: export the language once per session: `export APP_LANG=en`*

## 📚 الوحدات المتاحة / Available modules

1. **`boot`**: فحص وإصلاح مشاكل الإقلاع وGRUB، واكتشاف الإقلاع من لقطات Timeshift عن طريق الخطأ.
2. **`network`**: فحص وإعادة ضبط الشبكة، إصلاح مشاكل الواي فاي (`psk-flags`/KWallet)، تفعيل الراديو بعد إعادة الضبط.
3. **`packages`**: سلامة الحزم (`pacman -Qk`)، الملفات المفقودة، الحزم اليتيمة، ملفات `.pacnew`.
4. **`services`**: الخدمات الفاشلة أو المعلقة، وتعارضات إدارة الطاقة (TLP vs power-profiles-daemon).
5. **`btrfs`**: صحة نظام الملفات، لقطات Timeshift (حذف بوسم التاريخ الرسمي وتأكيد)، `scrub` دوري.
6. **`security`**: جدار الحماية (UFW)، المنافذ المفتوحة، حالة SSH وDocker.
7. **`logs`**: أخطاء الإقلاع الحالي، `coredumps`، تنظيف السجلات بأمان.

## 🔧 حل المشكلات الشائعة / Troubleshooting

- **خطأ `command not found`**: تأكد من تشغيل `sudo ./install.sh` لإنشاء الرابط الرمزي `mcare`، أو استخدم المسار الكامل `sudo ./manjaro-care-cli`.
- **فشل التثبيت التلقائي**: تأكد من توفر `curl` و`git` واتصال إنترنت نشط.
- **الأخطاء تبقى عربية رغم `APP_LANG=en`**: صدّر المتغير بشكل صحيح: `export APP_LANG=en` قبل الأمر.

## 🤝 المساهمة / Contributing

المساهمات مرحب بها! افتح Issue أو Pull Request على المستودع الرئيسي.
*Contributions are welcome! Open an issue or a pull request on the main repository.*

## 📝 الترخيص / License

MIT — راجع [LICENSE](../LICENSE). *See [LICENSE](../LICENSE).*
