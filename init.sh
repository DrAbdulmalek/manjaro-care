#!/usr/bin/env bash
# init.sh — بوابة الدخول الموحدة (Harness Engineering v2.0)
#
# يُشغَّل في بداية كل جلسة قبل أي عمل. يكتشف المشروع تلقائياً،
# يتحقق من البيئة وملفات الحالة، ويشغّل بوابة التحقق الخاصة بالمشروع.
#
# الاستخدام:
#   ./init.sh                 # تحقق كامل (بيئة + git + بوابة المشروع)
#   ./init.sh --quick         # تحقق سريع (بلا اختبارات)
#   ./init.sh --mem0          # + فحص مفتاح Mem0
#   ./init.sh --help
#
# أكواد الخروج:
#   0  كل الفحوصات نجحت
#   1  فشل فحص واحد أو أكثر (بوابة) — توقف ولا تكمل
#   2  بيئة ناقصة (أدوات مفقودة)
#
# آمن للاستخدام المتكرر: يقرأ ويتحقق فقط، لا يعدّل أي ملف.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT="unknown"
EXIT_CODE=0
QUICK=0
CHECK_MEM0=0
GATE_RAN=0

if [[ -t 1 ]]; then
    GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'; BLUE='\033[94m'; BOLD='\033[1m'; END='\033[0m'
else
    GREEN=''; RED=''; YELLOW=''; BLUE=''; BOLD=''; END=''
fi

log_info() { echo -e "${BLUE}ℹ️  $*${END}"; }
log_ok()   { echo -e "${GREEN}✅ $*${END}"; }
log_warn() { echo -e "${YELLOW}⚠️  $*${END}"; }
log_err()  { echo -e "${RED}❌ $*${END}"; EXIT_CODE=1; }
log_head() { echo -e "\n${BOLD}── $* ──${END}"; }

for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=1 ;;
        --mem0)  CHECK_MEM0=1 ;;
        --help)
            cat <<EOF
init.sh — بوابة الدخول الموحدة (Harness Engineering)

الاستخدام:
  ./init.sh                تحقق كامل
  ./init.sh --quick        تحقق سريع (بلا اختبارات)
  ./init.sh --mem0         + فحص MEM0_API_KEY
  ./init.sh --help         هذه المساعدة

الخروج:
  0  نجاح | 1 فشل بوابة (توقف) | 2 بيئة ناقصة
EOF
            exit 0 ;;
        *) log_warn "معامل غير معروف: $arg" ;;
    esac
done

echo -e "${BOLD}═══════════════════════════════════════════════════${END}"
echo -e "${BOLD}  🚀 Harness Init — بوابة الدخول الموحدة${END}"
echo -e "${BOLD}═══════════════════════════════════════════════════${END}"
echo ""
echo -e "  📁 المجلد: $SCRIPT_DIR"
echo -e "  🕐 الوقت:  $(date '+%Y-%m-%d %H:%M %Z')"
echo ""

# ─────────────────────────────────────────────
# 1. كشف المشروع
# ─────────────────────────────────────────────
log_head "1. كشف المشروع"

if   [[ -d "src/ocr_core" || -d "ocr_core" ]];            then PROJECT="ocr-core"
elif [[ -d "src/translation_core" ]];                      then PROJECT="translation-core"
elif [[ -d "src/marathon_suite" ]];                        then PROJECT="marathon-suite"
elif [[ -f "run_ocr_app.py" && -d "app_ocr" ]];            then PROJECT="tg-campaign-toolkit"
elif [[ -f "package.json" && -d "prisma" ]];               then PROJECT="channel-ops-dashboard"
elif [[ -f "PKGBUILD" && -d "core" ]];                     then PROJECT="manjaro-care"
elif [[ -f "Dockerfile.gradio" && -d "tests/security" ]];  then PROJECT="omni-medical-suite"
elif [[ -f "bot.py" && -d "collectors" ]];                 then PROJECT="marathon_ted_pipeline"
elif [[ -f "cli.py" && -d "tests/unit" ]];                 then PROJECT="intelli-file-manager"
elif [[ -f "src/ocr_processor.py" ]];                      then PROJECT="marathon_ted_pipeline"
fi

