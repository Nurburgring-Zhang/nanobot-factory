"""P2-3-W3 — OWASP A08 Audit Chain smoke tests.

覆盖:
1. secret 缺失 / 太短 → AuditChainError fail-fast
2. 写 3 条 → verify_chain True
3. 中间 entry payload 篡改 → verify_chain False
4. 中间 entry 删除 → verify_chain False (断链)
5. HMAC signature 字段为空 → verify_chain False
6. canvas_web.py middleware 集成 (TestClient + 写 audit_log + audit_chain)
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Add backend/imdf to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend" / "imdf"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _make_chain(tmp_path: Path, secret: str = "test-secret-32bytes-min-audit-chain-p2_3_w3"):
    """构造独立测试 chain."""
    from engines.audit_chain import AuditChain, AuditChainError

    db_path = tmp_path / "audit_chain.db"
    chain = AuditChain(db_path, secret=secret)
    chain.assert_chain()  # 空库 verify 应该 pass
    return chain


def test_secret_missing_fails_fast(tmp_path: Path):
    """secret 缺失 → AuditChainError raise."""
    from engines.audit_chain import AuditChain, AuditChainError

    db_path = tmp_path / "missing_secret.db"
    # 清空 env
    old = os.environ.pop("AUDIT_CHAIN_SECRET", None)
    try:
        try:
            AuditChain(db_path)
            assert False, "AuditChain should raise when secret missing"
        except AuditChainError as e:
            assert "AUDIT_CHAIN_SECRET" in str(e)
            print(f"  OK: missing secret → {type(e).__name__}: {str(e)[:80]}")
    finally:
        if old is not None:
            os.environ["AUDIT_CHAIN_SECRET"] = old


def test_secret_too_short_fails_fast(tmp_path: Path):
    """secret < 16 chars → AuditChainError raise."""
    from engines.audit_chain import AuditChain, AuditChainError

    db_path = tmp_path / "short_secret.db"
    try:
        AuditChain(db_path, secret="short")
        assert False, "AuditChain should raise when secret too short"
    except AuditChainError as e:
        assert "too short" in str(e)
        print(f"  OK: short secret → {type(e).__name__}: {str(e)[:80]}")


def test_append_and_verify_chain(tmp_path: Path):
    """写 3 条 → verify_chain True."""
    chain = _make_chain(tmp_path)
    ts_base = "2026-06-22T10:00:00+00:00"

    e1 = chain.append(timestamp=ts_base, method="POST", path="/api/users",
                      user="alice", body_hash="aaa", status_code=201)
    e2 = chain.append(timestamp=ts_base, method="DELETE", path="/api/users/1",
                      user="alice", body_hash="bbb", status_code=204)
    e3 = chain.append(timestamp=ts_base, method="POST", path="/api/datasets",
                      user="bob", body_hash="ccc", status_code=201)

    # seq 单调 +1
    assert e1.seq == 1, f"e1.seq={e1.seq}"
    assert e2.seq == 2, f"e2.seq={e2.seq}"
    assert e3.seq == 3, f"e3.seq={e3.seq}"

    # prev_hash 链接
    assert e1.prev_hash == "0" * 64
    assert e2.prev_hash == e1.entry_hash
    assert e3.prev_hash == e2.entry_hash

    # signature 非空 + 64 hex
    for e in (e1, e2, e3):
        assert len(e.signature) == 64
        assert all(c in "0123456789abcdef" for c in e.signature)

    # verify_chain True
    ok, bad_seq = chain.verify_chain()
    assert ok, f"verify should pass, got bad_seq={bad_seq}"
    assert bad_seq == -1
    print(f"  OK: 3 entries appended + verify_chain True, signatures OK")


def test_payload_tamper_detected(tmp_path: Path):
    """中间 entry payload 篡改 → verify_chain False."""
    chain = _make_chain(tmp_path)
    ts = "2026-06-22T10:00:00+00:00"

    chain.append(timestamp=ts, method="POST", path="/api/a", user="alice", status_code=201)
    chain.append(timestamp=ts, method="DELETE", path="/api/b", user="alice", status_code=204)
    chain.append(timestamp=ts, method="POST", path="/api/c", user="bob", status_code=201)

    # 直接 UPDATE 中间那条 (seq=2) 的 method 字段
    with chain._connect() as conn:
        conn.execute(
            f"UPDATE {chain.TABLE_NAME} SET method = 'PUT' WHERE seq = 2"
        )
        conn.commit()

    ok, bad_seq = chain.verify_chain()
    assert not ok, "tamper should be detected"
    assert bad_seq == 2, f"bad_seq should be 2, got {bad_seq}"
    print(f"  OK: payload tamper (method change at seq=2) → verify_chain False at seq={bad_seq}")


def test_entry_delete_detected(tmp_path: Path):
    """中间 entry 删除 → verify_chain False (断链)."""
    chain = _make_chain(tmp_path)
    ts = "2026-06-22T10:00:00+00:00"

    chain.append(timestamp=ts, method="POST", path="/api/a", user="alice", status_code=201)
    chain.append(timestamp=ts, method="DELETE", path="/api/b", user="alice", status_code=204)
    chain.append(timestamp=ts, method="POST", path="/api/c", user="bob", status_code=201)

    # 删中间那条
    with chain._connect() as conn:
        conn.execute(f"DELETE FROM {chain.TABLE_NAME} WHERE seq = 2")
        conn.commit()

    ok, bad_seq = chain.verify_chain()
    assert not ok, "delete should break chain"
    assert bad_seq == 3, f"bad_seq should be 3 (seq=3's prev_hash no longer matches), got {bad_seq}"
    print(f"  OK: middle entry delete → verify_chain False at seq={bad_seq}")


def test_signature_forgery_detected(tmp_path: Path):
    """伪造 signature (但保留 entry_hash) → verify_chain False."""
    chain = _make_chain(tmp_path)
    ts = "2026-06-22T10:00:00+00:00"
    chain.append(timestamp=ts, method="POST", path="/api/a", user="alice", status_code=201)
    chain.append(timestamp=ts, method="POST", path="/api/b", user="alice", status_code=201)

    # 试图用一个假 signature 替换
    with chain._connect() as conn:
        conn.execute(
            f"UPDATE {chain.TABLE_NAME} SET signature = ? WHERE seq = 2",
            ("f" * 64,),
        )
        conn.commit()

    ok, bad_seq = chain.verify_chain()
    assert not ok, "forged signature should be detected"
    assert bad_seq == 2
    print(f"  OK: forged signature at seq=2 → verify_chain False")


def test_assert_chain_raises_on_corrupt(tmp_path: Path):
    """assert_chain 在损坏库上 raise AuditChainError."""
    from engines.audit_chain import AuditChainError

    chain = _make_chain(tmp_path)
    ts = "2026-06-22T10:00:00+00:00"
    chain.append(timestamp=ts, method="POST", path="/api/a", status_code=201)
    chain.append(timestamp=ts, method="POST", path="/api/b", status_code=201)

    with chain._connect() as conn:
        conn.execute(
            f"UPDATE {chain.TABLE_NAME} SET status_code = 999 WHERE seq = 1"
        )
        conn.commit()

    try:
        chain.assert_chain()
        assert False, "assert_chain should raise on corrupt db"
    except AuditChainError as e:
        assert e.bad_seq == 1
        print(f"  OK: assert_chain raised AuditChainError at seq={e.bad_seq}: {str(e)[:80]}")


# ============================================================================
# canvas_web.py 集成测试 — TestClient + middleware 写 audit_chain
# ============================================================================

def test_canvas_web_middleware_writes_chain(tmp_path: Path):
    """TestClient POST → audit_log + audit_chain 同时写, verify_chain True."""
    secret = "integration-test-secret-32bytes-audit-chain-p2_3_w3"
    os.environ["AUDIT_CHAIN_SECRET"] = secret

    # 重新 import 以让 module-level 初始化读到 env
    if "engines.audit_chain" in sys.modules:
        del sys.modules["engines.audit_chain"]

    # 强制 audit_chain db 到 tmp
    from engines import audit_chain as ac_mod
    db_path = tmp_path / "integration_audit_chain.db"
    ac_mod.configure_default_db_path(db_path)
    chain = ac_mod.reset_singleton_for_tests(db_path, secret=secret)
    assert chain.verify_chain() == (True, -1), "fresh chain should verify"

    # 导入 canvas_web — 可能会拉很多 import, 慢, 但 hermetic
    from fastapi.testclient import TestClient
    import api.canvas_web as canvas_web

    # 替换 canvas_web 内部 _AUDIT_CHAIN_DB_PATH 指向 tmp
    canvas_web._AUDIT_CHAIN_DB_PATH = db_path
    # 替换 singleton 路径
    ac_mod._DEFAULT_DB_PATH = db_path
    ac_mod._chain_singleton = chain

    client = TestClient(canvas_web.app)

    # 发 3 个 POST 请求 (会触发 middleware audit)
    post_endpoints = [
        ("/api/prompt-templates", {"name": "test1", "content": "hello"}),
        ("/api/prompt-templates", {"name": "test2", "content": "world"}),
        ("/api/prompt-templates", {"name": "test3", "content": "foo"}),
    ]
    for path, payload in post_endpoints:
        r = client.post(path, json=payload)
        # 不关心状态码 (可能是 404/422 — endpoint 不一定存在), 只关心 audit 写入
        # 关键是 chain 里有记录
        print(f"    POST {path} → status={r.status_code}")

    # 验证 chain 至少写了 3 条 (具体条数取决于 endpoint 是否真的进入 middleware)
    entries = chain.load_all()
    assert len(entries) >= 3, f"expected >= 3 entries, got {len(entries)}"

    ok, bad_seq = chain.verify_chain()
    assert ok, f"verify should pass after real middleware writes, got bad_seq={bad_seq}"
    print(f"  OK: canvas_web middleware wrote {len(entries)} entries, verify_chain True")


# ============================================================================
# Runner
# ============================================================================

TESTS = [
    test_secret_missing_fails_fast,
    test_secret_too_short_fails_fast,
    test_append_and_verify_chain,
    test_payload_tamper_detected,
    test_entry_delete_detected,
    test_signature_forgery_detected,
    test_assert_chain_raises_on_corrupt,
]


def main() -> int:
    """Run unit tests (skip the integration test by default — it's slow + needs full FastAPI app)."""
    import inspect
    print("=" * 70)
    print("P2-3-W3 OWASP A08 Audit Chain — unit tests")
    print("=" * 70)

    passed = 0
    failed = 0
    cleanup_errors = 0
    for fn in TESTS:
        name = fn.__name__
        print(f"\n[{name}]")
        # Skip parametrize-style fn that takes arg
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if params != ["tmp_path"]:
            print(f"  SKIP (signature mismatch: {params})")
            continue
        try:
            td_path = Path(tempfile.mkdtemp(prefix="audit_chain_test_"))
            try:
                fn(td_path)
                passed += 1
            finally:
                # 清理 — Windows sqlite 可能持锁, best-effort
                import shutil
                try:
                    shutil.rmtree(str(td_path), ignore_errors=True)
                except Exception:
                    cleanup_errors += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 70}")
    total = passed + failed
    print(f"Unit tests: {passed}/{total} passed (failed={failed}, cleanup_errors={cleanup_errors})")
    print(f"{'=' * 70}")

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())