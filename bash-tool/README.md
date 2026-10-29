# manjaro-care-cli 🩺 (bash-tool)

نسخة الطرفية (bash) من manjaro-care، تعمل بجانب الواجهة الرسومية دون تعارض. الأمر بعد التثبيت: `manjaro-care-cli`.
بُنيت حول مشاكل فعلية ظهرت على جهاز حقيقي، وأُعيدت مراجعتها بعد اختبارها (انظر `CHANGES.md`).

## المشاكل التي تعالجها
- هوك **timeshift-autosnap** يجمّد معاملات pacman (`Select backup device`؛ pacman يشغّل الهوكات بلا لوحة مفاتيح).
- قفل **pamac-daemon** لقاعدة pacman (`db.lck`).
- خدمات عالقة بـ **start-limit-hit**.
- حزم AUR المكسورة بعد ترقية مكتبات (jsoncpp/boost/protobuf…) — كشف عبر `ldd`.
- **libvirtd** فاشل `243/CREDENTIALS` عند ضياع مفتاح المضيف.
- تعارض **TLP** مع **power-profiles-daemon**.
- coredumps ضخمة.

## التثبيت
```bash
git clone https://github.com/DrAbdulmalek/manjaro-care.git
cd manjaro-care/bash-tool
bash install.sh
```
المثبّت لا يستنسخ نسخة ثانية ولا يقبل توكناً كوسيط. الرفع إلى GitHub **معطّل افتراضياً**.

## الاستخدام
| الأمر | الوظيفة |
|---|---|
| `doctor` | فحص صحي، قراءة فقط |
| `fix` | إصلاحات (تسأل قبل كل خطوة خطرة) |
| `clean` | journal، كاش pacman/pamac، يتيمات، coredumps |
| `update` | ترقية مع فحوص قبلية وبعدية وحماية هوك timeshift |
| `all` | doctor → fix → clean → update |
| `sync` | رفع التقارير الآن (مستودع خاص فقط) |
| `last` / `config` | آخر تقرير / إعداد التوكن |

الخيارات: `--auto` (غير تفاعلي، **تُرفض العمليات الخطرة**)، `--yes` (موافقة صريحة على كل شيء)، `--no-push`، `--mirrors`، `--no-color`، `--version`.

## ما يعدّه fix خطراً ويرفضه في `--auto`
إعادة تثبيت الحزم، تعديل إعداد autosnap، توليد مفتاح libvirt جديد، إخفاء power-profiles-daemon، حذف اليتيمات.
أما المسموح تلقائياً فهو: إزالة قفل يتيم (بعد التأكد أن لا عملية تمسكه)، و`reset-failed`، وإيقاف pamac مؤقتاً.

### libvirt (حالة 243/CREDENTIALS)
يتحقق أولاً أن المفتاح لا يُفك تشفيره، ويرفض الإصلاح إن وُجدت أسرار libvirt أخرى (ستضيع)، ثم: نسخة احتياطية → `systemd-creds setup` عند الحاجة → نقل المفتاح القديم → توليد جديد → تحقق (32 بايت) → تشغيل الخدمة.

## التقارير والخصوصية
- تُحفظ في `~/.local/share/manjaro-care-cli/reports` (مستودع git مستقل عن الكود).
- اسم الجهاز واسم المستخدم والتوكن تُحجب من السجلات.
- الرفع (`MC_PUSH=1` أو الأمر `sync`) يتم **فقط إلى مستودع GitHub خاص**؛ يُتحقق عبر API وإلا يُرفض. يمكن تجاوز ذلك بـ `MC_ALLOW_PUBLIC=1` عن علم.
- التوكن عبر `GIT_ASKPASS`: لا يظهر في `ps` ولا في `.git/config`. استخدم fine-grained token مقصوراً على مستودع التقارير.

## الجدولة (اختياري)
وحدة **مستخدم** تشغّل `doctor` فقط كل أحد 21:00 (لا تحديث ولا إصلاح دون إشراف):
```bash
mkdir -p ~/.config/systemd/user
cp systemd/manjaro-care-cli.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now manjaro-care-cli.timer
```

## استكشاف الأخطاء
| المشكلة | الحل |
|---|---|
| `could not lock database` | `manjaro-care-cli fix` |
| pacman يعلق عند `Select backup device` | `fix` ثم `update` (يعطّل الهوك مؤقتاً ويعيده) |
| الهوك بقي معطّلاً بعد انقطاع | `doctor` يبلغ عنه مع أمر الاستعادة |
| `start-limit-hit` | `fix` (reset-failed) |
| تطبيق AUR توقف بعد ترقية | `fix` يكشف ويعرض إعادة البناء (`paru -S --rebuild`) |
| `libvirtd` 243/CREDENTIALS | `fix` |