if [[ "$PROJECT" == "unknown" ]]; then
    log_err "مشروع غير معروف — لا توجد بوابة تحقق موثوقة"
else
    log_ok "المشروع: $PROJECT"
fi

# ─────────────────────────────────────────────
# أدوات مشتركة
# ─────────────────────────────────────────────
PYTEST_BIN=""
if python3 -m pytest --version >/dev/null 2>&1; then
    PYTEST_BIN="python3 -m pytest"
elif command -v pytest >/dev/null 2>&1; then
    PYTEST_BIN="pytest"
fi

# ─────────────────────────────────────────────
# 2. حالة Git
# ─────────────────────────────────────────────
log_head "2. حالة Git"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    log_err "ليس مستودع git"
else
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    HEADSHA="$(git rev-parse --short HEAD)"
    log_ok "الفرع: $BRANCH @ $HEADSHA"

    case "$BRANCH" in
        main|master) log_warn "أنت على $BRANCH — القاعدة الصفرية: لا تعمل مباشرة عليه؛ افصل فرع feat/* أو fix/*" ;;
        *) log_ok "فرع عمل — سليم" ;;
    esac

    UNCOMMITTED="$(git status --porcelain | wc -l)"
    if [[ "$UNCOMMITTED" -gt 0 ]]; then
        log_warn "تغييرات غير ملتزمة: $UNCOMMITTED مسار"
    else
        log_ok "شجرة نظيفة"
    fi
fi

# ─────────────────────────────────────────────
# 3. الأدوات المتاحة
# ─────────────────────────────────────────────
log_head "3. الأدوات المتاحة"

check_tool() {
    local name="$1" cmd="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        log_ok "$name: $(command -v "$cmd")"
    else
        log_warn "$name غير مثبت"
    fi
}

check_tool "Python" "python3"
check_tool "git" "git"
if [[ -n "$PYTEST_BIN" ]]; then log_ok "pytest: $PYTEST_BIN"; else log_warn "pytest غير متاح"; fi
case "$PROJECT" in
    marathon_ted_pipeline|ocr-core) check_tool "ruff" "ruff" ;;
    channel-ops-dashboard)          check_tool "node" "node"; check_tool "npm" "npm" ;;
esac

# ─────────────────────────────────────────────
# 4. بوابات التحقق
# ─────────────────────────────────────────────
run_pytest() {
    # run_pytest <مسار الاختبارات> [معاملات إضافية...]
    local target="$1"; shift || true
    if [[ ! -e "$target" ]]; then
        log_err "لا يوجد $target — بوابة pytest مطلوبة ولا يمكن تخطيها"
        return 1
    fi
    if [[ -z "$PYTEST_BIN" ]]; then
        log_err "pytest غير متاح — لا يمكن اعتبار البوابة ناجحة"
        return 1
    fi
    log_info "تشغيل: $PYTEST_BIN $target $*"
    if $PYTEST_BIN "$target" "$@" 2>&1 | tail -6; then
        return 0
    else
        return 1
    fi
}

py_syntax_check() {
    # فحص صياغة كل ملفات .py المتتبعة (بلا استيراد ولا كتابة bytecode)
    local err=0 count=0 f
    while IFS= read -r f; do
        count=$((count + 1))
        if ! python3 -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read(),filename=sys.argv[1])" "$f" 2>/dev/null; then
            log_err "صياغة بايثون مكسورة: $f"
            err=1
        fi
    done < <(git ls-files '*.py')
    log_info "فحص صياغة: $count ملف .py"
    return $err
}

if [[ $QUICK -eq 1 ]]; then
    log_head "4. بوابات التحقق (سريع)"
    log_info "تم التخطي بـ --quick"
