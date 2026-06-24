"""P2-1-W1 TestClient smoke — 12 端点 (auth + users + projects + dashboard).

策略:
- 使用 ``IMDF_TEST_MODE=1`` (R9.5 已就绪, JWT 用 dev secret)
- TestClient 命中 FastAPI app, 不开 uvicorn
- 每个端点打印 status + 关键字段
- 验证 User / Project 跨"重启"持久化 (新 SessionLocal 查到上一步写入的数据)
"""
import os
import sys
from pathlib import Path

# ── 测试模式 (必须在 import auth_routes 之前设) ───────────────────────────
os.environ["IMDF_TEST_MODE"] = "1"
os.environ["IMDF_P2_DB_URL"] = ""  # 用默认 data/imdf_p2.db, 不要污染 prod DB
# 但是上面用 IMDF_P2_DB_URL="" 会 fallback 到默认路径, 没问题

_BACKEND = Path(r"D:\Hermes\生产平台\nanobot-factory\backend")
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "imdf"))

from fastapi.testclient import TestClient
from db import SessionLocal
from models import User, Project

# ── 导入 app (先尝试 imdf.api.app, 再 fallback 到 canvas_web) ───────────
try:
    from imdf.api.app import app  # type: ignore
except Exception:
    # fallback: 直接构造 canvas_web app
    from api.canvas_web import app  # type: ignore

client = TestClient(app, raise_server_exceptions=False)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


passed = 0
failed = 0


def _check(name: str, ok: bool, info: str = "") -> None:
    global passed, failed
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}{(' — ' + info) if info else ''}")
    if ok:
        passed += 1
    else:
        failed += 1


# ── 1. health/db ping ─────────────────────────────────────────────────
_section("health")
r = client.get("/api/v1/health")
_check("/api/v1/health", r.status_code == 200, f"status={r.status_code}")

# ── 2. auth: register admin (R9.5 auth_routes — prefix is /auth) ──────
_section("auth flow")
import random
rand = random.randint(100000, 999999)
admin_user = f"smoke_admin_{rand}"
admin_pass = "Test1234!"

r = client.post(
    "/auth/register",
    json={
        "username": admin_user,
        "password": admin_pass,
        "email": f"{admin_user}@smoke.local",
        "role": "admin",
    },
)
ok_reg = r.status_code in (200, 201)
_check("/auth/register", ok_reg, f"status={r.status_code}")

r = client.post(
    "/auth/login",
    json={"username": admin_user, "password": admin_pass},
)
ok_login = r.status_code == 200
token = None
if ok_login:
    body = r.json()
    token = body.get("access_token") or body.get("data", {}).get("access_token")
_check("/auth/login", ok_login and bool(token), f"token={'YES' if token else 'NO'}")

if token:
    r = client.get("/auth/me", headers=_h(token))
    _check("/auth/me", r.status_code == 200, f"status={r.status_code}")
else:
    print("  [SKIP] /auth/me (no token)")

