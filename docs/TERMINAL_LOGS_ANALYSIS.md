# تحليل سجلات الطرفاة — مشاكل النظام الفعلية وحلولها

> المصدر: `terminal_logs.tar.gz` (46 جلسة مؤرشفة + جلسة رئيسية 269KB + جلسة نشطة)
> فترة السجلات: 2026-04-02 ← 2026-10-27 | الجهاز: `xorthomson-hpnotebook` (Manjaro)
> أُعدّ هذا التوثيق من المسح الكامل للسجلات بتاريخ 2026-11-19 — كل مشكلة هنا حدثت فعلاً.

---

## 1. فشل مصادقة rclone مع Google Drive (متكرر — حرج للنسخ السحابي)

**الدليل من السجل (2026-04-02، تكرر 6 مرات):**
```
CRITICAL: Failed to create file system for "remote:terminal-logs/":
drive: failed when making oauth client: google: could not find default credentials.
See https://cloud.google.com/docs/authentication/external/set-up-adc
```

**السبب الجذري:** الريموت `remote:` أُضيف للنسخ المجدول (terminal-logs) لكن OAuth لم يكتمل —
rclone لا يجد بيانات اعتماد (لا `rclone.conf` مكتمل ولا `GOOGLE_APPLICATION_CREDENTIALS`).

**الحل:**
```bash
# 1) إنشاء/إكمال الريموت بمسار OAuth التفاعلي (مرة واحدة):
rclone config          # n → اسم remote → drive → أتبع خطوات التفويض بالمتصفح
# 2) التحقق قبل أي مجدول:
rclone about remote:   # يجب أن يعرض المساحة المستعملة
# 3) في سكربتات cron: فشل مبكر صريح بدل تمرير صامت
rclone lsd remote:terminal-logs || { echo "❌ فشل المصادقة"; exit 1; }
```
**الوقاية:** اختبار `rclone about` كأول خطوة في أي سكربت رفع، وتنبيه عند غياب `~/.config/rclone/rclone.conf`.

---

## 2. قفل معلق + فحص متوقف في مستودع Borg على القرص الخارجي

**الدليل من السجل (2026-10-22):**
```
/usr/bin/borg check --repository-only "/run/media/xorthomson/Extreme SSD/backup-…"   (حالة العملية T — متوقفة)
-rwxrwxrwx … lock.exclusive   (ملف قفل بحجم 1MB)
BORG_CACHE_DIR="$HOME/.cache/borg-recovery-test" borg info "$BACKUP"
```

**السبب الجذري:** فحص `borg check --repository-only` طويل على قرص USB أُوقف مؤقتاً (حالة `T`)،
وغلّف القفل الحصري المستودع فمنع أي عملية أخرى.

**الحل:**
```bash
# 1) تأكد أولاً أنه لا توجد عملية borg حية (ولا تقتل القفل قبل ذلك!)
pgrep -af borg
# 2) إن توقفت العملية نهائياً — استأنفها أو أنهِها ثم:
kill -CONT <PID>   # لاستئناف الفحص المتوقف، أو kill -TERM <PID> لإنهائه نظيفاً
# 3) فقط بعد التأكد من لا عملية حية — أزل القفل المعلق بأمان:
borg break-lock "/run/media/xorthomson/Extreme SSD/backup-…"
# 4) أعد الفحص على دفعات مع سجل تقدم:
borg check --repository-only --progress "$BACKUP"
```
**ممارسة جيدة رُصدت في السجل وتُثبّت كقاعدة:** اختبار الاسترجاع في كاش معزول
(`BORG_CACHE_DIR` منفصل) قبل لمس المستودع الأصلي — يمنع تلويث الكاش الرئيسي أثناء التجريب.

---

## 3. صورة Rescuezilla تالفة: خطأ I/O أثناء اختبار السلامة

**الدليل من السجل (2026-10-22):**
```
cat: '…/2026-06-01-0104-img-rescuezilla/sda3.ntfs-ptcl-img.gz.ap': Input/output error  (×2)
RESULT: FAIL — gzip test failed; preserve all image files
```

**السبب الجذري:** قراءة الجزء `.ap` من صورة القرص (قسم NTFS `sda3`) ترجع `Input/output error`
— إما قطاع تالف على "Extreme SSD" أو كابل/منفذ USB غير مستقر، والصورة نفسها قد تكون ناقصة.

