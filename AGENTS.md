# AGENTS.md — manjaro-care | Marathon Projects Harness

> اقرأ هذا الملف بالكامل قبل أي إجراء.
> هذا العقد ملزم لجميع وكلاء الذكاء الاصطناعي (Claude Code, Codex, Cursor, Gemini, وغيرها).
> آخر تحديث: 2026-10-05 | الإصدار: 2.0 | المستودع: `DrAbdulmalek/manjaro-care`
> الدليل المفهومي: [docs/HARNESS.md](docs/HARNESS.md) — يُقرأ مع هذا العقد.

## 1. هذا المستودع وأسطولته

**manjaro-care** — أداة صيانة Manjaro: تنظيف لقطات btrfs/snapper، صحة النظام، تقارير، وواجهة سطح مكتب..

| البند | القيمة |
|-------|--------|
| الحالة | نشط — فرع feature/tests-ci (اختبارات pytest للوحدات) |
| بوابة التحقق | `python3 -m pytest tests/ -q` |
| معيار النجاح | كل الاختبارات خضراء (boot-guard, btrfs, dry-run, ...) |

### أسطولة الماراثون (السياق الموحد)

| المشروع | الوصف | المستودع | الحالة |
|---------|-------|----------|--------|
| **ocr-core** | مكتبة OCR مشتركة (ميثاق الدليل البصري + محركات + تصحيحات عربية) | `DrAbdulmalek/ocr-core` | الواجهة العامة حقيقية (PEP 562) — تصحيحات DEV-extras على فرع |
| **translation-core** | نواة الترجمة: تخطيط، مسرد، ذاكرة ترجمة، اختيار محرك | `DrAbdulmalek/translation-core` | عقد الجسر `build_translation_plan` |
| **marathon_ted_pipeline** | جمع ترجمات TED، معالجتها بقواعد OCR، رفعها إلى Telegram | `DrAbdulmalek/marathon_ted_pipeline` | نشط — قواعد OCR مدمجة + تدقيق visual-evidence |
| **intelli-file-manager** | مدير ملفات ذكي محلي (بحث هجين + تصنيف + RAG) | `DrAbdulmalek/intelli-file-manager` | نشط — بوابة `ocr_gateway` مركزية على ocr-core |
| **marathon-suite** | منسّق الماراثونات: حملات، مصادر، جدولة، بوابات صدق | `DrAbdulmalek/marathon-suite` | v0.2.0 — حملة ortho حية على `@ortho_homs` |
| **tg-campaign-toolkit** | أدوات تنفيذ حملات تيليجرام (سكربتات + بيانات المصادر) | `DrAbdulmalek/tg-campaign-toolkit` | نشط — PR مسودة #4 (سكربتات ortho + بيانات) |
| **channel-ops-dashboard** | لوحة القنوات (Next.js) + محرّر OCR بنمط ABBYY + قاعدة قصاصات تدريب | `DrAbdulmalek/channel-ops-dashboard` | نشط — PR مسودة #2 (edit-ocr v0.2 + تصدير JSONL) |
| **manjaro-care** | أداة صيانة Manjaro (لقطات btrfs/snapper + تقارير) | `DrAbdulmalek/manjaro-care` | نشط — فرع feature/tests-ci |
| **omni-medical-suite** | حزمة طبية شاملة (قواميس + تصحيح + API + Docker) | `DrAbdulmalek/omni-medical-suite` | نشط — بعد مراجعة Category B |

**أنت تعمل الآن في `manjaro-care`** — بوابته وحده معتمدة هنا؛ باقي الصفوف للسياق فقط.

## 2. القواعد الصفرية (لا تُخترق)

1. **main لا يُلمَس مباشرة** — كل العمل على فروع `feat/*` أو `fix/*`، والدمج قرار المالك وحده عبر PR مسودة.
2. **كل ادعاء يحتاج مخرجاً خاماً** — لا تقل "نجح" دون طباعة `pytest` أو `ruff` أو `git rev-parse`.
3. **عند فشل أي بوابة تحقق → توقف فوراً** — لا تكمل، لا "تصلح بسرعة".
4. **كل مرحلة ناجحة = commit مستقل + وسم (`stage-N-complete`)**.
5. **ممنوعات مطلقة**: `force-push`، حذف فروع أو وسوم أو مستودعات، كتابة أسرار في المستودع.
6. **الأسرار تُقرأ من `$ENV_VAR` فقط** — لا تُطبع، لا تُكتب في ملفات، لا تُوضع في روابط.

## 3. الحالة (State)

### 3.1 الملفات الإلزامية
- `feature_list.json` — قائمة المهام والتبعيات وحالة كل مهمة.
- `progress.md` — سجل الجلسات: ماذا أُنجز، ماذا تعطّل، الخطوة التالية.
- `session-handoff.md` — ملخص يُكتب في نهاية كل جلسة ليقرأه الوكيل التالي.

### 3.2 دورة حياة الجلسة

