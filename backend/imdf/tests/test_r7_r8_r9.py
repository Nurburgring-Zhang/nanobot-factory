"""VDP-2026 R7 + R8 + R9 — Deployment readiness + Security + Perf tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ===========================================================================
# R7 deployment readiness
# ===========================================================================


class TestR7Deployment:
    def test_readiness_report(self):
        from deploy_r7.readiness import readiness_report
        rep = readiness_report()
        assert rep["total_endpoints"] >= 30
        for module in ("R1", "R2", "R3", "R4", "R5", "R6", "Health", "QC"):
            assert module in rep["modules"], f"missing module {module}"

    def test_audit_against_app(self):
        from deploy_r7.readiness import audit_against_app

        class _App:
            def __init__(self):
                from fastapi import FastAPI
                self.routes = FastAPI().routes
        rep = audit_against_app(_App())
        assert rep["catalogued"] >= 30


# ===========================================================================
# R8 security
# ===========================================================================


@pytest.fixture(autouse=True)
def isolated_r8(tmp_path):
    from security_r8 import configure_db, reset_security_for_test
    configure_db(tmp_path / "sec.db")
    reset_security_for_test()
    yield


class TestR8Security:
    def test_pii_redaction(self):
        from security_r8 import redact_pii
        text = "Contact alice@example.com or 13800001111 from 1.2.3.4 ID 123456789012345678"
        out = redact_pii(text)
        assert "[EMAIL]" in out["redacted"]
        assert "[PHONE]" in out["redacted"]
        assert "[IP]" in out["redacted"]
        assert "[ID]" in out["redacted"]
        assert out["counts"]["email"] == 1
        assert out["counts"]["phone"] == 1
        assert out["counts"]["ipv4"] == 1
        assert out["counts"]["ssn"] == 1

    def test_pii_selective(self):
        from security_r8 import redact_pii
        out = redact_pii("foo@bar.com 1.2.3.4", kinds=["email"])
        assert "[EMAIL]" in out["redacted"]
        assert "1.2.3.4" in out["redacted"]  # IP not redacted

    def test_rate_limiter(self):
        from security_r8 import get_rate_limiter
        rl = get_rate_limiter(max_per_min=3)
        results = [rl.check("rl_test", max_per_min=3) for _ in range(5)]
        allowed = [r["allowed"] for r in results]
        assert allowed == [True, True, True, False, False]

    def test_audit_chain(self):
        from security_r8 import get_audit
        audit = get_audit()
        audit.append("test.event", actor="alice", payload={"k": "v"})
        audit.append("test.event", actor="bob", payload={"k": "v2"})
        v = audit.verify()
        assert v["verified"] is True
        assert v["total_rows"] == 2
        tail = audit.tail(limit=10)
        assert len(tail) >= 2

    def test_audit_tamper_detection(self):
        from security_r8 import get_audit
        audit = get_audit()
        audit.append("test.event", actor="alice", payload={"k": "v"})
        # directly tamper with a row in the DB
        import sqlite3
        from security_r8 import configure_db as _cfg
        # reach the actual conn function via module attribute
        from security_r8 import hardening as _h
        with _h._conn() as conn:
            conn.execute("UPDATE audit_chain SET payload_json = ? WHERE id = (SELECT MAX(id) FROM audit_chain)",
                         ('{"k":"tampered"}',))
        v = audit.verify()
        assert v["verified"] is False
        assert len(v["tampered_rows"]) >= 1

    def test_secrets_vault(self):
        from security_r8 import get_vault
        v = get_vault()
        # 8 secrets seeded
        names = v.list_names()
        assert len(names) >= 4
        assert "openai_api_key" in names
        val = v.get("openai_api_key", actor="r8-test")
        assert isinstance(val, str) and val
        # rotate
        ok = v.rotate("openai_api_key", "new-secret-***", actor="r8-test")
        assert ok
        v2 = v.get("openai_api_key", actor="r8-test")
        assert v2 == "new-secret-***"
        # missing secret
        v3 = v.get("does-not-exist", actor="r8-test")
        assert v3 is None


# ===========================================================================
# R9 perf
# ===========================================================================


class TestR9Perf:
    def test_ttl_cache(self):
        from perf_r9 import get_cache, reset_for_test
        reset_for_test()
        from perf_r9 import configure_db as _dummy  # ensure db configured even if not used
        c = get_cache(max_size=2, ttl=1)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)  # evicts LRU
        assert "a" not in c._store
        assert c.get("a") is None  # miss
        assert c.get("b") == 2
        assert c.get("c") == 3
        stats = c.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1

    def test_ttl_expiry(self):
        from perf_r9 import get_cache, reset_for_test
        reset_for_test()
        c = get_cache(max_size=10, ttl=0.05)
        c.set("k", "v")
        assert c.get("k") == "v"
        import time as _t
        _t.sleep(0.1)
        assert c.get("k") is None

    def test_pool(self):
        from perf_r9 import get_pool, reset_for_test
        reset_for_test()
        p = get_pool(max_size=2)
        a = p.acquire()
        b = p.acquire()
        s = p.stats()
        assert s["in_use"] == 2
        p.release(a)
        p.release(b)
        s2 = p.stats()
        assert s2["in_use"] == 0
        assert s2["available"] == 2

    def test_batch_executes(self):
        from perf_r9 import get_batch, reset_for_test
        reset_for_test()
        b = get_batch()
        def _proc(n: int) -> int: return n * 2
        for n in range(7):
            b.add(_proc, args=(n,))
        b.flush()
        s = b.stats()
        assert s["jobs_executed"] == 7
        assert s["error_rate"] == 0

    def test_async_queue(self):
        from perf_r9 import get_queue, reset_for_test
        reset_for_test()
        q = get_queue()
        q.push({"i": 1})
        q.push({"i": 2})
        first = q.pop(timeout=1)
        assert first == {"i": 1}
        second = q.pop(timeout=1)
        assert second == {"i": 2}
        assert q.stats()["dequeued"] == 2


class TestHTTPAll:
    def _client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            return None
        from security_r8.routes import router as sec_r
        from perf_r9.routes import router as perf_r
        app = FastAPI()
        app.include_router(sec_r)
        app.include_router(perf_r)
        return TestClient(app)

    def test_security_http(self):
        c = self._client()
        if c is None: pytest.skip("fastapi")
        r = c.post("/api/v1/security/redact",
                   json={"text": "alice@example.com 13800001111", "actor": "http"})
        assert r.status_code == 200
        assert "[EMAIL]" in r.json()["redacted"]
        r = c.post("/api/v1/security/audit/append",
                   json={"event_type": "http.test", "actor": "h"})
        assert r.status_code == 200
        r = c.get("/api/v1/security/audit/verify")
        assert r.status_code == 200
        r = c.get("/api/v1/security/secrets")
        assert r.status_code == 200
        assert "openai_api_key" in r.json()["names"]

    def test_perf_http(self):
        c = self._client()
        if c is None: pytest.skip("fastapi")
        r = c.post("/api/v1/perf/cache/set", json={"key": "k1", "value": "v1"})
        assert r.status_code == 200
        r = c.get("/api/v1/perf/cache/get", params={"key": "k1"})
        assert r.status_code == 200
        assert r.json()["value"] == "v1"
        r = c.post("/api/v1/perf/cache/invalidate", json={"prefix": "k"})
        assert r.status_code == 200
        r = c.get("/api/v1/perf/cache/get", params={"key": "k1"})
        assert r.json()["value"] is None
        r = c.post("/api/v1/perf/batch/run", json={"jobs": [{"value": 1}, {"value": 2}]})
        assert r.status_code == 200
        r = c.post("/api/v1/perf/queue/push", json={"payload": {"i": 5}})
        assert r.status_code == 200
        r = c.get("/api/v1/perf/queue/pop", params={"timeout": 1.0})
        assert r.status_code == 200
        r = c.get("/api/v1/perf/health")
        assert r.status_code == 200
