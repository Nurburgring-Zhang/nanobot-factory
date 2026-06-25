"""P2-3-W3 — Smoke test: TestClient + canvas_web middleware → audit_chain.

运行此测试前先确认:
- AUDIT_CHAIN_SECRET env 已设 (>= 16 chars)
- canvas_web.py 可正常 import (TestClient 会在内存里启动)
- sqlite db 文件可写
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Add backend/imdf to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend" / "imdf"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_canvas_web_middleware_writes_chain():
    """用 TestClient POST → 验证 audit_chain 真正被 middleware 写入."""
    secret = "smoke-test-secret-32bytes-audit-chain-p2_3_w3"
    os.environ["AUDIT_CHAIN_SECRET"] = secret

    # 重置 audit_chain module singleton
    if "engines.audit_chain" in sys.modules:
        del sys.modules["engines.audit_chain"]
    if "engines" in sys.modules:
        # Don't fully drop engines — just the audit_chain submodule
        pass

    from engines import audit_chain as ac_mod

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        db_path = tmp / "audit_chain.db"
        chain = ac_mod.reset_singleton_for_tests(db_path, secret=secret)
        assert chain.verify_chain() == (True, -1), "fresh chain should verify"

        # 导入 canvas_web
        from fastapi.testclient import TestClient
        import api.canvas_web as canvas_web

        # 替换内部 db 路径
        canvas_web._AUDIT_CHAIN_DB_PATH = db_path
        ac_mod._DEFAULT_DB_PATH = db_path
        ac_mod._chain_singleton = chain

        client = TestClient(canvas_web.app)

        # 发 POST 触发 middleware
        post_paths = [
            ("/api/prompt-templates", {"name": "t1", "content": "c1"}),
            ("/api/prompt-templates", {"name": "t2", "content": "c2"}),
            ("/api/prompt-templates", {"name": "t3", "content": "c3"}),
        ]
        for path, payload in post_paths:
            r = client.post(path, json=payload)
            print(f"    POST {path} → status={r.status_code}")

        # 验证 chain 里至少 3 条
        entries = chain.load_all()
        assert len(entries) >= 3, f"expected >= 3 entries, got {len(entries)}"

        # verify_chain True
        ok, bad_seq = chain.verify_chain()
        assert ok, f"verify should pass, got bad_seq={bad_seq}"
        print(f"  OK: {len(entries)} entries written, verify_chain True")

        # 模拟篡改中间一条 → verify FAIL
        with chain._connect() as conn:
            conn.execute(
                f"UPDATE {chain.TABLE_NAME} SET method = 'PUT' WHERE seq = 2"
            )
            conn.commit()
        ok2, bad_seq2 = chain.verify_chain()
        assert not ok2
        print(f"  OK: tamper → verify_chain False at seq={bad_seq2}")

    print("=" * 70)
    print("canvas_web middleware integration smoke: PASS")
    print("=" * 70)


if __name__ == "__main__":
    test_canvas_web_middleware_writes_chain()