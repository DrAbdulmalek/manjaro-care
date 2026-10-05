#!/usr/bin/env bash
# verify.sh — بوابة التحقق قبل الالتزام (Harness Engineering v2.0)
#
# يتحقق من: (1) لا أسرار متتبَّعة (2) بوابة جودة المشروع.
# القاعدة الصفرية: عند فشل هذه البوابة → توقف، لا "تصلح بسرعة".
#
# الاستخدام:
#   ./scripts/verify.sh                # كامل: أسرار + بوابة المشروع
#   ./scripts/verify.sh --quick        # أسرار فقط (سريع، قبل commit الصغيرة)
#   ./scripts/verify.sh --format=json  # مخرج JSON للـ CI
#
# الخروج: 0 نجاح | 1 فشل (لا تلتزم قبل الإصلاح والنجاح)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# من scripts/ إلى جذر المستودع (مستوى واحد فقط)
cd "$SCRIPT_DIR/.." || exit 1

QUICK=0
FORMAT="text"
[[ "${1:-}" == "--quick" ]] && QUICK=1
[[ "${1:-}" == "--format=json" ]] && FORMAT="json"
[[ "${2:-}" == "--format=json" ]] && FORMAT="json"

PROJECT="unknown"
CHECKS=()   # "name|ok|output-tail"

if   [[ -d "src/ocr_core" || -d "ocr_core" ]];            then PROJECT="ocr-core"
elif [[ -d "src/translation_core" ]];                      then PROJECT="translation-core"
elif [[ -d "src/marathon_suite" ]];                        then PROJECT="marathon-suite"
elif [[ -f "run_ocr_app.py" && -d "app_ocr" ]];            then PROJECT="tg-campaign-toolkit"
elif [[ -f "package.json" && -d "prisma" ]];               then PROJECT="channel-ops-dashboard"
elif [[ -f "PKGBUILD" && -d "core" ]];                     then PROJECT="manjaro-care"
elif [[ -f "Dockerfile.gradio" && -d "tests/security" ]];  then PROJECT="omni-medical-suite"
elif [[ -f "bot.py" && -d "collectors" ]];                 then PROJECT="marathon_ted_pipeline"
elif [[ -f "cli.py" && -d "tests/unit" ]];                 then PROJECT="intelli-file-manager"
fi

add_check() { CHECKS+=("$1|$2|$3"); }

# ─────────────────────────────────────────────
# 1. فحص الأسرار في الملفات المتتبعة
# ─────────────────────────────────────────────
# أنماط عالية الدقة (بادئة + 20 محرفاً على الأقل) — لا تطابق نصوص الأنماط نفسها
# لأن ما يلي البادئة في هذا الملف يبدأ بـ '[' وليس بمحرف أبجدي رقمي.
SECRET_PATTERNS='ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|m0-[a-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|xox[bp]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{35}'

SECRET_HITS="$(git grep -I -n -E "$SECRET_PATTERNS" -- . 2>/dev/null || true)"
if [[ -n "$SECRET_HITS" ]]; then
    add_check "secrets" "fail" "$(echo "$SECRET_HITS" | head -5)"
    SECRETS_OK=0
else
    add_check "secrets" "pass" "لا أسرار متتبعة"
    SECRETS_OK=1
fi

# ─────────────────────────────────────────────
# 2. بوابة المشروع (تُتخطى في --quick)
# ─────────────────────────────────────────────
GATE_NAME="none"
GATE_OK=1
GATE_OUT="تخطي (--quick)"

PYTEST_BIN=""
if python3 -m pytest --version >/dev/null 2>&1; then PYTEST_BIN="python3 -m pytest";
elif command -v pytest >/dev/null 2>&1; then PYTEST_BIN="pytest"; fi

gate_pytest() {
    # gate_pytest <مسار الاختبارات> [معاملات إضافية...]
    local target="$1"; shift || true
    GATE_NAME="pytest"
    if [[ ! -e "$target" ]]; then
        GATE_OK=0; GATE_OUT="لا يوجد $target — بوابة pytest مطلوبة ولا يمكن تخطيها"
        return 1
    fi
    if [[ -z "$PYTEST_BIN" ]]; then
        GATE_OK=0; GATE_OUT="pytest غير متاح — لا يمكن اعتبار البوابة ناجحة"
        return 1
    fi
    if $PYTEST_BIN "$target" -q --tb=short "$@" >/tmp/verify_gate.log 2>&1; then
        GATE_OK=1; GATE_OUT="$(tail -2 /tmp/verify_gate.log)"
    else
        GATE_OK=0; GATE_OUT="$(tail -4 /tmp/verify_gate.log 2>/dev/null || echo 'pytest غير متاح أو فشل')"
    fi
}

# بوابة محرك Surya (ocr-core فقط) — تخطٍ أنيق عند غياب الحزمة الاختيارية
# تُخزن في فتحة GATE2 منفصلة حتى لا تطغى على نتيجة pytest
GATE2_NAME=""; GATE2_OK=1; GATE2_OUT=""
gate_surya_engine() {
    GATE2_NAME="surya-engine"
    if [[ ! -f src/ocr_core/engines/surya_engine.py ]]; then
        GATE2_OK=1; GATE2_OUT="محرك surya غير موجود على هذا الفرع — تخطي"
        return 0
    fi
    if ! python3 -c "import surya" >/dev/null 2>&1; then
        GATE2_OK=1; GATE2_OUT="surya-ocr غير مثبت (extra اختياري) — تخطي"
        return 0
    fi
    if python3 -c "from ocr_core.engines.surya_engine import SuryaEngine; assert SuryaEngine.name == 'surya'" >/tmp/verify_surya.log 2>&1; then
        GATE2_OK=1; GATE2_OUT="SuryaEngine متاح (0.22.x)"
    else
        GATE2_OK=0; GATE2_OUT="SuryaEngine مكسور: $(tail -2 /tmp/verify_surya.log)"
    fi
}

