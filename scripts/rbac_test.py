#!/usr/bin/env python3
"""
RBAC Full Permission Test - 11 preset accounts
Tests each account's permitted and forbidden endpoints.

P12-B1: 密码从环境变量解析,不再硬编码。
        每个账号的密码从对应的 ENV var 读,缺失时 fail-fast。
        推荐运行方式:
          set ADMIN_INITIAL_PASSWORD=... (在 .env 里)
          set PROD_LEAD_PASSWORD=... PROD_USER1_PASSWORD=... etc.
          python scripts/rbac_test.py
"""
import json
import secrets
import urllib.request
import urllib.error
import sys
import os

BASE = "http://localhost:8900"

# P12-B1: 11 个预设账号的密码从 env 解析,严禁硬编码。
# ENV 占位符格式: "ENV:<VARNAME>" 表示密码来自 os.environ[VARNAME]。
# admin 的密码统一从 ADMIN_INITIAL_PASSWORD 读 (与 unified_auth.py 一致)。
ACCOUNTS = [
    ("admin",       "ENV:ADMIN_INITIAL_PASSWORD",  "admin",      "system"),
    ("prod_lead",   "ENV:PROD_LEAD_PASSWORD",     "team_lead",  "production"),
    ("qc_lead",     "ENV:QC_LEAD_PASSWORD",       "reviewer",   "production"),
    ("prod_user1",  "ENV:PROD_USER1_PASSWORD",    "annotator",  "production"),
    ("prod_user2",  "ENV:PROD_USER2_PASSWORD",    "annotator",  "production"),
    ("prod_user3",  "ENV:PROD_USER3_PASSWORD",    "annotator",  "production"),
    ("crowd_lead",  "ENV:CROWD_LEAD_PASSWORD",    "team_lead",  "crowdsource"),
    ("crowd_mgr",   "ENV:CROWD_MGR_PASSWORD",     "reviewer",   "crowdsource"),
    ("crowd_qc",    "ENV:CROWD_QC_PASSWORD",      "reviewer",   "crowdsource"),
    ("crowd_user1", "ENV:CROWD_USER1_PASSWORD",   "annotator",  "crowdsource"),
    ("client1",     "ENV:CLIENT1_PASSWORD",       "viewer",     "client"),
]


def _resolve_account_password(password: str, username: str) -> str:
    """P12-B1: 把 ENV:<VARNAME> 占位符解析为真实密码。

    - 普通模式: 缺 env var → 报错并打印生成命令
    - IMDF_TEST_MODE=1: 自动生成 ephemeral random 密码 (与 unified_auth 一致)
    """
    if not password.startswith("ENV:"):
        return password  # 兼容非占位符的写法
    env_name = password[4:]
    pw = os.environ.get(env_name, "").strip()
    if pw:
        return pw
    if os.environ.get("IMDF_TEST_MODE", "").strip() == "1":
        ephemeral = secrets.token_urlsafe(16)
        print(f"[IMDF_TEST_MODE] {username}: ephemeral password = {ephemeral}", file=sys.stderr)
        return ephemeral
    raise RuntimeError(
        f"{env_name} env var is required to bootstrap {username} "
        f"for RBAC testing. Set it in .env or run with IMDF_TEST_MODE=1 "
        f"to use ephemeral passwords. The legacy hardcoded default has "
        f"been removed for security reasons (P12-B1)."
    )

# API endpoints to test with expected access by role
# Format: (method, path, body, description, "allowed_roles")
# "*" means all roles allowed, "" means no access expected
ENDPOINTS = [
    # Auth endpoints (public)
    ("POST", "/auth/login", {"username": "unused", "password": "unused"}, "Login", "*"),
    ("GET", "/auth/me", None, "Get current user", "*"),
    
    # Dataset endpoints
    ("GET", "/api/v1/datasets", None, "List datasets", "admin,team_lead,reviewer,annotator,viewer"),
    
    # Annotation endpoints
    ("POST", "/api/v1/annotations/log", {"dataset_id": "test_rbac", "action": "label", "label": "test"}, "Log annotation", "admin,team_lead,reviewer,annotator"),
    ("GET", "/api/v1/annotations/history", None, "Annotation history", "admin,team_lead,reviewer,annotator,viewer"),
    
    # Quality endpoints
    ("POST", "/api/quality/iaa/cohen-kappa", {"rater1": ["a","b"], "rater2": ["a","b"]}, "Cohen Kappa", "admin,team_lead,reviewer"),
    ("POST", "/api/quality/iaa/report", {"annotations": [{"id":1,"label":"a"}]}, "IAA Report", "admin,team_lead,reviewer"),
    
    # Pipeline endpoints
    ("POST", "/api/quality/pipeline/run", {"items": [{"id": 1}]}, "Run Pipeline", "admin,team_lead"),
    
    # Delivery endpoints
    ("GET", "/api/delivery/", None, "List deliveries", "admin,team_lead,reviewer,viewer"),
    ("POST", "/api/delivery/create", {"name": "rbac_test", "items": [{"id": "1"}]}, "Create delivery", "admin,team_lead"),
    
    # Admin endpoints
    ("GET", "/api/v1/admin/stats", None, "Admin stats", "admin"),
    
    # Eval endpoints
    ("POST", "/api/quality/eval/benchmark-report", {"results": [{"x": 1}], "benchmark": "test"}, "Eval report", "admin,team_lead,reviewer"),
    
    # Classification
    ("POST", "/api/quality/classify/accuracy", {"predictions": {"a":"x"}, "ground_truth": {"a":"x"}}, "Classify accuracy", "admin,team_lead,reviewer"),
    
    # Search
    ("POST", "/api/quality/search/metrics", {"queries": [{"q": "test"}]}, "Search metrics", "admin,team_lead,reviewer"),
    
    # Transfer
    ("POST", "/api/quality/transfer/verify", {"source_path": "/tmp/a", "dest_path": "/tmp/b"}, "Transfer verify", "admin,team_lead"),
    
    # Schemas (public-like)
    ("GET", "/api/quality/schemas", None, "List schemas", "*"),
]