# ── 3. users list/create/update/delete (P2-1-W1 DB-backed) ────────────
_section("users DB")
# 用 token 调用受保护端点 (若 R9.5 已加 auth), 没 token 也能调 (向后兼容)
r = client.get("/api/users?page=1&page_size=20")
_check("/api/users GET", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    j = r.json()
    body = j.get("data", j)
    print(f"    users.total = {body.get('total')}")

new_u = f"smoke_u_{rand}"
r = client.post(
    "/api/users",
    json={"username": new_u, "role": "annotator", "email": f"{new_u}@x", "skills": ["label"]},
)
ok_create_u = r.status_code == 200
created_uid = None
if ok_create_u:
    body = r.json().get("data", r.json())
    created_uid = body.get("id")
    print(f"    created user id={created_uid}")
_check("/api/users POST", ok_create_u, f"status={r.status_code}")

if created_uid:
    r = client.put(f"/api/users/{created_uid}", json={"role": "reviewer"})
    _check(f"/api/users/{created_uid} PUT", r.status_code == 200, f"status={r.status_code}")

    r = client.get(f"/api/users/{created_uid}/audit?limit=5")
    _check(f"/api/users/{created_uid}/audit GET", r.status_code == 200, f"status={r.status_code}")

# duplicate username 409
r = client.post("/api/users", json={"username": new_u, "role": "viewer"})
_check("/api/users POST dup → 409", r.status_code == 409, f"status={r.status_code}")

if created_uid:
    r = client.delete(f"/api/users/{created_uid}")
    _check(f"/api/users/{created_uid} DELETE", r.status_code == 200, f"status={r.status_code}")
    r = client.delete(f"/api/users/{created_uid}")
    _check("/api/users DELETE again → 404", r.status_code == 404, f"status={r.status_code}")

# ── 4. projects list/create/update/delete/members (DB-backed) ──────────
_section("projects DB")
r = client.get("/api/projects?page=1&page_size=20")
_check("/api/projects GET", r.status_code == 200, f"status={r.status_code}")

new_p = f"smoke_p_{rand}"
r = client.post(
    "/api/projects",
    json={"name": new_p, "description": "smoke test", "owner": admin_user, "members": [admin_user]},
)
ok_create_p = r.status_code == 200
created_pid = None
if ok_create_p:
    body = r.json().get("data", r.json())
    created_pid = body.get("id")
    print(f"    created project id={created_pid}")
_check("/api/projects POST", ok_create_p, f"status={r.status_code}")

if created_pid:
    r = client.put(f"/api/projects/{created_pid}", json={"description": "updated", "status": "active"})
    _check(f"/api/projects/{created_pid} PUT", r.status_code == 200, f"status={r.status_code}")
    r = client.get(f"/api/projects/{created_pid}/members")
    _check(f"/api/projects/{created_pid}/members GET", r.status_code == 200, f"status={r.status_code}")
    r = client.delete(f"/api/projects/{created_pid}")
    _check(f"/api/projects/{created_pid} DELETE", r.status_code == 200, f"status={r.status_code}")

# empty name → 400
r = client.post("/api/projects", json={"name": ""})
_check("/api/projects POST empty name → 400", r.status_code == 400, f"status={r.status_code}")

# ── 5. dashboard (5 endpoints, JSON-based) ────────────────────────────
_section("dashboard")
for path in [
    "/api/stats/overview",
    "/api/tasks/recent",
    "/api/notifications",
    "/api/audit/stats",
]:
    r = client.get(path)
    _check(f"{path} GET", r.status_code == 200, f"status={r.status_code}")

# ── 6. 持久化验证 (新 SessionLocal 跨 session 读) ───────────────────────
_section("persistence cross-session")
# 先创建一条 user 留着不删, 验证"重启"后还在
persist_user = f"persist_u_{rand}"
persist_proj = f"persist_p_{rand}"
r = client.post(
    "/api/users",
    json={"username": persist_user, "role": "admin"},
)
_check(f"persist user create", r.status_code == 200)
persist_uid = r.json().get("data", {}).get("id")
r = client.post(
    "/api/projects",
    json={"name": persist_proj, "owner": persist_user},
)
_check(f"persist project create", r.status_code == 200)
persist_pid = r.json().get("data", {}).get("id")

# 现在跨 SessionLocal 验证
s = SessionLocal()
try:
    u_count = s.query(User).count()
    p_count = s.query(Project).count()
    u_in_db = s.query(User).filter(User.id == persist_uid).first() if persist_uid else None
    p_in_db = s.query(Project).filter(Project.id == persist_pid).first() if persist_pid else None
    print(f"  User rows in DB = {u_count} (incl. {persist_user})")
    print(f"  Project rows in DB = {p_count} (incl. {persist_proj})")
    _check("DB has users", u_count > 0, f"{u_count} rows")
    _check("DB has projects", p_count > 0, f"{p_count} rows")
    _check(f"persist user {persist_uid} in DB", u_in_db is not None)
    _check(f"persist project {persist_pid} in DB", p_in_db is not None)
    if u_in_db:
        _check("persist user.username match", u_in_db.username == persist_user)
    if p_in_db:
        _check("persist project.name match", p_in_db.name == persist_proj)
finally:
    s.close()

# 清理持久化测试数据
if persist_uid:
    client.delete(f"/api/users/{persist_uid}")
if persist_pid:
    client.delete(f"/api/projects/{persist_pid}")

# ── 7. users/me (auth-gated) ───────────────────────────────────────────
_section("users/me")
r = client.get("/api/users/me")
_check("/api/users/me no token → 401", r.status_code == 401, f"status={r.status_code}")
if token:
    r = client.get("/api/users/me", headers=_h(token))
    _check("/api/users/me with token → 200", r.status_code == 200, f"status={r.status_code}")

# ── 总结 ────────────────────────────────────────────────────────────────
print()
print(f"=== TOTAL: {passed} PASS, {failed} FAIL ===")
sys.exit(0 if failed == 0 else 1)
