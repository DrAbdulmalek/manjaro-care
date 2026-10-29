# manjaro-care (CLI) 🩺

> نسخة الطرفية الخفيفة (bash) داخل مستودع manjaro-care — تعمل بجانب أداة الواجهة الرسومية PyQt5 الموجودة في جذر المستودع دون أي تعارض. الأمر بعد التثبيت: `manjaro-care-cli`.

أداة صيانة شاملة لنظام **Manjaro Linux** تُجري الفحص والإصلاح والتنظيف والتحديث، ثم **ترفع تقرير كل تشغيل تلقائياً** إلى هذا المستودع على GitHub تحت `reports/`، كي تبقى سجلات صحة جهازك مؤرشفة وقابلة للمراجعة من أي مكان.

تم بناء الأداة حول المشاكل الفعلية التي ظهرت على الجهاز المستهدف:

- **هوك `timeshift-autosnap` يجمّد معاملات pacman** بسؤال `Select backup device` في وضع btrfs (لاحظ أن `--hookdir` لا يحل المشكلة لأن المجلد الافتراضي `/usr/share/libalpm/hooks` يبقى فعّالاً دائماً).
- **قفل `pamac-daemon`** لقاعدة pacman (`db.lck`) أثناء عمليات التثبيت اليدوية.
- **خدمات تعلق بحالة `start-limit-hit`** بعد فشل متكرر (مثل `orthanc.service` مع `libjsoncpp.so.26: not found`).
- **تعطل حزم AUR** بعد ترقيات المكتبات (jsoncpp / boost / protobuf / icu / openssl) — بنفس نمط انهيار Orthanc 1.13.0.
- **`libvirtd` فاشل بسبب `status=243/CREDENTIALS`** عند فقدان `/var/lib/systemd/credential.secret`.
- **تعارض TLP مع `power-profiles-daemon`** وأخطاء `intel_pstate: Device or resource busy`.
- **ملفات coredump ضخمة** من تطبيقات مثل anydesk وplasmashell.

---

## المتطلبات

- Manjaro Linux (أو أي توزيعة Arch-based، مع تحذير بسيط عند التشغيل)
- `git` و`curl` و`sudo`
- توكن GitHub بصلاحية `repo` (classic) أو `Contents: Read and write` (fine-grained)

## التثبيت

```bash
git clone https://github.com/DrAbdulmalek/manjaro-care.git
cd manjaro-care
chmod +x bash-tool/install.sh
bash bash-tool/install.sh
```

سيقوم المثبّت بـ:

1. استنساخ/تحديث المستودع في `~/manjaro-care-cli`
2. طلب توكن GitHub والتحقق منه وحفظه في `~/.config/manjaro-care-cli/token` بصلاحيات `600` (مجلد إعدادات مستقل عن أداة الواجهة الرسومية)
3. ربط الأمر `manjaro-care-cli` في `~/.local/bin`
4. تجربة تشغيل سريعة للتأكد من سلامة التثبيت

> ملاحظة: التوكن لا يُخزَّن أبداً داخل `.git/config` ولا يُرفع مع التقارير — يُستخدم لحظياً عند الدفع ويُحجب من كل مخرجات السجل.

## الاستخدام

```bash
manjaro-care-cli              # القائمة التفاعلية (1-8)
manjaro-care-cli doctor       # فحص صحي شامل — للقراءة فقط، لا يغيّر شيئاً
manjaro-care-cli fix          # إصلاح المشاكل المكتشفة (يطلب sudo عند الحاجة)
manjaro-care-cli clean        # تنظيف الكاش واليتيمات وjournal وcoredumps
manjaro-care-cli update       # ترقية النظام مع فحوصات قبلية وبعدية
manjaro-care-cli all          # دورة كاملة: doctor → fix → clean → update
manjaro-care-cli sync         # رفع التقارير المعلّقة إلى GitHub الآن
manjaro-care-cli last         # عرض ملخص آخر تقرير
manjaro-care-cli config       # تجديد/تغيير توكن GitHub
manjaro-care-cli --auto       # وضع صامت غير تفاعلي — للجدولة
```

خيارات إضافية:

| الخيار | الوظيفة |
|--------|---------|
| `--auto` | وضع غير تفاعلي بقيم آمنة (للـ timer وcron) |
| `--yes` | الموافقة على كل الأسئلة التفاعلية |
| `--no-push` | تعطيل الرفع إلى GitHub لهذه الجلسة |
| `--mirrors` | ترتيب المرايا قبل التحديث (`pacman-mirrors --fasttrack 5`) |
| `--no-color` | تعطيل الألوان |

## ماذا تفعل كل وحدة؟

### doctor — الفحص الصحي (قراءة فقط)
معلومات النظام، استخدام الأقراص (تحذير فوق 85%)، الوحدات الفاشلة، أخطاء journal للإقلاع الحالي، سلامة ملفات حزم pacman (`-Qk`)، الحزم اليتيمة والأجنبية، **مسح المكتبات المفقودة في ثنائيات AUR عبر ldd**، أحجام الكاش، حالة Timeshift في الوضع المبرمَج (`--scripted`)، حالة pamac، تعارض الطاقة، libvirtd، الشبكة، وعدد التحديثات المتاحة وملفات `.pacnew`.

