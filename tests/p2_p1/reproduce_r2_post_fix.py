"""R2 reproducer script — confirms the R2-09 / R2-NEW-01 / R2-NEW-02
exploits no longer succeed against the P21 P2 P1 fix.

Usage: python reproduce_r2_post_fix.py
"""
import os
os.environ.setdefault("JWT_SECRET", "x" * 64)
os.environ.setdefault("IMDF_TEST_MODE", "1")
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

print("=" * 60)
print("R2-09 reproducer (no-auth admin creation)")
print("=" * 60)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.production import router

app = FastAPI()
app.include_router(router)
with TestClient(app) as c:
    r = c.post("/api/v2/users", json={"username": "attacker", "role": "admin"})
    body_text = r.text
    leak = "nbk-" in body_text.lower()
    print(f"  POST /api/v2/users (no auth) -> {r.status_code}")
    print(f"  Body (truncated): {body_text[:200]}")
    print(f"  api_key leaked? {leak}   <-- must be False")
    print(f"  RESULT: {'FAIL' if r.status_code != 401 or leak else 'PASS'}")

print()
print("=" * 60)
print("R2-NEW-02 reproducer (XSS in error body)")
print("=" * 60)
from common.error_handler import _build_error_body
body = _build_error_body(
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(2)>",
    None,
)
code_field = body["error"]["code"]
msg_field = body["error"]["message"]
print(f"  error.code    = {code_field}")
print(f"  error.message = {msg_field}")
script_in_code = "<script>" in code_field
img_in_msg = "<img src=x" in msg_field
print(f"  raw <script> in code? {script_in_code}   <-- must be False")
print(f"  raw <img> in message? {img_in_msg}   <-- must be False")
print(f"  RESULT: {'FAIL' if script_in_code or img_in_msg else 'PASS'}")

print()
print("=" * 60)
print("R2-NEW-01 reproducer (SQL injection in update_user)")
print("=" * 60)
from auth.unified_auth import AuthDatabase, AuthUser

db_path = os.path.join(tempfile.mkdtemp(prefix="r2_repro_"), "u.db")
db = AuthDatabase(db_path)
db.insert_user(AuthUser(
    user_id="u-victim", username="v", email="", role="viewer",
    password_hash="x", password_salt="y", hash_method="argon2",
    is_active=True, is_verified=True, display_name="", team="",
    metadata={}, created_at="2026-01-01T00:00:00", last_login=None, login_count=0,
))
captured = []
class Spy:
    def __init__(self, real): self.real = real
    def execute(self, sql, params=()):
        captured.append((sql, params))
        return self.real.execute(sql, params)
    def commit(self): return self.real.commit()
    def close(self): return self.real.close()
    def __getattr__(self, n): return getattr(self.real, n)
orig_get = db._get_conn
db._get_conn = lambda: Spy(orig_get())
db.update_user("u-victim", {"role": "admin", "email": "new@x"})
db._get_conn = orig_get

update_calls = [(s, p) for s, p in captured if "UPDATE auth_users" in s]
if not update_calls:
    print("  update_user did not call execute! RESULT: FAIL")
else:
    sql, params = update_calls[-1]
    print(f"  SQL    = {sql}")
    print(f"  PARAMS = {params}")
    sql_no_p = sql.replace("?", "")
    bad = [t for t in ("'", "--", "/*", "*/", "; DROP", ";SELECT", ";UPDATE", ";DELETE")
           if t in sql_no_p]
    print(f"  SQL inject markers found: {bad}   <-- must be []")
    print(f"  RESULT: {'FAIL' if bad else 'PASS'}")
