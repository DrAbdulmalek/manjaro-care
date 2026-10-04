#!/usr/bin/env python3
"""
session-handoff.py — توليد ملخص الجلسة وحفظه في الذاكرة (Mem0 MCP).

يُشغَّل في نهاية كل جلسة عمل (دورة الحياة: Resume → Advance → Handoff). يقوم بـ:
  1. جمع حالة Git (فرع، commits حديثة، تغييرات غير ملتزمة، آخر وسم)
  2. تشغيل بوابات التحقق الخاصة بالمشروع (اختياري — افتراضياً تعمل)
  3. كتابة session-handoff.md (يُستبدل — اللقطة الحالية تحل محل السابقة)
  4. حفظ الملخص في Mem0 (اختياري — إذا MEM0_API_KEY متاح)

الاستخدام:
  python3 scripts/session-handoff.py
  python3 scripts/session-handoff.py --no-tests      # تخطي بوابات التحقق
  python3 scripts/session-handoff.py --no-mem0       # تخطي الحفظ في Mem0
  python3 scripts/session-handoff.py --note "أنهيت X" --next "ابدأ بـ Y"

قواعد الحفظ (AGENTS.md §11.5): لا أسرار أبداً؛ فضّل التحديث على الإضافة؛
اكتب فقط ما سيفيد وكيلًا آخر بعد أسابيع.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ============ الألوان ============
class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

    @staticmethod
    def disable():
        C.GREEN = C.RED = C.YELLOW = C.BLUE = C.BOLD = C.END = ""


if not sys.stdout.isatty():
    C.disable()


def log(msg: str, level: str = "info"):
    icons = {
        "info": f"{C.BLUE}ℹ️{C.END}",
        "ok": f"{C.GREEN}✅{C.END}",
        "warn": f"{C.YELLOW}⚠️{C.END}",
        "err": f"{C.RED}❌{C.END}",
    }
    print(f"{icons.get(level, '•')} {msg}")


# ============ Git ============
def git(*args: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git"] + list(args), cwd=cwd, capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"<git error: {e}>"


def collect_git_state(project_dir: Path) -> dict:
    return {
        "branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_dir),
        "head": git("rev-parse", "--short", "HEAD", cwd=project_dir),
        "recent_commits": git("log", "--oneline", "-5", cwd=project_dir).splitlines(),
        "uncommitted": git("status", "--porcelain", cwd=project_dir).splitlines(),
        "last_tag": git("describe", "--tags", "--abbrev=0", cwd=project_dir) or "—",
    }


# ============ كشف المشروع ============
def detect_project(project_dir: Path) -> str:
    def has(p: str) -> bool:
        return (project_dir / p).exists()

    if has("src/ocr_core") or has("ocr_core"):
        return "ocr-core"
    if has("src/translation_core"):
        return "translation-core"
    if has("src/marathon_suite"):
        return "marathon-suite"
    if has("run_ocr_app.py") and has("app_ocr"):
        return "tg-campaign-toolkit"
    if has("package.json") and has("prisma"):
        return "channel-ops-dashboard"
    if has("PKGBUILD") and has("core"):
        return "manjaro-care"
    if has("Dockerfile.gradio") and has("tests/security"):
        return "omni-medical-suite"
    if has("bot.py") and has("collectors"):
        return "marathon_ted_pipeline"
    if has("cli.py") and has("tests/unit"):
        return "intelli-file-manager"
    if has("src/ocr_processor.py"):
        return "marathon_ted_pipeline"
    return "unknown"


# ============ بوابات التحقق ============
def _run(cmd: list[str], cwd: Path, timeout: int = 240) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        return r.returncode == 0, "\n".join(tail)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def pytest_prefix() -> list[str] | None:
    try:
        r = subprocess.run(["python3", "-m", "pytest", "--version"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return ["python3", "-m", "pytest"]
    except Exception:
        pass
    if subprocess.run(["bash", "-c", "command -v pytest"], capture_output=True).returncode == 0:
        return ["pytest"]
    return None


def run_verification(project_dir: Path, project: str) -> dict:
    """تشغيل بوابة التحقق المناسبة للمشروع."""
    result: dict = {"commands": [], "passed": True}
    cmds: list[tuple[list[str], str, dict | None]] = []

    pt = pytest_prefix()
    env_extra = None
    if project in ("ocr-core", "translation-core", "marathon-suite") and (project_dir / "src").exists():
        env_extra = {"PYTHONPATH": str(project_dir / "src")}

    if project in ("ocr-core", "translation-core", "marathon-suite") and pt:
        cmds.append(([*pt, "tests/", "-q", "--tb=short"], "pytest", env_extra))
    elif project == "manjaro-care" and pt:
        cmds.append(([*pt, "tests/", "-q", "--tb=short"], "pytest", None))
    elif project == "marathon_ted_pipeline":
        if pt:
            cmds.append(([*pt, "tests/", "-q", "--tb=short"], "pytest", None))
        cmds.append((["ruff", "check", "src/", "tests/", "--select", "E9,F63,F7,F82"],
                     "ruff-critical", None))
    elif project == "intelli-file-manager" and pt:
        cmds.append(([*pt, "tests/unit", "-q", "--tb=short"], "pytest-unit", None))
    elif project == "omni-medical-suite" and pt:
        cmds.append(([*pt, "tests/", "-q", "--collect-only", "--tb=short"],
                     "pytest-collect-only", None))
    elif project == "tg-campaign-toolkit":
        cmds.append((["bash", "-c", "err=0; while IFS= read -r f; do "
                      "python3 -c \"import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read())\" \"$f\" || { echo \"broken: $f\"; err=1; break; }; "
                      "done < <(git ls-files '*.py'); exit $err"],
                     "py-syntax", None))
    elif project == "channel-ops-dashboard":
        cmds.append((["bash", "-c", "if [ -d node_modules ]; then npx --no-install tsc --noEmit; "
                     "else echo 'node_modules مفقود — تخطي'; fi"],
                     "tsc", None))
    else:
        result["passed"] = False
        result["commands"].append({"name": "detect", "ok": False, "output": "مشروع غير معروف"})
        return result

    for cmd, name, env in cmds:
        ok, out = _run(cmd, project_dir, timeout=300)
        result["commands"].append({"name": name, "ok": ok, "output": out or "(لا مخرج)"})
        if not ok:
            result["passed"] = False

    return result


# ============ Mem0 ============
def save_to_mem0(summary: str, project: str, note: str = "") -> bool:
    """حفظ الملخص في Mem0 (اختياري — مفتاح من البيئة فقط، لا يُطبع ولا يُكتب)."""
    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        log("MEM0_API_KEY غير موجود — تخطي Mem0 (الذاكرة معطلة)", "warn")
        return False

    user_id = os.getenv("MEM0_USER_ID", "DrAbdulmalek")
    agent_id = os.getenv("MEM0_AGENT_ID", project)

    content = f"[{project}] {note}\n\n{summary}" if note else f"[{project}]\n\n{summary}"

    payload = {
        "messages": [{"role": "user", "content": content}],
        "user_id": user_id,
        "agent_id": agent_id,
        "metadata": {
            "project": project,
            "type": "session_handoff",
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        req = urllib.request.Request(
            "https://api.mem0.ai/v1/memories/",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            log(f"تم الحفظ في Mem0: {body.get('id', 'ok')}", "ok")
            return True
    except urllib.error.HTTPError as e:
        log(f"فشل Mem0: HTTP {e.code} — {e.read().decode()[:200]}", "warn")
        return False
    except Exception as e:
        log(f"فشل Mem0: {e}", "warn")
        return False


# ============ الملخص ============
def build_summary(project: str, git_state: dict, verification: dict,
                  note: str, next_step: str) -> str:
    lines = [
        f"# Session Handoff — {project}",
        "",
        f"**التاريخ**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**الفرع**: `{git_state['branch']}` @ `{git_state['head']}`",
        f"**آخر وسم**: `{git_state['last_tag']}`",
        "",
    ]

    if note:
        lines.extend(["## 📝 ملاحظة الجلسة", "", note, ""])

    lines.extend(["## 📊 حالة التحقق", ""])

    if verification.get("commands"):
        lines.append("| الفحص | النتيجة | المخرج |")
        lines.append("|-------|---------|--------|")
        for cmd in verification["commands"]:
            status = "✅" if cmd["ok"] else "❌"
            output = cmd["output"].replace("|", "\\|")[:100]
            lines.append(f"| {cmd['name']} | {status} | `{output}` |")
        lines.append("")
    else:
        lines.extend(["لم تُشغَّل بوابات التحقق (--no-tests).", ""])

    lines.extend(["## 🔨 آخر الالتزامات", ""])
    for commit in git_state["recent_commits"][:5]:
        lines.append(f"- `{commit}`")
    lines.append("")

    if git_state["uncommitted"]:
        lines.extend(["## ⚠️ تغييرات غير ملتزمة", "", "```"])
        lines.extend(git_state["uncommitted"][:20])
        lines.append("```")
        lines.append("")

    lines.extend(["## ➡️ الخطوة التالية", "", next_step or "<!-- ما يجب أن يفعله الوكيل التالي -->", ""])
    lines.extend(["---", "",
                  "*تم توليد هذا الملف بواسطة `scripts/session-handoff.py` — "
                  "يُستبدل في كل جلسة؛ السجل الكامل في progress.md وMem0.*"])
    return "\n".join(lines)


# ============ Main ============
def main():
    parser = argparse.ArgumentParser(description="توليد session-handoff.md وحفظه في Mem0")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--note", default="", help="ملاحظة الجلسة")
    parser.add_argument("--next", dest="next_step", default="",
                        help="ما يجب أن يفعله الوكيل التالي")
    parser.add_argument("--no-tests", action="store_true", help="تخطي بوابات التحقق")
    parser.add_argument("--no-mem0", action="store_true", help="تخطي الحفظ في Mem0")
    parser.add_argument("--output", type=Path, default=Path("session-handoff.md"))
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    if not (project_dir / ".git").exists():
        log(f"ليس مستودع git: {project_dir}", "err")
        return 1

    print(f"{C.BOLD}═══ Session Handoff ═══{C.END}\n")

    project = detect_project(project_dir)
    log(f"المشروع: {project}", "info")

    git_state = collect_git_state(project_dir)
    log(f"الفرع: {git_state['branch']} @ {git_state['head']}", "info")
    if git_state["uncommitted"]:
        log(f"تغييرات غير ملتزمة: {len(git_state['uncommitted'])} مسار", "warn")

    if args.no_tests:
        verification = {"commands": [], "passed": None}
        log("تخطي بوابات التحقق (--no-tests)", "info")
    else:
        log("تشغيل بوابات التحقق...", "info")
        verification = run_verification(project_dir, project)
        if verification["passed"]:
            log("النتيجة: ✅ نجحت", "ok")
        else:
            log("النتيجة: ❌ فشلت — قاعدة صفرية 3: توقف", "err")

    summary = build_summary(project, git_state, verification, args.note, args.next_step)

    output_path = project_dir / args.output
    output_path.write_text(summary, encoding="utf-8")
    log(f"تم الكتابة: {output_path}", "ok")

    if args.no_mem0:
        log("تخطي Mem0 (--no-mem0)", "info")
    else:
        save_to_mem0(summary, project, args.note)

    print()
    print(f"{C.BOLD}═══ انتهى ═══{C.END}")
    return 0 if verification.get("passed", True) else 2


if __name__ == "__main__":
    sys.exit(main())
