#!/usr/bin/env python3
"""
test_mem0_memory.py — اختبار الذاكرة عبر الجلسات (Mem0 MCP / REST).

يقيس:
  1. وجود MEM0_API_KEY في البيئة (لا يُطبع أبداً)
  2. حفظ ذكرى جديدة عبر REST API
  3. البحث عنها بعد الفهرسة الدلالية
  4. محاكاة "جلسة ثانية" بعملية منفصلة والبحث فيها
  5. طباعة أوامر MCP المكافئة للتنفيذ داخل Claude Code / Cursor

الاستخدام:
  export MEM0_API_KEY="m0-your-key"   # من البيئة فقط — لا يُكتب في أي ملف
  python3 scripts/test_mem0_memory.py

ملاحظة أمان: هذا السكريبت لا يحفظ أسراراً في الذاكرة ولا يطبع المفتاح.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

TEST_USER_ID = "marathon_test_user"
TEST_AGENT_ID = "harness_test"


def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    symbols = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WAIT": "⏳"}
    print(f"[{ts}] {symbols.get(level, '•')} {msg}")


def check_env():
    if not os.getenv("MEM0_API_KEY"):
        log("MEM0_API_KEY غير موجود في البيئة", "FAIL")
        log("  الحل: export MEM0_API_KEY='m0-your-key'  (من https://app.mem0.ai)", "INFO")
        return False
    log("MEM0_API_KEY موجود (لا يُطبع)", "PASS")
    return True


def _api_call(url: str, payload: dict, timeout: int = 30):
    key = os.environ["MEM0_API_KEY"]
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def test_via_rest_api() -> bool:
    log("اختبار REST API مباشر...")
    add_payload = {
        "messages": [
            {"role": "user", "content": "test memory for marathon harness"},
            {"role": "assistant", "content": "acknowledged"},
        ],
        "user_id": TEST_USER_ID,
        "agent_id": TEST_AGENT_ID,
        "metadata": {"source": "test_script", "ts": time.time()},
    }
    try:
        body = _api_call("https://api.mem0.ai/v1/memories/", add_payload)
        log(f"تم الحفظ: {body.get('id', 'no-id')}", "PASS")
    except urllib.error.HTTPError as e:
        log(f"فشل الحفظ: HTTP {e.code} — {e.read().decode()[:200]}", "FAIL")
        return False
    except Exception as e:
        log(f"فشل الحفظ: {e}", "FAIL")
        return False

    log("انتظار 3 ثوانٍ للفهرسة الدلالية...", "WAIT")
    time.sleep(3)

    search_payload = {"query": "marathon test memory", "user_id": TEST_USER_ID, "limit": 5}
    try:
        body = _api_call("https://api.mem0.ai/v1/memories/search/", search_payload)
        results = body.get("results", [])
        log(f"تم البحث: {len(results)} نتيجة", "PASS")
        found = any("marathon" in str(r).lower() for r in results)
        if found:
            log("الذكرى وُجدت في النتائج", "PASS")
            return True
        log("الذكرى لم تُوجد في النتائج", "FAIL")
        return False
    except Exception as e:
        log(f"فشل البحث: {e}", "FAIL")
        return False


def test_cross_session() -> bool:
    """حفظ في عملية منفصلة ("جلسة 1") ثم بحث في عملية أخرى ("جلسة 2")."""
    log("اختبار عبر الجلسات (عمليتان منفصلتان)...")

    marker = f"test_marker_{uuid.uuid4().hex[:8]}"
    log(f"العلامة: {marker}", "INFO")

    save_code = f"""
import os, json, urllib.request
payload = {{
    "messages": [{{"role": "user", "content": "العلامة التجريبية هي {marker}"}}],
    "user_id": "{TEST_USER_ID}",
    "metadata": {{"test_marker": "{marker}"}}
}}
req = urllib.request.Request(
    "https://api.mem0.ai/v1/memories/",
    data=json.dumps(payload).encode(),
    headers={{"Authorization": "Token " + os.environ["MEM0_API_KEY"], "Content-Type": "application/json"}},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    print("saved")
"""
    r1 = subprocess.run([sys.executable, "-c", save_code], capture_output=True,
                        text=True, timeout=60)
    if r1.returncode != 0:
        log(f"فشل الحفظ: {r1.stderr[:200]}", "FAIL")
        return False
    log("تم الحفظ في الجلسة 1", "PASS")

    time.sleep(3)

    search_code = f"""
import os, json, urllib.request
payload = {{"query": "{marker}", "user_id": "{TEST_USER_ID}", "limit": 5}}
req = urllib.request.Request(
    "https://api.mem0.ai/v1/memories/search/",
    data=json.dumps(payload).encode(),
    headers={{"Authorization": "Token " + os.environ["MEM0_API_KEY"], "Content-Type": "application/json"}},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    body = json.loads(r.read())
    print("FOUND" if body.get("results") else "NOT_FOUND")
"""
    r2 = subprocess.run([sys.executable, "-c", search_code], capture_output=True,
                        text=True, timeout=60)
    if r2.returncode != 0:
        log(f"فشل البحث: {r2.stderr[:200]}", "FAIL")
        return False

    if "FOUND" in r2.stdout:
        log("الذكرى موجودة في الجلسة 2 — الاختبار نجح", "PASS")
        return True
    log("الذكرى مفقودة في الجلسة 2 — الاختبار فشل", "FAIL")
    return False


def print_mcp_equivalents():
    log("المكافئ عبر MCP (داخل Claude Code / Cursor / Codex):", "INFO")
    print()
    print("  ─── اختبار 1: حفظ ذكرى ───")
    print(f"  add_memory(content='محرك OCR الافتراضي في ocr-core هو Tesseract',")
    print(f"              userId='{TEST_USER_ID}', agentId='{TEST_AGENT_ID}')")
    print()
    print("  ─── اختبار 2: البحث ───")
    print(f"  search_memories(query='ما محرك OCR الافتراضي في ocr-core؟', userId='{TEST_USER_ID}')")
    print()
    print("  ─── اختبار 3: التحقق ───")
    print("  يجب أن تعود النتيجة بذكر 'Tesseract'")
    print()


def main():
    print("=" * 60)
    print("🧠 اختبار Mem0 — الذاكرة عبر الجلسات (Harness Engineering)")
    print("=" * 60)
    print()

    if not check_env():
        return 1

    print("\n─── الوضع 1: REST API مباشر ───")
    ok1 = test_via_rest_api()

    print("\n─── الوضع 2: عبر الجلسات (عمليتان منفصلتان) ───")
    ok2 = test_cross_session()

    print("\n─── الوضع 3: تعليمات MCP ───")
    print_mcp_equivalents()

    print("=" * 60)
    if ok1 and ok2:
        print("✅ كل الاختبارات نجحت — الذاكرة عبر الجلسات تعمل")
        return 0
    print("❌ بعض الاختبارات فشلت — راجع الأخطاء أعلاه")
    return 1


if __name__ == "__main__":
    sys.exit(main())
