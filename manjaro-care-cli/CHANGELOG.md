# Changelog

## [1.1.3] - 2026-11-02 — إصلاح التشغيل عبر الرابط الرمزي `mcare`

### Fixed
- invoking the installed command `/usr/local/bin/mcare` (a symlink) computed
  `SCRIPT_DIR` from the link location, so `config/i18n.sh` and `modules/`
  were never found; with `set -u` the first message variable crashed the CLI
  (`sudo mcare doctor` → `MSG_FULLCHECK_TITLE: unbound variable`).
- `SCRIPT_DIR` is now derived from `readlink -f` of the real script file;
  symlinked invocation reaches the root check cleanly and loads i18n.

### Tests
- new symlink-invocation regression test in `tests/safety-regression.sh`
  (asserts no `unbound variable` and a clean root-required message);
  it skips gracefully where symlinks are not permitted.


## [1.1.2] - 2026-11-02 — إصلاحات السلامة

### Fixed
- المثبّت لا يحذف مجلد التثبيت عند فشل التحديث أو عند وجود مجلد غير معروف؛
  يجري الاستنساخ الجديد في مجلد مؤقت، ويرفض استبدال مجلد غير فارغ.
- إصلاح الإقلاع لا يحذف أو يعيد إنشاء `grubenv`، ولا يستبدل سطر
  معاملات النواة كاملاً. لا يضيف `rootflags=subvol=@` إلا بعد التحقق من
  أن الجذر الحالي Btrfs subvolume `/@`، ويرفض الكتابة فوق rootflags موجودة.
- توليد `grub.cfg` إلى ملف مؤقت والتحقق منه قبل الاستبدال، مع نسخ احتياطية
  لإعدادات GRUB السابقة.
- كشف ملف النواة يتعامل مع تسمية Manjaro `vmlinuz-<major.minor>-*`
  ومع الروابط الرمزية.
- إزالة الحزم اليتيمة تتطلب موافقة تفاعلية؛ التشغيل دون TTY لا يحذف الحزم.
- ملفات `.pacnew/.pacsave` لا تُحذف تلقائياً.
- إخراج `-j doctor` يرسل التشخيص إلى stderr ويحتفظ بـ stdout لكائن JSON.

### Tests
- إضافة اختبارات انحدار للسلامة، وإدراجها في Bash CI.

جميع التغييرات الملحوظة في هذا المشروع سيتم توثيقها في هذا الملف.

## [1.1.1] - 2026-11-02 — التدويل والتثبيت التلقائي وCI

### Added
- **دعم ثنائي اللغة (عربي/إنجليزي)**: ملف `config/i18n.sh` يحوي كل
  الرسائل؛ اللغة تُختار بمتغير البيئة `APP_LANG` (العربية افتراضياً).
  حُوِّلت الوحدتان `boot-sanity` و`network-reset` والسكريبت الرئيسي
  (بما فيه المساعدة) بالكامل؛ باقي الوحدات تتبنى النمط تدريجياً.
  - قرار تصميمي: رسائل i18n نصوص ثابتة أو قوالب `printf (%s)` تُركَّب
    في موضع الاستدعاء — لا توسيع متغيرات داخل التعريفات (نمط شائع
    يُفحى الرسائل لأن التوسع يحدث عند التحميل قبل وجود القيم).
- **مثبّت تلقائي بضغطة واحدة** عبر curl:
  `curl -sSL https://raw.githubusercontent.com/DrAbdulmalek/manjaro-care/main/manjaro-care-cli/install.sh | sudo bash`
  - يحدّث نسخة قائمة بـ `git pull --ff-only` ويعيد الاستنساخ عند الفشل.
  - مسارات قابلة للتجاوز (`MCARE_INSTALL_DIR`/`MCARE_BIN_DIR`)، وبلا
    أي read تفاعلي (آمن مع piping عبر curl).
- **CI لسكريبتات Bash** (`.github/workflows/ci.yml`): ShellCheck
  (بصلاحية warning) + `bash -n` لكل السكريبتات + اختبار دخان للغة
  العربية والإنجليزية، مع اختبار فقدان ملف i18n (fallback).

### Fixed
- المساعدة كانت تطبع رموز الألوان `\033` نصاً حرفياً (heredoc لا يوسّع
  التهريبات) — تُوسَّع الآن عبر `printf '%b'`.
- `bash-tool/lib/common.sh`: نمط `case` في `ask_yes` كان يحوي `Y`
  مكررة (SC2221/SC2222) — أُزيلت المكررة.
- bash-tool/install.sh: نصوص رسائل PATH كانت تستخدم `~` داخل اقتباس
  (SC2088) — صُححت إلى `$HOME`.
- توجيهات shellcheck موثّقة لإنذارات SC2034 الكاذبة (متغيرات تُعرَّف
  في ملف وتُستهلك في ملف آخر يُصدر source).

### Changed
- README الرئيسي والخاص بالـ CLI أُعيدت هيكلتهما ثنائيي اللغة مع
  شارات الحالة وأمر التثبيت السريع والفهرسة الكاملة للمكونات.

## [1.1.0] - 2026-11-01 — مراجعة وتصحيح شامل

### Fixed — وحدة الشبكة network-reset (المشكلة الأساسية)
- `((problems++))` بقيمة 0 يُرجع حالة خروج 1: مع `set -e` كان يقتل
  السكربت عند أول مشكلة تُكتشف في `network check`. استُبدل بـ
  `problems=$((problems + 1))` في كل الوحدات.
- `nmcli device status | grep wifi|ethernet` بلا نتائج كان يكسر
  pipefail ويُنهي الفحص صامتة — أُضيفت الحماية.
