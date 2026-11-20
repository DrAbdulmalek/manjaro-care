# فهرس سكربتات old-scripts-archive — وتوزيعها على المشاريع

> المصدر: `old-scripts-archive.zip` / `old-scripts-archive.7z.001` (المحتوى الجوهري واحد بينهما؛
> فرق 7z إضافي = مجلدات و`.git` مضمّن لمشروع manjaro-ultimate-control-center).
> أُرشف هنا الجذر القابل لإعادة الاستخدام بتاريخ 2026-11-19، مع خريطة لكل سكربت إلى
> المشروع الأنسب له في حساب `DrAbdulmalek`.

**ملاحظة عن الطلب الأصلي "lh dg.l":** بحث شامل بالاسم والمحتوى في الأرشيفين (zip و7z)
لم يجد أي ملف بهذا الاسم أو أي محتوى يطابقه — الأرجح أنه إشارة عامة لسكربتات هذا الأرشيف،
وقد أُرشفت كلها هنا وتوزّع الأنسب منها كما في الجدول أدناه. إن كان المقصود ملفاً بعينه
فاسمه بخلاف ذلك — يكفي ذكره ليُستخرج ويوزّع فوراً.

## خريطة التوزيع المقترحة

| السكربت | الغرض (من محتواه) | المشروع الوجهة | الحالة |
|---|---|---|---|
| `fix-scanner-ready.sh` | إصلاح سريع للسكانر: إعادة تحميل وحدات usb_storage/usblp وقواعد udev | كان مرشحاً لـ **scanner-fixer** — لكن المستودع مؤرشف على GitHub (read-only) فلا يقبل دفع؛ يبقى مؤرشفاً هنا ويمكن دفعه عند إلغاء الأرشفة | محفوظ هنا |
| `manjaro-maintenance.sh` | صيانة مانجارو: قفل pacman db.lck، فحص المفاتيح، التنظيف | **manjaro-care** (نسخة مطورة موجودة أصلاً في `scripts/` — لا تُستبدل) | محفوظ هنا كمرجع |
| `update_terminal_logger.sh` | تحديث نظام تسجيل الطرفاة بـ `$HOME` بدل المسارات المطلقة | **workspace-scripts-archive** (هذا المستودع) — مرجع لوحدة الطرفية في manjaro-care | مؤرشف |
| `fix-github-uploader.sh` / `fix-github-uploader-full.sh` | إصلاح مشروع github-file-uploader (Next.js): قتل عمليات dev المنفذة، تحرير منفذ 3000 | مؤرشف — المشروع الأصلي (`~/github-file-uploader`) ليس مستودعاً عاماً | مؤرشف |
| `fix-outline.sh` / `fix-outline-window.sh` / `fix-outline-routing.sh` | إصلاحات عميل Outline VPN (نافذة/توجيه) | مرشح لوحدة الشبكة في **manjaro-care** | مؤرشف |
| `fix-wd-drive.sh` | إصلاح تركيب أقراص Western Digital | مرشح لوحدة الأقراص في **manjaro-care** | مؤرشف |
| `fix-ja-netfilter*.sh` + `setup-ja-netfilter-pycharm.sh` + `install_pycharm_plugins.sh` | تثبيت/إصلاح ja-netfilter وإضافات PyCharm | أدوات JetBrains — مؤرشفة | مؤرشف |
| `fix-prisma-nextjs.sh` | إصلاح بيئة Prisma/Next.js | مؤرشف | مؤرشف |
| `fix-and-build-ja-netfilter.sh`, `fix-ja-netfilter-java25.sh` | بناء ja-netfilter ضد Java 25 | مؤرشف | مؤرشف |
| `install_apps.sh` / `overall_installation.sh` / `overall_update_script.sh` / `setup-manjaro-v4.sh` | تثبيت وتحديث شامل للنظام | مُحلّ محلها بوحدات manjaro-care الـ49 | مؤرشف |
| `manjaro-to-windows11.sh` / `manjaro-win11-ultimate.sh` / `win11-setup.sh` | جسور النقل بين Manjaro وWindows 11 | مؤرشف | مؤرشف |
| `setup-sublime.sh` / `patch_sublime.py` | إعداد وتفعيل Sublime Text | مؤرشف | مؤرشف |
| `manjaro-control-center.py` / `manjaro-ultimate-control.py` | الإصدارات القديمة من مركز التحكم | **manjaro-ultimate-control-center/** (مشروع كامل مضمّن في الأرشيف بمجلداته و.git الخاصة) | مؤرشف |
| `manjaro-audit-20261027-*/` | نتائج تدقيق النظام (منها `errors-and-warnings.txt` المستخدم في تحليل سجلات manjaro-care) | **manjaro-care** → `docs/TERMINAL_LOGS_ANALYSIS.md` | مستشهد به |
| `manjaro-maintenance-reports/2026-10-22/` | جرد حزم من صيانة سابقة | مرجع تاريخي | مؤرشف |

## لماذا هذا المجلد؟

هذه السكربتات كُتبت بين 2026-04 و2026-10 لحل مشاكل حقيقية (موثقة في سجلات الطرفاة)، وبعضها
طوّر لاحقاً إلى مستودعات قائمة: `scanner-fixer` (السكانر)، `manjaro-care` (الصيانة)،
`repo-sync-toolkit` (المزامنة بعد أرشفة `sync-github` في 2026-07-31). أرشفة الجذر هنا تحفظ
التاريخ القابل للاسترجاع دون تلويث المستودعات المطور بها.