else
    log_head "4. بوابات التحقق"
    GATE_RAN=1

    case "$PROJECT" in
        ocr-core)
            [[ -d src ]] && export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
            run_pytest "tests/" -q --tb=short || log_err "بوابة ocr-core فشلت (قد تحتاج: pip install -e '.[dev]')"
            ;;

        translation-core)
            [[ -d src ]] && export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
            run_pytest "tests/" -q --tb=short || log_err "بوابة translation-core فشلت"
            ;;

        marathon-suite)
            [[ -d src ]] && export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
            run_pytest "tests/" -q --tb=short || log_err "بوابة marathon-suite فشلت"
            ;;

        tg-campaign-toolkit)
            py_syntax_check || log_err "بوابة الصياغة فشلت"
            ;;

        channel-ops-dashboard)
            if [[ -d node_modules ]]; then
                log_info "تشغيل tsc --noEmit..."
                if npx --no-install tsc --noEmit 2>&1 | tail -5; then
                    log_ok "TypeScript سليم"
                else
                    log_err "tsc وجد أخطاء"
                fi
            else
                log_err "node_modules مفقود — بوابة tsc مطلوبة ولا يمكن اعتبار التحقق ناجحاً"
            fi
            ;;

        manjaro-care)
            run_pytest "tests/" -q --tb=short || log_err "بوابة manjaro-care فشلت"
            ;;

        omni-medical-suite)
            # بوابة هيكلية (collection يجري الاستيرادات ويكشف الكسر) — التشغيل الكامل في CI
            run_pytest "tests/" -q --collect-only --tb=short || log_err "بوابة الهيكل (collect-only) فشلت"
            ;;

        marathon_ted_pipeline)
            run_pytest "tests/" -q --tb=short || log_err "بوابة pytest فشلت"
            if command -v ruff >/dev/null 2>&1; then
                log_info "تشغيل ruff (حرج فقط)..."
                if ruff check src/ tests/ --select E9,F63,F7,F82 2>&1 | tail -3; then
                    log_ok "ruff نظيف"
                else
                    log_err "ruff وجد أخطاء حرجة"
                fi
            else
                log_warn "ruff غير مثبت — تخطي الفحص الحرج"
            fi
            ;;

        intelli-file-manager)
            run_pytest "tests/unit" -q --tb=short || log_err "بوابة unit فشلت"
            ;;

        unknown)
            log_err "مشروع غير معروف — لا توجد بوابة تحقق موثوقة"
            ;;
    esac
fi

# ─────────────────────────────────────────────
# 5. Mem0 (اختياري)
# ─────────────────────────────────────────────
if [[ $CHECK_MEM0 -eq 1 ]]; then
    log_head "5. الذاكرة (Mem0)"
    if [[ -z "${MEM0_API_KEY:-}" ]]; then
        log_warn "MEM0_API_KEY غير موجود — الذاكرة طويلة المدى معطلة"
        log_info "  احصل على مفتاح من https://app.mem0.ai ثم: export MEM0_API_KEY=..."
    else
        log_ok "MEM0_API_KEY موجود (الطول: ${#MEM0_API_KEY})"
    fi
fi

# ─────────────────────────────────────────────
# 6. ملفات الحالة (Harness)
# ─────────────────────────────────────────────
log_head "6. ملفات الحالة (Harness)"

for file in "AGENTS.md" "feature_list.json" "progress.md" "session-handoff.md"; do
    if [[ -f "$file" ]]; then
        log_ok "$file موجود"
    else
        log_warn "$file مفقود — الوكيل سيبدأ أعمى؛ انظر docs/HARNESS.md"
    fi
done

# ─────────────────────────────────────────────
# الخلاصة
# ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${END}"
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}  ✅ كل الفحوصات نجحت — جاهز للعمل ($PROJECT)${END}"
else
    echo -e "${RED}${BOLD}  ❌ بعض الفحوصات فشلت — قاعدة صفرية 3: توقف ولا تكمل${END}"
fi
echo -e "${BOLD}═══════════════════════════════════════════════════${END}"
echo ""

exit $EXIT_CODE