def http_request(method, path, body=None, headers=None):
    """Make HTTP request."""
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, str(e)


def login(username, password):
    """Login and get token."""
    status, body = http_request("POST", "/auth/login", {"username": username, "password": password})
    if status == 200:
        return json.loads(body).get("access_token")
    return None


def register_account(username, password, role):
    """Register account if not exists."""
    status, body = http_request("POST", "/auth/register", {"username": username, "password": password, "role": role})
    if status == 200:
        return True, "created"
    data = json.loads(body)
    if "already exists" in str(data).lower():
        return True, "exists"
    return False, str(data)


def check_permission(role, allowed_str):
    """Check if role is in allowed list."""
    if allowed_str == "*":
        return True
    allowed = [r.strip() for r in allowed_str.split(",")]
    return role in allowed


def main():
    print("=" * 100)
    print("  Nanobot Factory - RBAC Full Permission Test (11 Accounts)")
    print("=" * 100)
    
    # Step 1: Register all accounts
    print("\n--- Phase 1: Register Accounts ---")
    print(f"{'Username':<16} {'Role':<12} {'Password':<20} {'Status':<15}")
    print("-" * 65)
    
    accounts_ready = []
    for username, password, role, team in ACCOUNTS:
        # P12-B1: 解析 ENV:<VARNAME> 占位符
        try:
            resolved_pw = _resolve_account_password(password, username)
        except RuntimeError as e:
            print(f"  [FAIL] {username}: {e}")
            print(f"\n  Aborting RBAC test. Set the required env vars in .env or use IMDF_TEST_MODE=1.")
            sys.exit(2)
        ok, msg = register_account(username, resolved_pw, role)
        status_icon = "✓" if ok else "✗"
        # 打印时隐藏密码 (安全)
        display_pw = "<from-env>" if password.startswith("ENV:") else resolved_pw
        print(f"{status_icon} {username:<14} {role:<12} {display_pw:<20} {msg:<15}")
        if ok:
            accounts_ready.append((username, resolved_pw, role, team))
    
    print(f"\nAccounts ready: {len(accounts_ready)}/11")
    
    # Step 2: Login each account and get tokens
    print("\n--- Phase 2: Login & Token Acquisition ---")
    print(f"{'Username':<16} {'Role':<12} {'Login':<10} {'Token'}")
    print("-" * 60)
    
    tokens = {}
    for username, password, role, team in accounts_ready:
        token = login(username, password)
        status = "✓" if token else "✗"
        token_preview = (token[:20] + "...") if token else "FAILED"
        print(f"{status} {username:<14} {role:<12} {status:<10} {token_preview}")
        if token:
            tokens[username] = {"token": token, "role": role, "team": team}
    
    print(f"\nTokens obtained: {len(tokens)}/11")
    
    # Step 3: Comprehensive RBAC test
    print("\n--- Phase 3: RBAC Permission Matrix ---")
    print(f"\n  Testing {len(ENDPOINTS)} endpoints across {len(tokens)} accounts...\n")
    
    # Print header
    header = f"{'Endpoint':<45} {'Method':<7}"
    for username in sorted(tokens.keys()):
        header += f" {username:<12}"
    print(header)
    print("-" * (60 + 13 * len(tokens)))
    
    results = {}
    for username, info in tokens.items():
        results[username] = {"passed": 0, "failed": 0, "details": []}
    
    for method, path, body, desc, allowed_roles in ENDPOINTS:
        # Build display name
        display = f"{desc} ({path})"
        if len(display) > 44:
            display = display[:41] + "..."
        
        line = f"{display:<45} {method:<7}"
        
        for username in sorted(tokens.keys()):
            info = tokens[username]
            role = info["role"]
            token = info["token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            status, resp_body = http_request(method, path, body, headers)
            
            should_have_access = check_permission(role, allowed_roles)
            has_access = (200 <= status < 300)
            
            if should_have_access and has_access:
                line += f" {'✓':>12}"
                results[username]["passed"] += 1
            elif not should_have_access and not has_access:
                line += f" {'✗':>12}"
                results[username]["passed"] += 1
            elif should_have_access and not has_access:
                line += f" {'!':>12}"
                results[username]["failed"] += 1
                results[username]["details"].append(f"BLOCKED: {method} {path} (status={status})")
            else:  # not should_have_access but has_access
                line += f" {'⚠':>12}"
                results[username]["failed"] += 1
                results[username]["details"].append(f"LEAK: {method} {path} (status={status})")
        
        print(line)
    
    # Step 4: Summary
    print("\n" + "=" * 100)
    print("  RBAC TEST SUMMARY")
    print("=" * 100)
    print(f"\n  Endpoints tested: {len(ENDPOINTS)}")
    print(f"  Accounts tested:  {len(tokens)}")
    print()
    print(f"  {'Username':<16} {'Role':<12} {'Team':<14} {'Passed':<8} {'Failed':<8} {'Rate':<8}")
    print(f"  {'-'*65}")
    
    total_pass = 0
    total_fail = 0
    for username in sorted(tokens.keys()):
        info = tokens[username]
        r = results[username]
        rate = f"{r['passed']}/{r['passed']+r['failed']}" if (r['passed']+r['failed']) > 0 else "N/A"
        pct = f"{100*r['passed']/(r['passed']+r['failed']):.0f}%" if (r['passed']+r['failed']) > 0 else "N/A"
        print(f"  {username:<16} {info['role']:<12} {info['team']:<14} {r['passed']:<8} {r['failed']:<8} {rate} ({pct})")
        total_pass += r['passed']
        total_fail += r['failed']
        
        # Print failure details
        if r['details']:
            for d in r['details']:
                print(f"    → {d}")
    
    print(f"  {'-'*65}")
    print(f"  {'TOTAL':<16} {'':<12} {'':<14} {total_pass:<8} {total_fail:<8}")
    
    # Step 5: Specific E2E endpoint verification
    print("\n--- Phase 4: E2E Endpoint Verification (Fixed) ---")
    
    # Get admin token for verification
    admin_token = tokens.get("admin", {}).get("token")
    if not admin_token:
        print("  ✗ Admin token not available, skipping E2E verification")
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test 1: POST /api/v1/annotations/log (with dataset_id)
    print("\n  [1] POST /api/v1/annotations/log (with dataset_id)")
    status, body = http_request("POST", "/api/v1/annotations/log", 
                                 {"dataset_id": "e2e_ds_001", "action": "label", "label": "cat", "labeler_id": "test"}, headers)
    data = json.loads(body)
    print(f"      Status: {status} → {'✓ PASS' if status==200 else '✗ FAIL'}")
    
    # Test 2: POST /api/quality/iaa/cohen-kappa (with string arrays)
    print("\n  [2] POST /api/quality/iaa/cohen-kappa (with string arrays)")
    status, body = http_request("POST", "/api/quality/iaa/cohen-kappa",
                                 {"rater1": ["positive", "negative", "positive"], "rater2": ["positive", "positive", "positive"]}, headers)
    data = json.loads(body)
    print(f"      Status: {status} → {'✓ PASS' if status==200 else '✗ FAIL'}")
    if status == 200:
        print(f"      Kappa: {data.get('kappa')}, Quality: {data.get('quality')}")
    
    # Test 3: POST /api/delivery/create (with object list)
    print("\n  [3] POST /api/delivery/create (with object list)")
    status, body = http_request("POST", "/api/delivery/create",
                                 {"name": "E2E Delivery", "format": "json", 
                                  "items": [{"id": "1", "label": "cat"}, {"id": "2", "label": "dog"}]}, headers)
    data = json.loads(body)
    print(f"      Status: {status} → {'✓ PASS' if status==200 else '✗ FAIL'}")
    if status == 200:
        print(f"      Delivery ID: {data.get('delivery_id')}")
    
    print("\n" + "=" * 100)
    if total_fail == 0:
        print("  ✅ ALL RBAC TESTS PASSED")
    else:
        print(f"  ⚠ {total_fail} RBAC TEST FAILURES DETECTED")
    print("=" * 100)


if __name__ == "__main__":
    main()