```
Resume → Advance → Handoff

1. اقرأ AGENTS.md + init.sh + feature_list.json + session-handoff.md
   · ابحث في Mem0 عن سياق ذي صلة (انظر القسم 11)
2. اختر مهمة واحدة غير مكتملة من feature_list.json.
3. نفّذ، تحقق (./scripts/verify.sh)، حدّث الحالة.
4. احفظ الدروس المستفادة في Mem0 (انظر القسم 11).
5. اكتب session-handoff.md جديداً:
   python3 scripts/session-handoff.py --note "..." --next "..."
6. Commit.
```

## 4. التحقق (Verification)

### 4.1 بوابة التحقق الموحدة
- شغّل `./init.sh` في **بداية** كل جلسة (بيئة + git + بوابة المشروع).
- شغّل `./scripts/verify.sh` **قبل أي التزام** (أسرار + بوابة المشروع).
- `init.sh` يجب أن يُرجع `exit 0` فقط عند نجاح كل الفحوصات.
- لا تعتمد على "يبدو صحيحاً" — اعتمد على المخرجات الخام.

### 4.2 بوابات الأسطولة

| المشروع | أمر التحقق | المعيار |
|---------|-----------|---------|
| ocr-core | `PYTHONPATH=src python3 -m pytest tests/ -q` | كل الاختبارات خضراء (يتطلب `pip install -e \".[dev]\"`) |
| translation-core | `PYTHONPATH=src python3 -m pytest tests/ -q` | كل الاختبارات خضراء |
| marathon-suite | `PYTHONPATH=src python3 -m pytest tests/ -q` | كل الاختبارات خضراء |
| tg-campaign-toolkit | فحص صياغة بايثون (ast) لكل `.py` المتتبعة | صفر ملفات مكسورة |
| channel-ops-dashboard | `npx tsc --noEmit` (بعد `npm install`) | صفر أخطاء TypeScript |
| manjaro-care | `python3 -m pytest tests/ -q` | كل الاختبارات خضراء | ← **هذا المستودع**
| omni-medical-suite | `python3 -m pytest tests/ -q --collect-only` | collection نظيف (التشغيل الكامل في CI) |
| marathon_ted_pipeline | `python3 -m pytest tests/ -q` + `ruff check src/ tests/ --select E9,F63,F7,F82` | pytest أخضر + ruff حرج نظيف |
| intelli-file-manager | `python3 -m pytest tests/unit -q` | الاختبارات الوحدوية خضراء |

## 5. النطاق (Scope)

### 5.1 يشمل
- core/ وmodules/ وgui/ (PySide6) على سطح المكتب
- اختبارات الوحدات وأوضاع dry-run
- التغليف (PKGBUILD)

### 5.2 لا يشمل
- خدمات سحابية
- OCR أو ترجمة أو قنوات

### 5.3 التبعيات
- مستقل تماماً.

## 6. معايير الجودة

- **لا اختراع حقائق**: أي رقم أو اسم أو رابط بدون مصدر يُحذف.
- **الترخيص أولاً**: قبل إضافة أي مكتبة، تحقق من ترخيصها. لا GPL/AGPL في نواة MIT.
- **الاختبارات أولاً**: أي ميزة جديدة تُضاف مع اختبار لها.
- **RTL للعربية**: أي واجهة نصية يجب أن تدعم `RightToLeft` وتستخدم خطاً عربياً صحيحاً.

## 7. الأدوات المسموحة

| الفئة | الأداة | ملاحظة |
|-------|--------|--------|
| OCR | Tesseract, RapidOCR, PaddleOCR | Apache-2.0 |
| OCR (اختياري) | Surya | أوزان مقيدة تجارياً |
| PDF | pypdfium2, pypdf, pikepdf | متسامحة |
| PDF (تجنّب) | PyMuPDF | AGPL-3.0 — لا تستخدمه في MIT |
| UI | PySide6 | LGPL-3.0 — تجنّب PyQt5 (GPL) |
| تحقق | pytest, ruff, mypy | — |
| ذاكرة | Mem0 REST اختياري / MCP خارجي | انظر القسم 11 |

## 8. أنماط الفشل المعروفة

| النمط | كيف تتجنبه |
|-------|-------------|
| "phantom bug" | لا تبنِ على نصوص معروضة — اقرأ البايتات (`od -c`) |
| اختلاق مصادر | كل ادعاء يحتاج رابطاً — أو يُحذف |
| تدمير بيانات | لا تطبّق `normalize_arabic` على النص المعروض — فقط على مفاتيح المطابقة |
| تجاوز البوابات | لا تكمل بعد فشل بوابة، ولو بدا الخطأ "بسيطاً" |

## 9. أوامر سريعة

```bash
# بوابة الدخول (بداية الجلسة)
./init.sh

# فرع عمل — لا تكتب على main أبداً
git checkout main && git pull
git checkout -b feat/my-feature

# بوابة الجودة قبل كل التزام
./scripts/verify.sh

# تسليم الجلسة (نهاية كل جلسة)
python3 scripts/session-handoff.py --note "..." --next "..."

# بوابة هذا المستودع مباشرة
python3 -m pytest tests/ -q
```

