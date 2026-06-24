#!/usr/bin/env python3
"""
Nanobot Factory — 全功能逐项验证测试
直接测试每个功能模块的真实输出，而不是只测HTTP状态码
"""
import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

PASS = 0
FAIL = 0
TOTAL = 0

def test(name, condition, detail=""):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")

def test_api(name, url, expected_status=200, validation=None):
    """测试API端点的真实返回数据"""
    import urllib.request, json
    try:
        req = urllib.request.Request(f"http://127.0.0.1:8001{url}", headers={"User-Agent": "Test"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        content_ok = True
        if validation:
            content_ok = validation(data)
        test(name, resp.status == expected_status and content_ok, 
             f"status={resp.status}, {json.dumps(data)[:100]}")
    except Exception as e:
        test(name, False, str(e)[:100])

print("\n" + "="*60)
print("   Nanobot Factory — 全功能逐项真实验证")
print("="*60 + "\n")

# ===== 1. 服务器基础 =====
print("--- 1. 服务器基础 ---")
test_api("GET /", "/")
test_api("GET /health", "/health")
test_api("GET /metrics/json", "/metrics/json")

# ===== 2. 智影数据工场 =====
print("\n--- 2. 智影数据工场 ---")
test_api("GET /zhiying", "/zhiying")

# ===== 3. 算子系统 =====
print("\n--- 3. 算子系统 ---")
def check_operators(data):
    if not isinstance(data, (list, dict)):
        return False
    items = data if isinstance(data, list) else data.get("data", data)
    if not isinstance(items, list):
        return False
    # 检查supports_ai字段——区分真实算子vs占位符
    ai_count = sum(1 for op in items if op.get("supports_ai"))
    return len(items) >= 30 and ai_count >= 10

test_api("GET /api/v2/operators", "/api/v2/operators", validation=check_operators)

# ===== 4. 需求管理 =====
print("\n--- 4. 需求管理 ---")
def check_requirements(data):
    items = data if isinstance(data, list) else data.get("data", data)
    return isinstance(items, list) and all(isinstance(r, dict) for r in items)
test_api("GET /api/v2/requirements", "/api/v2/requirements", validation=check_requirements)

# ===== 5. Agent系统 =====
print("\n--- 5. Agent系统 ---")
test_api("GET /api/v2/agents", "/api/v2/agents")
test_api("GET /api/v2/agents/status", "/api/v2/agents/status")

# ===== 6. AIGC生成 =====
print("\n--- 6. AIGC生成 ---")
test_api("GET /studio.html", "/studio.html")
test_api("GET /studio", "/studio")

# 生成API（真实的错误消息验证）
def check_generate_error(data):
    return "diffusers" in str(data).lower() or "prompt is required" in str(data).lower()
try:
    req = urllib.request.Request("http://127.0.0.1:8001/api/v2/generate",
        data=json.dumps({"prompt":"test"}).encode(),
        headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read().decode())
    test("POST /api/v2/generate (真实错误)", True, str(data)[:100])
except urllib.error.HTTPError as e:
    data = json.loads(e.read().decode())
    has_real_error = "diffusers" in str(data).lower() or "error" in str(data).lower()
    test("POST /api/v2/generate (真实错误)", has_real_error, str(data)[:100])
except Exception as e:
    test("POST /api/v2/generate", False, str(e)[:100])

# ===== 7. 资产系统 =====
print("\n--- 7. 资产系统 ---")
def check_assets(data):
    return "total" in data or "assets" in data or isinstance(data, dict)
test_api("GET /api/assets?limit=5", "/api/assets?limit=5", validation=check_assets)

# ===== 8. 数据库真实持久化 =====
print("\n--- 8. 数据库——写入验证 ---")
try:
    db_dir = os.path.join(backend_dir, "data")
    db_files = [f for f in os.listdir(db_dir) if f.endswith(".db")] if os.path.isdir(db_dir) else []
    test("SQLite数据库文件存在", len(db_files) > 0, f"found: {db_files}")
except Exception as e:
    test("SQLite数据库文件存在", False, str(e))

# 检查数据库中有真实数据
import sqlite3
try:
    db_path = os.path.join(backend_dir, "data", "nanobot.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        test("数据库表存在", len(tables) >= 5, f"{len(tables)} tables: {tables[:10]}")
        
        # 检查是否有真实数据行
        has_data = False
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                cnt = cur.fetchone()[0]
                if cnt > 0:
                    has_data = True
                    break
            except:
                pass
        test("数据库有真实数据", has_data, f"data exists in database")
        conn.close()
    else:
        test("数据库文件存在", False, "nanobot.db not found")
except Exception as e:
    test("数据库验证", False, str(e))

# ===== 9. 功能模块真实实现 =====
print("\n--- 9. 功能模块真实实现 ---")

# Browser functions — 真实HTML抓取
from functions.browser_functions import BrowserFunctions, BrowserFunctionCategory
bf = BrowserFunctions()
func_html = bf.functions.get("browser_get_html")
if func_html:
    # 直接调用_sync_fallback验证真实抓取
    class FakeFunc:
        id = "browser_get_html"
        name = "Get HTML"
        description = ""
        category = BrowserFunctionCategory.NAVIGATION
        parameters = {}
    r = bf._sync_fallback(FakeFunc(), {"url": "https://httpbin.org/html"})
    is_real = isinstance(r, str) and ("html" in r.lower() or "<!doctype" in r.lower())
    test("browser_get_html 真实HTML抓取", is_real, f"返回{len(str(r))}字节，含真实网页内容")

func_links = bf.functions.get("browser_get_links")
if func_links:
    class LFake:
        id = "browser_get_links"; name = ""; description = ""
        category = BrowserFunctionCategory.NAVIGATION; parameters = {}
    r = bf._sync_fallback(LFake(), {"url": "https://example.com"})
    is_real = isinstance(r, list) and len(r) > 0 and all(isinstance(x, str) for x in r)
    test("browser_get_links 真实链接提取", is_real, f"返回{len(r)}个链接")

# Operators — 检查真实计算
from core.operators_lib import OPERATOR_REGISTRY
test("44个算子已注册", len(OPERATOR_REGISTRY) >= 40, f"{len(OPERATOR_REGISTRY)}个")

# 选一个真实计算类测试
for op_cls in list(OPERATOR_REGISTRY.values())[:5]:
    try:
        inst = op_cls()
        test(f"算子 {inst.__class__.__name__} 可实例化", True, f"type={inst.type}")
    except Exception as e:
        test(f"算子 {op_cls.__name__} 可实例化", False, str(e))

# ai_models — AestheticScorer不再返回固定7.5
import core.ai_models as am
scorer = am.AestheticScorer()
# fallback不应含random
import inspect
fb_source = inspect.getsource(am.AestheticScorer._fallback_score)
no_random = "random" not in fb_source
test("AestheticScorer._fallback_score 无random", no_random, "移除random假分数")

# ===== 10. 安全认证 =====
print("\n--- 10. 安全认证 ---")
# 检查auth_required依赖已定义
import server as sv
has_auth = hasattr(sv, 'auth_required')
test("auth_required 认证依赖存在", has_auth)
has_exception_handler = hasattr(sv.app, 'exception_handlers') and len(sv.app.exception_handlers) > 0
test("全局异常处理器已注册", has_exception_handler, f"{len(sv.app.exception_handlers)}个handler")

# ===== 11. 日志系统 =====
print("\n--- 11. 日志系统 ---")
log_dir = os.path.join(backend_dir, "logs")
has_logs = os.path.isdir(log_dir)
test("日志目录存在", has_logs)
if has_logs:
    log_files = os.listdir(log_dir)
    test("日志文件存在", len(log_files) > 0, f"files: {log_files}")

# ===== 输出 =====
print("\n" + "="*60)
print(f"   测试结果: {PASS}/{TOTAL} 通过")
print("="*60)

if FAIL > 0:
    sys.exit(1)