**الحل:**
```bash
# 1) افحص صحة القرص الحامل للصور:
sudo smartctl -a /dev/sdX | grep -E "Reallocated|Pending|Uncorrect"
sudo dmesg | grep -iE "usb|sd[a-z]|I/O error" | tail -20
# 2) أنقذ الجزء التالف إلى قرص آخر بدل إعادة قراءته مراراً:
sudo ddrescue -d -r3 "…/sda3.ntfs-ptcl-img.gz.ap" /mnt/other-disk/sda3.ap rescue.log
# 3) أعد اختبار السلامة على النسخة المنقذة، ثم أعد بناء الصورة من الأجزاء:
cat /mnt/other-disk/sda3.ntfs-ptcl-img.gz.a? | gzip -t && echo "OK"
```
**الوقاية:** لا تعتمد على قرص واحد للصور الاحتياطية — نسختان على قرصين، وتشغيل `gzip -t` بعد
كل نسخة (السجل يُظهر أن فاحصهم يفعل ذلك أصلاً ويحتفظ بالملفات عند الفشل — ممتاز، أُبقِ عليه).

---

## 4. ترقية جزئية خطرة: `pacman -Sy` بدون `-u`

**الدليل من السجل:**
```
sudo pacman -Sy --noconfirm      ← ظهرت منفردة في إحدى الجلسات
sudo pacman -Syyu --noconfirm    ← الاستخدام الصحيح في جلسات أخرى
```

**السبب الجذري:** `-Sy` يحدّث فهارس المستودعات دون تحديث الحزم — أي تثبيت بعدها يسحب حزماً
جديدة ضد مكتبات قديمة → كسر نظام كلاسيكي على Manjaro/Arch (`partial upgrade`).

**الحل والقاعدة:**
```bash
# استبدلها دائماً بـ:
sudo pacman -Syu
# وإن احتجت تثبيت حزمة فوراً:
sudo pacman -Syu && sudo pacman -S <package>
```
**الوقاية:** أضف لدوال zshrc الحارسة: `pacman() { [ "$1" = "-Sy" ] && echo "ممنوع -Sy منفردة — استخدم -Syu" && return 1 || command pacman "$@"; }`
(مرشّح لإضافتها كفحص في وحدة `package-manager` بالمشروع).

---

## 5. starship يفشل تحت الطرفات غير التفاعلية (`TERM=dumb`)

**الدليل من السجل (2026-04-02، 3 مرات في جلسات `script(1)`):**
```
[ERROR] - (starship::print): Under a 'dumb' terminal (TERM=dumb).
```

**السبب الجذري:** تهيئة starship تعمل في كل shell حتى غير التفاعلية (تسجيل الجلسات، cron، SSH بدون TTY) فترمي أخطاء.

**الحل:** عند استدعاء starship في `~/.zshrc` / `~/.bashrc`:
```bash
if [[ $- == *i* && "$TERM" != "dumb" && -n "$TERM" ]]; then
  eval "$(starship init zsh)"
fi
```
**الوقاية:** نفس الشرط يُطبق على أي أداة prompt (powerlevel10k، oh-my-posh).

---

## 6. سطر تالف في zshrc يفسد التسجيل التلقائي للأوامر

**الدليل من السجل (أثناء تعديل zshrc — ظهر السطر مقطوعاً):**
```
echo -e "\n## Session: $PS0\n## Command: $BASH_COMMAND\n## Return: $RETRN_VAL" >> ~/terminal_logs/auto_log_$( >
```

**السبب الجذري:** سطر `PROMPT_COMMAND`/` precmd` لسجل الأوامر التلقائي انقطع منتصف `$( )`
— أي shell يقرأ الملف يرتكب خطأ صياغة ويتوقف التسجيل التلقائي.

**الحل:**
```bash
# 1) افحص الصياغة قبل التحميل:
zsh -n ~/.zshrc && bash -n ~/.bashrc
# 2) أعد كتابة الدالة مكتملة (نسخة سليمة موجودة في السجل نفسه):
export PROMPT_COMMAND='RETRN_VAL=$?; logger -t cmdline "$USER|$RETRN_VAL|$BASH_COMMAND"'
# أو في zsh:
precmd() { print -r -- "## $(date +%F_%T) | $? | $ZSH_EVAL_CONTEXT" >> "$HOME/terminal_logs/auto_log.txt"; }
```
**الوقاية:** تحقق نحوي تلقائي لملفات rc بعد كل تعديل (`zsh -n`)، وإبقاء نسخة مرجعية واحدة بدل
الكتل المكررة (السجل يُظهر تعريف `startlog/stoplog/searchlog` 3 مرات بأشكال مختلفة — دمجها).