### fix — الإصلاحات
1. إزالة قفل pacman اليتيم بأمان (يتحقق أولاً أن لا عملية حية تمسكه، ويوقف pamac مؤقتاً إن لزم — ويعيده تلقائياً عند الخروج).
2. `systemctl reset-failed` لكل وحدة فاشلة (يزيل `start-limit-hit`) مع خيار محاولة تشغيلها.
3. إعادة تثبيت الحزم الناقصة الملفات (`pacman -S --needed`).
4. كشف المكتبات المفقودة في حزم AUR واقتراح إعادة البناء عبر `paru`/`yay` (بموافقة صريحة، ولا يُنفَّذ في الوضع التلقائي).
5. **حل مشكلة هوك timeshift**: كتابة `"backup": false` في `/etc/timeshift-autosnap.conf` (مع نسخة احتياطية من الملف) كي لا تعلق معاملات pacman، أو الاعتماد على الحماية المؤقتة في وحدة update.
6. تشغيل `systemd-creds setup` وإقلاع `libvirtd` عند فقدان ملف الاعتمادات.
7. إخفاء (mask) `power-profiles-daemon` وإعادة تشغيل TLP عند التعارض.

### clean — التنظيف
تقليم journal (بحد 200م / 30 يوماً)، كاش pacman مع الاحتفاظ بآخر نسختين (`paccache -rk2 -ruk0`)، كاش pamac، الحزم اليتيمة (`pacman -Rns`)، حذف coredumps الأقدم من 7 أيام عند تجاوز 100م، و`systemd-tmpfiles --clean` — مع عرض المساحة المحررة في النهاية.

### update — التحديث
فحص المساحة (يتوقف إن كانت أقل من 3G)، التأكد من خلوه القفل، إيقاف pamac مؤقتاً، **تعطيل مؤقت لهوك timeshift-autosnap في الوضع غير التفاعلي** (مع إعادة تلقائية عند الخروج)، ثم `pacman -Syu`، وبعدها: كشف تحديث النواة (تنبيه إعادة تشغيل + DKMS)، كشف ترقيات المكتبات الحرجة (اقتراح `manjaro-care-cli fix` لفحص ثنائيات AUR)، وعدّ ملفات `.pacnew` مع اقتراح `sudo pacdiff`.

## التقارير و GitHub

بعد كل تشغيل تُنشأ مجلدات بهذا الشكل:

```
reports/
└── 2026-10-29/
    ├── 031502-doctor/
    │   ├── log.txt      ← المخرجات الكاملة (منقّاة من التوكن)
    │   └── summary.md   ← ملخص مفهوم مع التحذيرات
    └── 032201-all/
        ├── log.txt
        └── summary.md
```

- الرفع يتم **تلقائياً بعد كل تشغيل** (commit + push إلى فرع `main`)، وعند الفشل بسبب الشبكة تبقى الالتزامات محلياً وتُرفع في أول مزامنة ناجحة.
- يُحفظ آخر **150 تقريراً** فقط افتراضياً (عدّل `MC_KEEP_REPORTS` في `~/.config/manjaro-care-cli/config`).
- السجلات تُكتب بالإنجليزية كي تبقى قابلة للقراءة في أي طرفية ومتصفح (مشاكل اتجاه النص العربي في الطرفيات)، بينما القائمة التفاعلية ثنائية اللغة.

## الجدولة التلقائية (اختياري)

الوحدة المرفقة في `systemd/` تشغّل صيانة كاملة صامتة كل يوم أحد 21:00:

```bash
sed 's/REPLACE_USER/'$USER'/g' systemd/manjaro-care-cli.service | sudo tee /etc/systemd/system/manjaro-care-cli.service
sudo cp systemd/manjaro-care-cli.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now manjaro-care-cli.timer
```

الخدمة تعمل باسم root (لأن pacman والتنظيف يحتاجانه)، تقرأ التوكن من إعدادات مستخدمك، وتعيد ملكية التقارير إليك بعد كل تشغيل. لجعلها يومية غيّر السطر `OnCalendar` إلى `*-*-* 21:00:00`.

## الأمان

- التوكن في `~/.config/manjaro-care-cli/token` بصلاحيات `600` ولا يُكتب في أي مكان آخر.
- كل مخرجات السجل تمر عبر مرشّح يحجب التوكن قبل العرض أو الأرشفة.
- `.gitignore` يمنع رفع أي ملفات توكن بالخطأ.
- **مهم:** التوكن الذي استُخدم أثناء إعداد هذه الأداة تمت مشاركته في محادثة نصية — اعتبره مكشوفاً. أنشئ توكناً جديداً بصلاحية `repo` فقط، بدّله عبر `manjaro-care-cli config`، ثم ألغِ القديم من https://github.com/settings/tokens.

## استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| `error: could not lock database` | `manjaro-care-cli fix` — يوقف pamac ويزيل القفل اليتيم بأمان |
| pacman يعلق عند `Select backup device` | `manjaro-care-cli fix` ثم `fix` يكتب `backup:false`؛ و`update` يحمي الهوك مؤقتاً تلقائياً |
| `start-limit-hit` لخدمة ما | `manjaro-care-cli fix` — الخيار 2 يعمل reset-failed ويعيد المحاولة |
| تطبيق AUR توقف بعد ترقية مكتبة | `manjaro-care-cli fix` — الخيار 4 يكتشف الثنائيات المكسورة ويعيد بناءها |
| `libvirtd` فاشل (243/CREDENTIALS) | `manjaro-care-cli fix` — الخيار 6 ينشئ credential.secret ويشغّله |
| فشل رفع التقارير | `manjaro-care-cli sync` بعد استعادة الشبكة، أو جدّد التوكن بـ `manjaro-care-cli config` |