- `network wifi` كان يحذف **الشبكات المفتوحة السليمة**: القيمة الفارغة
  لـ key-mgmt تعني شبكة بلا تشفير وليست ملفاً تالفاً. الحذف الآن فقط
  للملفات التي يفشل استعلامها فعلاً وبتأكيد صريح من المستخدم.
- `network reset` لم يكن يُعيد تفعيل الراديو — أُضيف
  `nmcli radio wifi on` و `nmcli networking on` (بدونهما لا يتصل
  الواي فاي بعد إعادة الضبط، وهذا كان العَرَض الأصلي).
- `/var/lib/dhcp` مسار دبيان — على مانجارو الذيلات في `/var/lib/dhcpcd`.
- أسماء ملفات الواي فاي المحتوية على `:` كانت تُقرأ خاطئة في الوضع terse.

### Fixed — السكربت الرئيسي
- أُزيل `set -e`: كان يُنهي `doctor`/`report` عند أول مشكلة مكتشفة
  (الفحص وظيفته كشف المشاكل، لا الموت عندها). الأخطاء تُعالج صراحة.
- **التقرير لم يكن يُكتب إطلاقاً** (`REPORT_FILE` معلن بلا استخدام) —
  كل مخرجات السجل تُكتب الآن فعلياً في `reports/report-*.txt`.
- الخيارات `-q` و `-j` و `-f` كانت موثقة في المساعدة ولا تُقرأ —
  أُضيف محلل خيارات كامل مع ملخص JSON للفحوص.
- أسماء الأوامر المختصرة (boot check / network reset / ...) كانت تُقرأ
  من وسيط خاطئ بعد `shift`.

### Fixed — تعارض مع واجهة GUI
- أمر التثبيت كان `manjaro-care` في `/usr/local/bin` — يُظلل به أمر
  واجهة GUI المثبت في `/usr/bin/manjaro-care`. الاسم الآن **`mcare`**.

### Fixed — بقية الوحدات
- btrfs: `grep -c "^[0-9]" || echo 0` كان يطبع عدداً مزدوجاً
  ("0\n0") فيكسر المقارنة الرقمية — أُصلح الالتقاط.
- btrfs snapshots: الحذف كان يعتمد على رقم عمود هش في جدول العرض —
  الآن بوسم التاريخ الرسمي لـ timeshift مع تأكيد قبل الحذف.
- package-check: عدّ حزم AUR المعطوبة كان داخل subshell فيضيع —
  الآن عبر process substitution، مع حماية `ldd` من المسار الفارغ.
- service-check: `systemd-resolved` غير المثبتة كانت تُحتسب مشكلة —
  تُتخطى الآن إن لم تكن مثبتة.
- security-check: فحص LLMNR كان يفشل على مجلد فارغ فيظهر تحذيراً
  كاذباً — يفحص الآن المجلد والملف الأساسي معاً.
- boot-sanity: حماية أنابيب efibootmgr/findmnt + فشل grub-mkconfig
  يُبلَّغ عنه ويُبقي النسخة الاحتياطية.

### Changed
- الحساب والمستودع في كل التوثيق: DrAbdulmalek/manjaro-care (التطبيق
  داخل المجلد الفرعي `manjaro-care-cli/`).
- أمر التثبيت في كل الأمثلة: `sudo mcare …`.

## [1.0.0] - 2026-11-01

### Added
- وحدة فحص الإقلاع (boot-sanity)
  - التحقق من مصدر الجذر
  - فحص grub.cfg
  - التحقق من rootflags
  - فحص ملفات النواة
  - فحص grubenv
  
- وحدة إعادة ضبط الشبكة (network-reset)
  - فحص حالة الأجهزة
  - التحقق من rfkill
  - فحص NetworkManager
  - إصلاح ملفات الواي فاي (psk-flags)
  - إعادة ضبط كاملة للشبكة
  
- وحدة فحص الحزم (package-check)
  - التحقق من قاعدة البيانات
  - البحث عن ملفات مفقودة
  - البحث عن حزم يتيمة
  - التحقق من التحديثات المعلقة
  - فحص ملفات .pacnew/.pacsave
  - فحص حزم AUR المعطوبة
  
- وحدة فحص الخدمات (service-check)
  - البحث عن خدمات فاشلة
  - التحقق من الخدمات الأساسية
  - كشف تعارضات إدارة الطاقة
  - التحقق من الخدمات المعلقة
  
- وحدة فحص Btrfs (btrfs-check)
  - التحقق من نظام الملفات
  - فحص أخطاء الجهاز
  - إدارة لقطات Timeshift
  - تشغيل scrub
  
- وحدة فحص الأمان (security-check)
  - التحقق من جدار الحماية
  - فحص SSH
  - كشف المنافذ المفتوحة
  - فحص حاويات Docker
  - التحقق من LLMNR
  
- وحدة تحليل السجلات (log-analyzer)
  - أخطاء الإقلاع الحالي
  - أخطاء النواة
  - Coredumps
  - تنظيف السجلات
  
- وحدة الإصلاح التلقائي (auto-fix)
  - إصلاح شامل لجميع المشاكل المكتشفة

### Features
- واجهة سطر أوامر واضحة
- دعم الألوان والمخرجات المنسقة
- نسخ احتياطية قبل أي تعديل
- تقارير مفصلة
- وحدات منفصلة قابلة للتوسيع

### Fixed
- مشكلة الإقلاع من لقطة Timeshift
- تأخر الإقلاع بسبب قرص NTFS مفقود
- مشاكل الواي فاي (psk-flags و KWallet)
- تعارض TLP مع power-profiles-daemon
- خدمة update_startup.service المعلقة
- انهيارات AnyDesk المتكررة
- حزمة Ghidra المعطوبة
- منفذ Docker 7860 المكشوف