---

## 7. أداة التدقيق تعمل بلا صلاحيات root فتفشل 6 فحوصات

**الدليل (ملف `manjaro-audit-20261027-140859/errors-and-warnings.txt` المصاحب للسجلات):**
```
[WARNING] Command failed: Btrfs subvolumes (exit 1)
[WARNING] Command failed: Orphan candidates (report only) (exit 1)
[WARNING] Command failed: Detailed package file verification (exit 1)
[WARNING] Command failed: Pacman cache size (exit 1)
[WARNING] Command failed: EFI mount points (exit 1)
Timeshift snapshot listing failed.
```
وفي `btrfs-usage.txt`: `WARNING: cannot read detailed chunk info … run as root`

**السبب الجذري:** تشغيل التدقيق كمستخدم عادي — كل الفحوصات النظامية (btrfs، timeshift، pacman cache، EFI) تحتاج root.

**الحل والوقاية:**
```bash
sudo ./manjaro-audit.sh
# وفي أول السكربت نفسه:
[ "$EUID" -ne 0 ] && { echo "⚠️ شغّل التدقيق بـ sudo — الفحوصات النظامية ستفشل"; }
```

---

## 8. ملاحظات غير حرجة رُصدت في السجلات

| الملاحظة | التفصيل | الإجراء |
|---|---|---|
| `Skipping verification of source file PGP signatures` | بناء AUR بتجاوز تحقق التوقيع | تحقق يدوي من checksum للمصادر، أو استورد مفاتيح المطورين `gpg --recv-keys` |
| `Skipping timeshift-autosnap because only 0 hours have passed` | سلوك طبيعي لمنع تكرار اللقطات | لا شيء — سلوك سليم |
| تثبيت أدوات هندسة عكسية (`radare2 ghidra angr qiling…`) بنجاح | نشاط مقصود | لا شيء |
| `diagnose-outline.sh` موجود في الجذر | سكربت تشخيص Outline VPN | أُرشف في `workspace-scripts-archive` — مرشح لوحدة شبكة هنا |

---

## 9. ممارسات سليمة رُصدت في السجلات (تُثبّت كنمط)

1. **اختبار صور النسخ الاحتياطي بـ `gzip -t` بعد كل نسخ** مع الاحتفاظ بالملفات عند الفشل.
2. **كاش Borg معزول للاختبارات** (`BORG_CACHE_DIR` مستقل) قبل لمس المستودع الأصلي.
3. **تسجيل جلسات الطرفاة تلقائياً** (`startlog/stoplog` + PROMPT_COMMAND) — هو نفسه ما أنتج هذه السجلات وأتاح هذا التحليل.
4. **تاريخ كبير محفوظ للأوامر** (`HISTSIZE=50000`، `HISTFILESIZE=100000`).

---

## الخلاصة التنفيذية

| # | المشكلة | الخطورة | الحل السريع |
|---|---------|---------|-------------|
| 1 | rclone بلا OAuth | حرجة (فشل النسخ السحابي) | `rclone config` + اختبار `rclone about` |
| 2 | قفل Borg معلق + فحص متوقف | عالية | `pgrep borg` ثم `borg break-lock` بعد التأكد |
| 3 | I/O error في صور Rescuezilla | عالية (نسخة احتياطية متضررة) | `smartctl` + `ddrescue` + نسخة ثانية على قرص آخر |
| 4 | `pacman -Sy` منفردة | عالية (خطر كسر النظام) | `-Syu` دائماً + دالة حارسة |
| 5 | starship تحت TERM=dumb | منخفضة | شرط `$TERM` قبل التهيئة |
| 6 | سطر zshrc مقطوع | متوسطة (التسجيل معطّل) | `zsh -n` + إعادة كتابة الدالة |
| 7 | تدقيق بلا root | متوسطة (نتائج ناقصة) | `sudo` + فحص `$EUID` |
| 8 | PGP يتجاهل في بناء AUR | منخفضة | استيراد المفاتيح / تحقق يدوي |
