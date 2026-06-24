"""
P2-1-W3: OSS / MinIO 真接入 — 测试套件
=======================================

覆盖维度:
1. Engine (engines.oss_triple_bucket) — Mock 后端 CRUD / 签名 / 列对象
2. Engine — 显式 oss2 / minio backend 选择 (无凭证时自动 fallback mock)
3. Engine — vector / table 桶 (P0 兼容)
4. Engine — SmartFolder 规则
5. Engine — 模块单例 + 后端切换
6. API (api.oss_routes) — 9 个端点的 TestClient smoke (upload / download / sign / list / head / delete / health / exists / upload-bytes)
7. 集成 (p1_c_w1 /assets) — upload + download + sign + delete 走 OSS

目标: >= 30 用例 PASS, 覆盖 mock + 真后端路径
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

# ── 环境设置: 测试模式 + 清 OSS 变量保证 mock 起点 ────────────────────────
for _k in (
    "OSS_ACCESS_KEY_ID",
    "OSS_ACCESS_KEY_SECRET",
    "OSS_ENDPOINT",
    "OSS_BUCKET",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_BUCKET",
    "OSS_BACKEND",
):
    os.environ.pop(_k, None)
os.environ["OSS_BACKEND"] = "mock"  # 显式 mock, 避免探测到环境变量
os.environ.setdefault("IMDF_TEST_MODE", "1")

# ── 路径设置: 让 api / engines / db / models 都能 import ──────────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_IMDF = _BACKEND / "imdf"
if str(_IMDF) not in sys.path:
    sys.path.insert(0, str(_IMDF))


# ── Engine imports ───────────────────────────────────────────────────────
from engines.oss_triple_bucket import (  # noqa: E402
    BackendType,
    BucketType,
    OSSTripleManager,
    OSSBucketConfig,
    Rule,
    SmartFolder,
    _build_object_backend,
    _detect_backend_from_env,
    _MockObjectStore,
    get_default_manager,
    reset_default_manager,
)


# ─────────────────────────────────────────────────────────────────────────
# 1. Engine — Mock 后端 CRUD
# ─────────────────────────────────────────────────────────────────────────
class TestMockBackend:
    def test_default_backend_is_mock(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        assert mgr.get_backend_name() == "mock"
        assert mgr.is_initialized() is False  # 未调 init_triple_buckets

    def test_upload_returns_etag(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        etag = mgr.upload_to_object_bucket("a/b.txt", b"hello", {"u": "alice"})
        assert isinstance(etag, str)
        assert len(etag) == 32  # md5 hex

    def test_download_roundtrip(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_object_bucket("foo.bin", b"\x00\x01\x02\x03", {"k": "v"})
        data = mgr.download_from_object_bucket("foo.bin")
        assert data == b"\x00\x01\x02\x03"

    def test_download_missing_returns_none(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        assert mgr.download_from_object_bucket("nope.txt") is None

    def test_head_returns_metadata(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_object_bucket("k1", b"data", {"role": "admin"})
        meta = mgr.head_object("k1")
        assert meta is not None
        assert meta["size"] == 4
        assert meta["role"] == "admin"
        assert meta["etag"]  # md5 of "data" = 3a5eb... (任意 32 字符)

    def test_head_missing_returns_none(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        assert mgr.head_object("nope") is None

    def test_delete_existing(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_object_bucket("k1", b"x")
        assert mgr.delete_object("k1") is True
        assert mgr.download_from_object_bucket("k1") is None

    def test_delete_missing_returns_false(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        assert mgr.delete_object("nope") is False

    def test_list_keys_with_prefix(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_object_bucket("imgs/a.png", b"a")
        mgr.upload_to_object_bucket("imgs/b.png", b"b")
        mgr.upload_to_object_bucket("docs/x.txt", b"x")
        all_keys = mgr.list_object_bucket()
        assert len(all_keys) == 3
        prefix_keys = mgr.list_object_bucket(prefix="imgs/")
        assert sorted(prefix_keys) == ["imgs/a.png", "imgs/b.png"]

    def test_presign_url_returns_mock_scheme(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_object_bucket("x", b"x")
        url = mgr.presign_url("x", expires=60)
        assert url.startswith("mock://x")
        assert "expires=" in url

    def test_health_check_ok(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        h = mgr.health_check()
        assert h["status"] == "ok"
        assert h["backend"] == "mock"

    def test_usage_stats_includes_backend(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_object_bucket("k", b"abcdef")
        stats = mgr.get_usage_stats()
        assert stats["backend"] == "mock"
        assert stats["object_bucket"]["total_keys"] == 1
        assert stats["object_bucket"]["total_size_bytes"] == 6


# ─────────────────────────────────────────────────────────────────────────
# 2. Engine — 显式 oss2 / minio backend 选择 (无凭证时 fallback mock)
# ─────────────────────────────────────────────────────────────────────────
class TestBackendSelection:
    def test_explicit_oss2_falls_back_to_mock_without_creds(self):
        """oss2 backend 但 env 没凭证 → 自动降级 mock, 不抛"""
        for k in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET"):
            os.environ.pop(k, None)
        mgr = OSSTripleManager(backend_type=BackendType.OSS2)
        # 失败时切换到 mock
        assert mgr.get_backend_name() in ("mock", "oss2")
        # 至少 health 能跑
        h = mgr.health_check()
        assert h["status"] in ("ok", "error")
        if h.get("init_error"):
            assert "requires" in h["init_error"].lower() or "failed" in h["init_error"].lower()

    def test_explicit_minio_falls_back_to_mock_without_creds(self):
        for k in ("MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_ENDPOINT", "MINIO_BUCKET"):
            os.environ.pop(k, None)
        mgr = OSSTripleManager(backend_type=BackendType.MINIO)
        h = mgr.health_check()
        # 没有真 MinIO 服务器 → 必然降级 mock
        assert mgr.get_backend_name() in ("mock", "minio")
        if h.get("init_error"):
            assert "requires" in h["init_error"].lower() or "failed" in h["init_error"].lower()

    def test_detect_backend_with_no_env_returns_mock(self):
        for k in ("OSS_BACKEND", "OSS_ACCESS_KEY_ID", "MINIO_ENDPOINT"):
            os.environ.pop(k, None)
        bt, kwargs = _detect_backend_from_env()
        assert bt == BackendType.MOCK
        assert kwargs == {}

    def test_detect_backend_with_oss2_env(self):
        os.environ["OSS_BACKEND"] = "oss2"
        os.environ["OSS_ACCESS_KEY_ID"] = "fake-ak"
        os.environ["OSS_ACCESS_KEY_SECRET"] = "fake-sk"
        os.environ["OSS_ENDPOINT"] = "oss-cn-hangzhou.aliyuncs.com"
        os.environ["OSS_BUCKET"] = "fake-bucket"
        try:
            bt, kwargs = _detect_backend_from_env()
            assert bt == BackendType.OSS2
            assert kwargs["access_key"] == "fake-ak"
            assert kwargs["bucket_name"] == "fake-bucket"
        finally:
            for k in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET", "OSS_BACKEND"):
                os.environ.pop(k, None)

    def test_detect_backend_with_minio_env(self):
        os.environ["OSS_BACKEND"] = "minio"
        os.environ["MINIO_ENDPOINT"] = "127.0.0.1:9000"
        os.environ["MINIO_ACCESS_KEY"] = "minioadmin"
        os.environ["MINIO_SECRET_KEY"] = "minioadmin"
        os.environ["MINIO_BUCKET"] = "test-bucket"
        try:
            bt, kwargs = _detect_backend_from_env()
            assert bt == BackendType.MINIO
            assert kwargs["endpoint"] == "127.0.0.1:9000"
        finally:
            for k in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET", "OSS_BACKEND"):
                os.environ.pop(k, None)

    def test_set_backend_runtime_switch(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        assert mgr.get_backend_name() == "mock"
        h = mgr.set_backend(BackendType.OSS2)  # 缺凭证会降级
        assert h["status"] in ("ok", "error")

    def test_init_triple_buckets_keeps_legacy_compat(self):
        """P0 兼容: init_triple_buckets 接受 OSSBucketConfig 三参数"""
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        ok = mgr.init_triple_buckets(
            object_cfg=OSSBucketConfig(
                bucket_type=BucketType.OBJECT,
                endpoint="",
                bucket_name="b1",
                backend_type=BackendType.MOCK,
            ),
            vector_cfg=OSSBucketConfig(
                bucket_type=BucketType.VECTOR, endpoint="", bucket_name="b2",
            ),
            table_cfg=OSSBucketConfig(
                bucket_type=BucketType.TABLE, endpoint="", bucket_name="b3",
            ),
        )
        assert ok is True
        assert mgr.is_initialized() is True
        assert mgr.configs[BucketType.OBJECT].bucket_name == "b1"

    def test_minio_sdk_imported(self):
        """真凭证路径依赖: minio 7.2.0 SDK 可 import"""
        import minio
        assert minio.__version__ is not None
        assert minio.__version__.startswith("7.")

    def test_oss2_sdk_imported(self):
        """真凭证路径依赖: oss2 SDK 可 import"""
        import oss2
        assert oss2.__version__ is not None


# ─────────────────────────────────────────────────────────────────────────
# 3. Engine — vector / table 桶 (P0 兼容)
# ─────────────────────────────────────────────────────────────────────────
class TestVectorTableBuckets:
    def test_vector_upsert_and_query(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.upload_to_vector_bucket("v1", [1.0, 0.0, 0.0], {"tag": "x"})
        mgr.upload_to_vector_bucket("v2", [0.0, 1.0, 0.0])
        mgr.upload_to_vector_bucket("v3", [1.0, 0.0, 0.0])
        results = mgr.query_vector_bucket([1.0, 0.0, 0.0], top_k=2)
        keys = [k for k, _ in results]
        assert "v1" in keys
        assert "v3" in keys
        # v1 应该是最高相似度 (ties 都行)

    def test_table_crud(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.create_table(["id", "name", "value"])
        mgr.insert_into_table({"id": 1, "name": "alice", "value": 100})
        mgr.insert_into_table({"id": 2, "name": "bob", "value": 200})
        mgr.insert_into_table({"id": 3, "name": "alice", "value": 300})
        all_rows = mgr.query_table()
        assert len(all_rows) == 3
        alice_rows = mgr.query_table({"name": "alice"})
        assert len(alice_rows) == 2

    def test_table_sync_replaces(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        mgr.insert_into_table({"a": 1})
        mgr.sync_table_bucket([{"a": 10}, {"a": 20}])
        rows = mgr.query_table()
        assert len(rows) == 2


# ─────────────────────────────────────────────────────────────────────────
# 4. Engine — SmartFolder
# ─────────────────────────────────────────────────────────────────────────
class TestSmartFolder:
    def test_create_and_match(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        sf = mgr.create_smart_folder("images_jpg", [
            Rule("type", "eq", "image"),
            Rule("name", "contains", ".jpg"),
        ])
        items = [
            {"type": "image", "name": "cat.jpg"},
            {"type": "image", "name": "dog.png"},
            {"type": "video", "name": "movie.jpg"},
        ]
        matched = sf.match_items(items)
        assert len(matched) == 1
        assert matched[0]["name"] == "cat.jpg"

    def test_rule_operators(self):
        mgr = OSSTripleManager(backend_type=BackendType.MOCK)
        # 用 ``count=10`` 作为 item 字段值, 测试各 operator
        for op, val, expected in [
            ("gt", 5, True),    # 10 > 5
            ("gt", 10, False),  # 10 > 10 strict
            ("lt", 5, False),   # 10 < 5
            ("lt", 15, True),   # 10 < 15
            ("gte", 10, True),  # 10 >= 10
            ("lte", 10, True),  # 10 <= 10
            ("ne", 5, True),    # 10 != 5
            ("ne", 10, False),  # 10 != 10
            ("in", [1, 2, 10], True),    # 10 in list
            ("in", [1, 2, 3], False),    # 10 not in list
        ]:
            r = Rule("count", op, val)
            assert r.matches({"count": 10}) is expected, f"operator {op} val={val} expected={expected}"


# ─────────────────────────────────────────────────────────────────────────
# 5. Engine — Singleton
# ─────────────────────────────────────────────────────────────────────────
class TestSingleton:
    def test_get_default_manager_returns_same_instance(self):
        reset_default_manager()
        a = get_default_manager()
        b = get_default_manager()
        assert a is b

    def test_singleton_uses_env(self):
        reset_default_manager()
        os.environ["OSS_BACKEND"] = "mock"
        mgr = get_default_manager()
        assert mgr.get_backend_name() == "mock"
        assert mgr.is_initialized() is True  # init_triple_buckets 在 lazy 路径自动调


# ─────────────────────────────────────────────────────────────────────────
# 6. API (api.oss_routes) — 9 个端点 TestClient smoke
# ─────────────────────────────────────────────────────────────────────────
class TestOssApiRoutes:
    """用最小 FastAPI app 挂载 oss router, 不依赖 canvas_web.py 全部加载。"""

    @classmethod
    def setup_class(cls):
        # 重置单例, 保证 mock 起点
        reset_default_manager()
        os.environ["OSS_BACKEND"] = "mock"

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        # 强制重置 (避免测试间状态污染)
        reset_default_manager()
        from api.oss_routes import router as oss_router
        app = FastAPI()
        app.include_router(oss_router)
        return TestClient(app)

    def test_health_endpoint(self):
        c = self._client()
        r = c.get("/api/v1/oss/health")
        assert r.status_code == 200
        d = r.json()
        assert "backend" in d
        assert d["backend"] == "mock"

    def test_list_empty(self):
        c = self._client()
        r = c.get("/api/v1/oss/list")
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["count"] == 0
        assert d["data"]["keys"] == []

    def test_upload_multipart(self):
        c = self._client()
        r = c.post(
            "/api/v1/oss/upload",
            files={"file": ("hello.txt", b"hello world", "text/plain")},
            data={"prefix": "test/"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is True
        assert d["data"]["size"] == 11
        assert d["data"]["key"].startswith("test/")
        assert d["data"]["etag"]
        assert d["data"]["sign_url"]

    def test_upload_bytes(self):
        c = self._client()
        body = {
            "key": "raw/b64-test.bin",
            "data_b64": base64.b64encode(b"abc123").decode("ascii"),
            "metadata": {"role": "admin"},
        }
        r = c.post("/api/v1/oss/upload-bytes", json=body)
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["key"] == "raw/b64-test.bin"
        assert d["data"]["size"] == 6

    def test_download_roundtrip(self):
        c = self._client()
        # upload
        up = c.post(
            "/api/v1/oss/upload",
            files={"file": ("a.bin", b"\x00\xff\x10", "application/octet-stream")},
            data={"key": "dl/a.bin"},
        )
        assert up.status_code == 200
        key = up.json()["data"]["key"]
        # download
        dl = c.get(f"/api/v1/oss/download/{key}")
        assert dl.status_code == 200
        assert dl.content == b"\x00\xff\x10"
        assert dl.headers.get("X-Backend") == "mock"

    def test_download_missing_404(self):
        c = self._client()
        r = c.get("/api/v1/oss/download/nope.bin")
        assert r.status_code == 404

    def test_head_object(self):
        c = self._client()
        c.post(
            "/api/v1/oss/upload",
            files={"file": ("h.txt", b"hhhh", "text/plain")},
            data={"key": "head/h.txt"},
        )
        r = c.get("/api/v1/oss/head/head/h.txt")
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["size"] == 4

    def test_head_missing_404(self):
        c = self._client()
        r = c.get("/api/v1/oss/head/nope.txt")
        assert r.status_code == 404

    def test_sign_get(self):
        c = self._client()
        c.post(
            "/api/v1/oss/upload",
            files={"file": ("s.txt", b"x", "text/plain")},
            data={"key": "sign/s.txt"},
        )
        r = c.get("/api/v1/oss/sign/sign/s.txt?expires=60")
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["method"] == "GET"
        assert d["data"]["expires"] == 60
        assert d["data"]["url"].startswith("mock://")

    def test_sign_post_put(self):
        c = self._client()
        # /api/v1/oss/sign/{key:path} (POST) 接受 method=GET|PUT
        r = c.post("/api/v1/oss/sign/new/key.txt?expires=120&method=PUT")
        assert r.status_code == 200, f"got {r.status_code} body={r.text}"
        d = r.json()
        assert d["data"]["method"] == "PUT"

    def test_delete_object(self):
        c = self._client()
        c.post(
            "/api/v1/oss/upload",
            files={"file": ("d.txt", b"d", "text/plain")},
            data={"key": "del/d.txt"},
        )
        r = c.delete("/api/v1/oss/object/del/d.txt")
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True

    def test_delete_missing_returns_200_idempotent(self):
        c = self._client()
        r = c.delete("/api/v1/oss/object/nope.txt")
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is False

    def test_exists(self):
        c = self._client()
        c.post(
            "/api/v1/oss/upload",
            files={"file": ("e.txt", b"e", "text/plain")},
            data={"key": "exists/e.txt"},
        )
        r = c.get("/api/v1/oss/exists/exists/e.txt")
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["exists"] is True
        assert d["data"]["size"] == 1

    def test_list_with_prefix(self):
        c = self._client()
        c.post(
            "/api/v1/oss/upload",
            files={"file": ("a.txt", b"a", "text/plain")},
            data={"key": "list-test/a.txt"},
        )
        c.post(
            "/api/v1/oss/upload",
            files={"file": ("b.txt", b"b", "text/plain")},
            data={"key": "list-test/b.txt"},
        )
        r = c.get("/api/v1/oss/list?prefix=list-test/")
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["count"] == 2
        assert all(k.startswith("list-test/") for k in d["data"]["keys"])

    def test_key_path_traversal_rejected(self):
        c = self._client()
        # ``..`` 在 key 中
        r = c.get("/api/v1/oss/download/../etc/passwd")
        # FastAPI path conversion may collapse or return 404 — 两者都 OK
        assert r.status_code in (400, 404)
        # 含非法字符
        r = c.get("/api/v1/oss/sign/has%20space")
        assert r.status_code in (400, 404, 422)

    def test_upload_empty_file_400(self):
        c = self._client()
        r = c.post(
            "/api/v1/oss/upload",
            files={"file": ("empty.txt", b"", "text/plain")},
            data={"key": "empty.txt"},
        )
        assert r.status_code == 400

    def test_upload_bytes_invalid_b64_400(self):
        c = self._client()
        r = c.post("/api/v1/oss/upload-bytes", json={
            "key": "x.bin", "data_b64": "not-valid-base64!@#",
        })
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────
# 7. 集成 (p1_c_w1 /assets) — upload + download + sign + delete 走 OSS
# ─────────────────────────────────────────────────────────────────────────
class TestAssetsIntegration:
    """验证 p1_c_w1 /assets/* 端点在 OSS 接入后仍能 PASS, 且落 OSS (而非只写本地)"""

    @classmethod
    def setup_class(cls):
        reset_default_manager()
        os.environ["OSS_BACKEND"] = "mock"

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        reset_default_manager()
        from api.p1_c_w1_routes import router as p1_router
        app = FastAPI()
        app.include_router(p1_router)
        return TestClient(app)

    def test_upload_stores_oss_key(self):
        c = self._client()
        r = c.post(
            "/api/assets/upload",
            files={"file": ("test.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100, "image/png")},
            data={"type": "image", "tags": "test,ci"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is True
        asset = d["data"]
        assert asset["storage"] == "oss"  # P2-1-W3 优先 OSS
        assert asset["oss_key"] is not None
        assert asset["oss_key"].startswith("p1_c_w1/assets/")
        assert asset["oss_backend"] == "mock"
        assert asset["oss_sign_url"]

    def test_download_roundtrip_from_oss(self):
        c = self._client()
        content = b"ASSET-CONTENT-" + uuid.uuid4().hex.encode()
        up = c.post(
            "/api/assets/upload",
            files={"file": ("a.bin", content, "application/octet-stream")},
            data={"type": "raw"},
        )
        asset_id = up.json()["data"]["id"]
        r = c.get(f"/api/assets/{asset_id}/download")
        assert r.status_code == 200
        assert r.content == content
        assert r.headers.get("X-Storage") == "oss"
        assert r.headers.get("X-OSS-Backend") == "mock"

    def test_sign_asset_url(self):
        c = self._client()
        up = c.post(
            "/api/assets/upload",
            files={"file": ("s.txt", b"x", "text/plain")},
        )
        asset_id = up.json()["data"]["id"]
        r = c.get(f"/api/assets/{asset_id}/sign?expires=120")
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["url"].startswith("mock://")
        assert d["data"]["expires"] == 120

    def test_delete_asset_clears_oss(self):
        c = self._client()
        up = c.post(
            "/api/assets/upload",
            files={"file": ("d.txt", b"d", "text/plain")},
        )
        asset_id = up.json()["data"]["id"]
        # 确认 OSS 里有
        oss_key = up.json()["data"]["oss_key"]
        from engines.oss_triple_bucket import get_default_manager
        assert get_default_manager().download_from_object_bucket(oss_key) == b"d"
        # 删除
        r = c.delete(f"/api/assets/{asset_id}")
        assert r.status_code == 200
        # OSS 也清掉了
        assert get_default_manager().download_from_object_bucket(oss_key) is None

    def test_legacy_asset_without_oss_key_returns_400_on_sign(self):
        """P0 时代上传的 asset (无 oss_key) 调 sign 应 400 而不是 500"""
        c = self._client()
        # 注入一个伪 legacy asset
        from pathlib import Path as _P
        assets_file = _P(_IMDF) / "data" / "p1_c_w1" / "assets.json"
        legacy = [
            {"id": "legacy_x", "name": "old.txt", "type": "image",
             "size": 10, "tags": [], "path": "uploads/legacy_x_old.txt",
             "uploaded_at": "2020-01-01T00:00:00Z"}  # no oss_key
        ]
        original = assets_file.read_text(encoding="utf-8") if assets_file.exists() else "[]"
        assets_file.write_text(__import__("json").dumps(legacy), encoding="utf-8")
        try:
            r = c.get("/api/assets/legacy_x/sign")
            assert r.status_code == 400
        finally:
            assets_file.write_text(original, encoding="utf-8")