## 10. الاتصال والإبلاغ

عند الانتهاء اكتب تقريراً بالصيغة التالية، وعند الفشل: توقف، اطبع المخرج الخام، واكتب `REASON:` في التقرير.

```
=== SESSION REPORT ===
Project: manjaro-care
Branch: <name>
Status: [COMPLETED/PARTIAL/BLOCKED]
Verified: <command> → <result>
Memories saved: <count>
Next: <what the next session should do>
```

## 11. الذاكرة طويلة المدى (Mem0 — REST اختياري / MCP خارجي)

### 11.1 نظرة عامة

التكامل البرمجي الموجود في هذا المستودع يستخدم Mem0 REST API اختيارياً؛ أما MCP فهو مسار تكامل خارجي موثق للوكلاء الذين يدعمونه.
الذكريات مرتبطة بـ user_id (الافتراضي: `DrAbdulmalek`) وagent_id (= اسم المشروع).
المفتاح من البيئة حصراً: `MEM0_API_KEY` — لا يُطبع ولا يُكتب في أي ملف.
بديل محلي بالكامل (بلا سحابة): OpenMemory MCP.

### 11.2 الأدوات المتاحة (عبر MCP)

| الأداة | الوظيفة |
|--------|---------|
| `add_memory` | حفظ نص أو محادثة لمستخدم/وكيل |
| `search_memories` | بحث دلالي في الذكريات مع فلاتر |
| `get_memories` / `get_memory` | عرض/استرجاع ذكرى أو قائمة |
| `update_memory` | تحديث ذكرى موجودة |
| `delete_memory` / `delete_all_memories` | حذف فردي/جماعي في النطاق المحدد |

### 11.3 متى تستخدم البحث (search_memories)

- في بداية كل جلسة: ابحث عن سياق ذي صلة بالمشروع الحالي.
- عند تبديل السياق: ابحث عن معلومات حول المهمة الجديدة.
- عندما يشير المستخدم إلى عمل سابق: ابحث تلقائياً قبل السؤال.
- قبل بدء مهمة جديدة: تحقق من وجود قرارات أو قيود سابقة.

### 11.4 متى تستخدم الحفظ (add_memory)

- بعد إتمام مهمة: احفظ الدروس المستفادة.
- عند اتخاذ قرار معماري: احفظ القرار وسببه.
- عند اكتشاف قيد: احفظه (مثل: "لا تستخدم PyMuPDF — AGPL في نواة MIT").
- عند تعلم تفضيل: احفظ تفضيل المستخدم.

**ما يجب حفظه**: القرارات المعمارية المهمة، التفضيلات، السياق التصحيحي، القيود الصارمة.
**ما لا يجب حفظه**: الأسرار (مفاتيح API، كلمات مرور، رموز جلسات)، المحتوى المؤقت، البيانات الشخصية الحساسة.

### 11.5 قواعد الحفظ

- لا تعلن عن الاسترجاع: لا تقل "لقد تذكرت..." — استخدم المعلومة مباشرة.
- فضّل `update_memory` على `add_memory` عند تحديث معلومة موجودة.
- اكتب فقط عند الضرورة: اكتب إن كانت المعلومة ستفيد وكيلًا آخر بعد أيام أو أسابيع.
- اربط الذكريات بالمشروع: استخدم agentId = اسم المشروع عند الحفظ.

### 11.6 التكامل مع سير العمل

```
الجلسة تبدأ
    ↓
1. اقرأ AGENTS.md
    ↓
2. search_memories(query="<اسم المشروع> context")
    ↓
3. نفّذ المهمة (+ ./scripts/verify.sh قبل الالتزام)
    ↓
4. add_memory / update_memory للدروس المستفادة
    ↓
5. اكتب session-handoff.md
    ↓
6. Commit (على فرع) → PR مسودة
```

### 11.7 التحقق من الذاكرة

```bash
export MEM0_API_KEY="..."   # من البيئة فقط
python3 scripts/test_mem0_memory.py   # حفظ + بحث + عبر الجلسات
```

## 12. المراجع

- [docs/HARNESS.md](docs/HARNESS.md) — الدليل المفهومي الكامل
- Learn Harness Engineering (MIT، 15 لغة) — منهجية بناء Harness
- Mem0 / OpenMemory — الذاكرة طويلة المدى • LobeHub — فرق الوكلاء • MCP
- القوالب المركزية: `templates/` في `DrAbdulmalek/marathon-suite`



## قاعدة main

- main على GitHub: ممنوع الدفع إليه مباشرة (فروع `feat/*` أو `fix/*` ثم PR مسودة).
- main محلي في مساحة عمل بلا remote: ممنوع الدفع لاحقًا بدون فرع.
- الملفات المشتركة تُثبَّت على main المحلي فقط عند غياب remote كليًا.
- إضافة remote مستقبلًا لا تغير القاعدة: كل محتوى جديد يمر عبر فرع + PR.