if [[ $QUICK -eq 0 ]]; then
    case "$PROJECT" in
        ocr-core|translation-core|marathon-suite)
            [[ -d src ]] && export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
            gate_pytest "tests/"
            if [[ "$PROJECT" == "ocr-core" ]]; then
                gate_surya_engine
            fi
            ;;
        manjaro-care)
            gate_pytest "tests/"
            ;;
        marathon_ted_pipeline)
            gate_pytest "tests/"
            GATE_NAME="pytest+ruff-critical"
            if command -v ruff >/dev/null 2>&1; then
                if ! ruff check src/ tests/ --select E9,F63,F7,F82 >/tmp/verify_ruff.log 2>&1; then
                    GATE_OK=0; GATE_OUT="$GATE_OUT | ruff: $(tail -2 /tmp/verify_ruff.log)"
                fi
            fi
            ;;
        intelli-file-manager)
            gate_pytest "tests/unit"
            ;;
        omni-medical-suite)
            gate_pytest "tests/" --collect-only
            GATE_NAME="pytest-collect-only"
            ;;
        tg-campaign-toolkit)
            GATE_NAME="py-syntax"
            err=0
            while IFS= read -r f; do
                python3 -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read(),filename=sys.argv[1])" "$f" 2>/dev/null || { GATE_OUT="صياغة مكسورة: $f"; err=1; break; }
            done < <(git ls-files '*.py')
            if [[ $err -eq 0 ]]; then GATE_OK=1; else GATE_OK=0; fi
            [[ $err -eq 1 ]] || GATE_OUT="صياغة سليمة لكل .py المتتبعة"
            ;;
        channel-ops-dashboard)
            GATE_NAME="tsc"
            if [[ -d node_modules ]]; then
                if npx --no-install tsc --noEmit >/tmp/verify_gate.log 2>&1; then
                    GATE_OK=1; GATE_OUT="$(tail -2 /tmp/verify_gate.log)"
                else
                    GATE_OK=0; GATE_OUT="$(tail -4 /tmp/verify_gate.log)"
                fi
            else
                GATE_OK=0; GATE_OUT="node_modules مفقود — بوابة tsc مطلوبة ولا يمكن اعتبار التحقق ناجحاً"
            fi
            ;;
        *)
            GATE_NAME="none"; GATE_OK=0; GATE_OUT="مشروع غير معروف — لا توجد بوابة تحقق موثوقة"
            ;;
    esac
fi

add_check "gate:$GATE_NAME" "$( [[ $GATE_OK -eq 1 ]] && echo pass || echo fail )" "$GATE_OUT"

# بوابة ثانية اختيارية (Surya في ocr-core)
if [[ -n "$GATE2_NAME" ]]; then
    add_check "gate:$GATE2_NAME" "$( [[ $GATE2_OK -eq 1 ]] && echo pass || echo fail )" "$GATE2_OUT"
fi

# طبقة الذاكرة: ملاحظة إخبارية دائمًا (غيابها لا يحمرّ البوابة)
MEM_NOTE="غير مفعلة في هذا المستودع — تخطي"
if [[ -f memory/decisions.md && -f memory/lessons.md && -f memory/constraints.md ]]; then
    MEM_NOTE="كاملة (decisions + lessons + constraints)"
elif [[ -d memory ]]; then
    MEM_NOTE="جزئية — راجع memory/"
fi
add_check "memory-layer" "pass" "$MEM_NOTE"

# ─────────────────────────────────────────────
# 3. النتيجة
# ─────────────────────────────────────────────
PASSED=$(( ( SECRETS_OK && GATE_OK && GATE2_OK ) ? 1 : 0 ))

if [[ "$FORMAT" == "json" ]]; then
    echo "{"
    echo "  \"project\": \"$PROJECT\","
    echo "  \"quick\": $QUICK,"
    echo "  \"passed\": $PASSED,"
    echo "  \"checks\": ["
    first=1
    for c in "${CHECKS[@]}"; do
        IFS='|' read -r name status out <<< "$c"
        out_escaped="${out//\\/\\\\}"; out_escaped="${out_escaped//\"/\\\"}"
        [[ $first -eq 0 ]] && echo ","
        first=0
        printf '    {"name": "%s", "status": "%s", "output": "%s"}' "$name" "$status" "$out_escaped"
    done
    echo ""
    echo "  ]"
    echo "}"
else
    echo "═══ Harness Verify — $PROJECT ═══"
    for c in "${CHECKS[@]}"; do
        IFS='|' read -r name status out <<< "$c"
        if [[ "$status" == "pass" ]]; then
            echo "✅ $name — $out"
        else
            echo "❌ $name — $out"
        fi
    done
    echo ""
    if [[ $PASSED -eq 1 ]]; then
        echo "✅ البوابة خضراء — يُسمح بالالتزام"
    else
        echo "❌ البوابة حمراء — توقف (قاعدة صفرية 3)"
    fi
fi

exit $(( 1 - PASSED ))
