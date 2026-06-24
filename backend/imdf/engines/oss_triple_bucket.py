"""阿里云 OSS / MinIO 三桶架构 + 智能文件夹引擎 (P2-1-W3 真接入版本)

设计要点
========

1. **三桶分离**: ``object`` (二进制文件/媒体) / ``vector`` (向量嵌入) / ``table`` (结构化元数据)。
2. **真后端支持**: ``object`` 桶可挂载 ``oss2`` (阿里云) / ``minio`` (S3 兼容) / ``mock`` (内存) 三种后端,
   通过环境变量 ``OSS_BACKEND`` 一键切换。无凭证时自动 fallback 到 ``mock``。
3. **API 兼容**: 保留原有 ``OSSTripleManager`` 全部方法 (R2 系列已经在用), 同时新增:
   - ``presign_url(key, expires=3600)`` — 生成带签名 URL
   - ``head_object(key)`` — 取元数据/大小/ETag
   - ``list_objects(prefix='')`` — 按前缀列对象
   - ``health_check()`` — 后端连通性检查
   - ``get_backend_name()`` — 当前后端名 (mock/oss2/minio)

4. **冷启动 fallback**: 缺失凭证 / 库导入失败 / 网络不可达 → 自动降级到 mock, **不抛 500**。
5. **smart folder 引擎**: 基于 ``Rule`` 列表动态聚合 assets (保留 P0 引擎语义)。
6. **零侵入 import**: 本文件既可直接 ``from engines.oss_triple_bucket import ...``, 也可被
   ``canvas_web.py`` / ``p1_c_w1_routes.py`` 复用。

环境变量
========

- ``OSS_BACKEND``        : ``oss2`` | ``minio`` | ``mock`` (默认自动检测)
- ``OSS_ACCESS_KEY_ID``  : AK (阿里云 AccessKeyId / MinIO access_key)
- ``OSS_ACCESS_KEY_SECRET``: SK (阿里云 AccessKeySecret / MinIO secret_key)
- ``OSS_ENDPOINT``       : endpoint (阿里云: ``oss-cn-hangzhou.aliyuncs.com``; MinIO: ``http://127.0.0.1:9000``)
- ``OSS_BUCKET``         : 默认 bucket 名 (object 桶)
- ``OSS_REGION``         : 阿里云 region, 默认 ``cn-hangzhou``
- ``OSS_SECURE``         : bool, ``true`` → https, ``false`` → http (MinIO)
- ``OSS_PRESIGN_EXPIRES``: 默认签名 URL 过期秒数, 默认 3600
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)

# ── 桶类型枚举 (保留 P0 兼容) ───────────────────────────────────────────

class BucketType(str, Enum):
    OBJECT = "object"
    VECTOR = "vector"
    TABLE = "table"


class BackendType(str, Enum):
    """object 桶底层后端类型"""
    MOCK = "mock"
    OSS2 = "oss2"   # 阿里云 OSS
    MINIO = "minio"  # S3 兼容 (MinIO / AWS S3)


# ── 桶配置 (保留 P0 兼容 + 新增 backend_type / secure / presign_expires) ─

@dataclass
class OSSBucketConfig:
    """桶配置 — object / vector / table 三种桶独立持有, 但本类统一描述"""
    bucket_type: BucketType
    endpoint: str
    bucket_name: str
    region: str = "cn-hangzhou"
    access_key: str = ""
    secret_key: str = ""
    # P2-1-W3 新增
    backend_type: BackendType = BackendType.MOCK
    secure: bool = True
    presign_expires: int = 3600  # 秒


# ═══════════════════════════════════════════════════════════════════════════
#                       Object 桶后端抽象与三种实现
# ═══════════════════════════════════════════════════════════════════════════

class _ObjectBackend(Protocol):
    """object 桶后端接口 — 任何真实后端必须实现这些方法。"""
    name: str

    def put(self, key: str, data: bytes, meta: Optional[dict] = None) -> str: ...
    def get(self, key: str) -> Optional[bytes]: ...
    def delete(self, key: str) -> bool: ...
    def list_keys(self, prefix: str = "") -> List[str]: ...
    def head(self, key: str) -> Optional[dict]: ...
    def sign(self, key: str, expires: int = 3600, method: str = "GET") -> str: ...
    def size(self) -> int: ...
    def health_check(self) -> dict: ...


# ── 1. Mock 后端 (内存, 永不失败) ───────────────────────────────────────

class _MockObjectStore:
    """进程内 Dict 存储 — 无网络, 用于开发/测试。"""
    name = "mock"

    def __init__(self):
        self._objects: Dict[str, bytes] = {}
        self._metadata: Dict[str, dict] = {}

    def put(self, key: str, data: bytes, meta: Optional[dict] = None) -> str:
        etag = hashlib.md5(data).hexdigest()
        self._objects[key] = data
        self._metadata[key] = {
            "etag": etag,
            "size": len(data),
            "upload_time": time.time(),
            **(meta or {}),
        }
        return etag

    def get(self, key: str) -> Optional[bytes]:
        return self._objects.get(key)

    def delete(self, key: str) -> bool:
        if key in self._objects:
            self._objects.pop(key, None)
            self._metadata.pop(key, None)
            return True
        return False

    def list_keys(self, prefix: str = "") -> List[str]:
        return sorted([k for k in self._objects if k.startswith(prefix)])

    def head(self, key: str) -> Optional[dict]:
        if key not in self._metadata:
            return None
        m = dict(self._metadata[key])
        return m

    def sign(self, key: str, expires: int = 3600, method: str = "GET") -> str:
        """Mock 签名: 返回 ``mock://<key>?expires=<ts>`` 让前端能识别。

        语义:
        - GET: 用于下载 — mock 后端假定 key 已存在 (真实后端也会做 head 检查)
        - PUT: 用于上传 — key 还不存在, 必须给 URL (与真 S3/OSS 一致)
        """
        if method.upper() == "GET" and key not in self._objects:
            return ""
        return f"mock://{key}?expires={int(time.time()) + expires}&method={method.upper()}"

    def size(self) -> int:
        return sum(len(v) for v in self._objects.values())

    def health_check(self) -> dict:
        return {
            "backend": self.name,
            "status": "ok",
            "mode": "in-memory",
            "object_count": len(self._objects),
            "total_bytes": self.size(),
        }


# ── 2. 阿里云 OSS 后端 (oss2) ──────────────────────────────────────────

class _Oss2ObjectStore:
    """真实阿里云 OSS 后端 — 走 ``oss2`` SDK。

    失败策略: 任意网络/认证错误抛出 oss2.exceptions.OssError, 调用方需要捕获并降级。
    """
    name = "oss2"

    def __init__(self, endpoint: str, bucket_name: str, access_key: str,
                 secret_key: str, region: str = "cn-hangzhou"):
        import oss2  # 局部 import, 避免模块加载阶段硬依赖
        self._oss2 = oss2
        auth = oss2.Auth(access_key, secret_key)
        # 阿里云 bucket 端点格式: https://{bucket}.{endpoint}
        self._bucket_name = bucket_name
        self._endpoint = endpoint
        self._bucket = oss2.Bucket(auth, f"https://{bucket_name}.{endpoint}", bucket_name)
        self._region = region
        # 验证连通性 (best-effort, 失败不抛 — 留给 health_check 报告)
        self._reachable: Optional[bool] = None

    def _ensure_bucket(self):
        """确认 bucket 存在 — 若不存在则尝试创建。"""
        try:
            self._bucket.get_bucket_info()
        except self._oss2.exceptions.NoSuchBucket:
            try:
                self._bucket.create_bucket(self._oss2.BUCKET_ACL_PRIVATE)
                logger.info(f"[oss2] created bucket {self._bucket_name}")
            except Exception as e:
                logger.warning(f"[oss2] create_bucket {self._bucket_name} failed: {e}")

    def put(self, key: str, data: bytes, meta: Optional[dict] = None) -> str:
        headers: Dict[str, str] = {}
        if meta:
            for k, v in meta.items():
                # OSS Object 自定义 meta 头需以 ``x-oss-meta-`` 开头
                key_lower = str(k).lower().replace("_", "-")
                headers[f"x-oss-meta-{key_lower}"] = str(v)
        result = self._bucket.put_object(key, data, headers=headers)
        return result.etag

    def get(self, key: str) -> Optional[bytes]:
        try:
            obj = self._bucket.get_object(key)
            return obj.read()
        except self._oss2.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.warning(f"[oss2] get {key} failed: {e}")
            return None

    def delete(self, key: str) -> bool:
        try:
            self._bucket.delete_object(key)
            return True
        except Exception as e:
            logger.warning(f"[oss2] delete {key} failed: {e}")
            return False

    def list_keys(self, prefix: str = "") -> List[str]:
        keys: List[str] = []
        try:
            for obj in self._oss2.ObjectIterator(self._bucket, prefix=prefix):
                keys.append(obj.key)
        except Exception as e:
            logger.warning(f"[oss2] list prefix={prefix!r} failed: {e}")
        return keys

    def head(self, key: str) -> Optional[dict]:
        try:
            meta = self._bucket.head_object(key)
            return {
                "etag": meta.etag,
                "size": meta.content_length,
                "content_type": meta.content_type,
                "last_modified": meta.last_modified,
            }
        except self._oss2.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.warning(f"[oss2] head {key} failed: {e}")
            return None

    def sign(self, key: str, expires: int = 3600, method: str = "GET") -> str:
        try:
            url = self._bucket.sign_url(method, key, expires)
            return url
        except Exception as e:
            logger.warning(f"[oss2] sign {key} failed: {e}")
            return ""

    def size(self) -> int:
        total = 0
        for obj in self._oss2.ObjectIterator(self._bucket):
            total += obj.size
        return total

    def health_check(self) -> dict:
        try:
            info = self._bucket.get_bucket_info()
            return {
                "backend": self.name,
                "status": "ok",
                "endpoint": self._endpoint,
                "bucket": self._bucket_name,
                "region": info.location if hasattr(info, "location") else self._region,
                "creation_date": str(info.creation_date) if hasattr(info, "creation_date") else None,
                "extranet_endpoint": info.extranet_endpoint if hasattr(info, "extranet_endpoint") else None,
            }
        except Exception as e:
            return {
                "backend": self.name,
                "status": "error",
                "error": str(e),
                "endpoint": self._endpoint,
                "bucket": self._bucket_name,
            }


# ── 3. MinIO / S3 兼容后端 (minio) ──────────────────────────────────────

class _MinioObjectStore:
    """MinIO / S3 兼容后端 — 走 ``minio`` SDK。

    MinIO 启动示例: docker run -d -p 9000:9000 -p 9001:9001 --name minio \\
        -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \\
        quay.io/minio/minio server /data --console-address ":9001"
    """
    name = "minio"

    def __init__(self, endpoint: str, bucket_name: str, access_key: str,
                 secret_key: str, region: str = "us-east-1", secure: bool = False):
        from minio import Minio  # 局部 import
        from minio.error import S3Error  # noqa: F401  (用于异常类引用)
        self._minio = Minio
        self._S3Error = S3Error
        # endpoint 不应带 scheme, Minio 客户端由 secure 参数决定
        clean_endpoint = endpoint.replace("http://", "").replace("https://", "")
        self._client = Minio(clean_endpoint, access_key=access_key, secret_key=secret_key,
                             secure=secure, region=region)
        self._bucket_name = bucket_name
        self._endpoint = clean_endpoint
        self._region = region
        self._secure = secure
        # best-effort: 自动创建 bucket
        try:
            if not self._client.bucket_exists(bucket_name):
                self._client.make_bucket(bucket_name, location=region)
                logger.info(f"[minio] created bucket {bucket_name}")
        except Exception as e:
            logger.warning(f"[minio] ensure bucket {bucket_name} failed: {e}")

    def put(self, key: str, data: bytes, meta: Optional[dict] = None) -> str:
        from datetime import datetime
        import uuid as _uuid
        # minio SDK 要求文件流, 用 BytesIO
        stream = io.BytesIO(data)
        size = len(data)
        # metadata 必须为 dict[str,str]
        m: Dict[str, str] = {}
        if meta:
            for k, v in meta.items():
                m[str(k)] = str(v)
        etag = self._client.put_object(
            self._bucket_name, key, stream, size=size,
            content_type=m.get("content_type", "application/octet-stream"),
            metadata=m or None,
        )
        return etag.etag if hasattr(etag, "etag") else str(etag)

    def get(self, key: str) -> Optional[bytes]:
        try:
            resp = self._client.get_object(self._bucket_name, key)
            return resp.read()
        except self._S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return None
            logger.warning(f"[minio] get {key} failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"[minio] get {key} failed: {e}")
            return None

    def delete(self, key: str) -> bool:
        try:
            self._client.remove_object(self._bucket_name, key)
            return True
        except Exception as e:
            logger.warning(f"[minio] delete {key} failed: {e}")
            return False

    def list_keys(self, prefix: str = "") -> List[str]:
        keys: List[str] = []
        try:
            objs = self._client.list_objects(self._bucket_name, prefix=prefix, recursive=True)
            for o in objs:
                keys.append(o.key)
        except Exception as e:
            logger.warning(f"[minio] list prefix={prefix!r} failed: {e}")
        return keys

    def head(self, key: str) -> Optional[dict]:
        try:
            stat = self._client.stat_object(self._bucket_name, key)
            return {
                "etag": stat.etag,
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "metadata": dict(stat.metadata) if stat.metadata else {},
            }
        except self._S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return None
            logger.warning(f"[minio] head {key} failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"[minio] head {key} failed: {e}")
            return None

    def sign(self, key: str, expires: int = 3600, method: str = "GET") -> str:
        try:
            from datetime import timedelta
            # minio 7.2.0: presigned_get_object / presigned_put_object
            method_upper = method.upper()
            if method_upper == "PUT":
                url = self._client.presigned_put_object(self._bucket_name, key, expires=timedelta(seconds=expires))
            else:
                url = self._client.presigned_get_object(self._bucket_name, key, expires=timedelta(seconds=expires))
            return url
        except Exception as e:
            logger.warning(f"[minio] sign {key} failed: {e}")
            return ""

    def size(self) -> int:
        total = 0
        try:
            objs = self._client.list_objects(self._bucket_name, recursive=True)
            for o in objs:
                total += o.size
        except Exception:
            pass
        return total

    def health_check(self) -> dict:
        try:
            exists = self._client.bucket_exists(self._bucket_name)
            return {
                "backend": self.name,
                "status": "ok",
                "endpoint": self._endpoint,
                "bucket": self._bucket_name,
                "region": self._region,
                "secure": self._secure,
                "bucket_exists": exists,
            }
        except Exception as e:
            return {
                "backend": self.name,
                "status": "error",
                "error": str(e),
                "endpoint": self._endpoint,
                "bucket": self._bucket_name,
            }


# ── 4. 后端工厂 ─────────────────────────────────────────────────────────

def _build_object_backend(
    backend_type: BackendType,
    endpoint: str,
    bucket_name: str,
    access_key: str,
    secret_key: str,
    region: str = "cn-hangzhou",
    secure: bool = True,
) -> Tuple[_ObjectBackend, Optional[str]]:
    """构造后端; 失败时降级到 mock 并返回错误原因 (用于 health 报告)。"""
    if backend_type == BackendType.MOCK:
        return _MockObjectStore(), None

    if backend_type == BackendType.OSS2:
        if not (access_key and secret_key and endpoint and bucket_name):
            return (_MockObjectStore(),
                    f"oss2 backend requires OSS_ACCESS_KEY_ID + OSS_ACCESS_KEY_SECRET + "
                    f"OSS_ENDPOINT + OSS_BUCKET (got endpoint={endpoint!r}, "
                    f"bucket={bucket_name!r}, ak={'yes' if access_key else 'no'}, "
                    f"sk={'yes' if secret_key else 'no'})")
        try:
            return _Oss2ObjectStore(endpoint, bucket_name, access_key, secret_key, region), None
        except Exception as e:
            logger.warning(f"[oss_triple_bucket] build oss2 backend failed: {e}; fallback to mock")
            return _MockObjectStore(), f"oss2 build failed: {e}"

    if backend_type == BackendType.MINIO:
        if not (access_key and secret_key and endpoint and bucket_name):
            return (_MockObjectStore(),
                    f"minio backend requires MINIO_ACCESS_KEY + MINIO_SECRET_KEY + "
                    f"MINIO_ENDPOINT + MINIO_BUCKET (got endpoint={endpoint!r}, "
                    f"bucket={bucket_name!r}, ak={'yes' if access_key else 'no'}, "
                    f"sk={'yes' if secret_key else 'no'})")
        try:
            return _MinioObjectStore(endpoint, bucket_name, access_key, secret_key, region, secure), None
        except Exception as e:
            logger.warning(f"[oss_triple_bucket] build minio backend failed: {e}; fallback to mock")
            return _MockObjectStore(), f"minio build failed: {e}"

    return _MockObjectStore(), f"unknown backend type {backend_type!r}"


def _detect_backend_from_env() -> Tuple[BackendType, dict]:
    """从环境变量自动检测 backend。

    优先级:
    1. ``OSS_BACKEND`` 显式指定 (``oss2`` / ``minio`` / ``mock``)
    2. ``OSS_ACCESS_KEY_ID`` + ``OSS_ENDPOINT`` (阿里云) → oss2
    3. ``MINIO_ENDPOINT`` / ``OSS_MINIO_*`` → minio
    4. 都没有 → mock
    """
    explicit = os.environ.get("OSS_BACKEND", "").lower().strip()
    if explicit in ("mock", ""):
        return BackendType.MOCK, {}
    if explicit in ("oss2", "aliyun", "alioss"):
        return BackendType.OSS2, {
            "endpoint": os.environ.get("OSS_ENDPOINT", ""),
            "bucket_name": os.environ.get("OSS_BUCKET", "imdf-objects"),
            "access_key": os.environ.get("OSS_ACCESS_KEY_ID", ""),
            "secret_key": os.environ.get("OSS_ACCESS_KEY_SECRET", ""),
            "region": os.environ.get("OSS_REGION", "cn-hangzhou"),
            "secure": True,
        }
    if explicit in ("minio", "s3"):
        return BackendType.MINIO, {
            "endpoint": os.environ.get("MINIO_ENDPOINT", os.environ.get("OSS_ENDPOINT", "")),
            "bucket_name": os.environ.get("MINIO_BUCKET", os.environ.get("OSS_BUCKET", "imdf-objects")),
            "access_key": os.environ.get("MINIO_ACCESS_KEY", os.environ.get("OSS_ACCESS_KEY_ID", "")),
            "secret_key": os.environ.get("MINIO_SECRET_KEY", os.environ.get("OSS_ACCESS_KEY_SECRET", "")),
            "region": os.environ.get("MINIO_REGION", os.environ.get("OSS_REGION", "us-east-1")),
            "secure": _str2bool(os.environ.get("MINIO_SECURE", os.environ.get("OSS_SECURE", "false"))),
        }

    # 隐式探测
    if os.environ.get("OSS_ACCESS_KEY_ID") and os.environ.get("OSS_ENDPOINT"):
        return BackendType.OSS2, {
            "endpoint": os.environ.get("OSS_ENDPOINT", ""),
            "bucket_name": os.environ.get("OSS_BUCKET", "imdf-objects"),
            "access_key": os.environ.get("OSS_ACCESS_KEY_ID", ""),
            "secret_key": os.environ.get("OSS_ACCESS_KEY_SECRET", ""),
            "region": os.environ.get("OSS_REGION", "cn-hangzhou"),
            "secure": True,
        }
    if os.environ.get("MINIO_ENDPOINT"):
        return BackendType.MINIO, {
            "endpoint": os.environ.get("MINIO_ENDPOINT", ""),
            "bucket_name": os.environ.get("MINIO_BUCKET", "imdf-objects"),
            "access_key": os.environ.get("MINIO_ACCESS_KEY", ""),
            "secret_key": os.environ.get("MINIO_SECRET_KEY", ""),
            "region": os.environ.get("MINIO_REGION", "us-east-1"),
            "secure": _str2bool(os.environ.get("MINIO_SECURE", "false")),
        }

    return BackendType.MOCK, {}


def _str2bool(s: str) -> bool:
    return str(s).lower().strip() in ("1", "true", "yes", "on")


# ═══════════════════════════════════════════════════════════════════════════
#                      Vector / Table 桶 (保持内存实现)
# ═══════════════════════════════════════════════════════════════════════════

class _MockVectorStore:
    """模拟向量存储 (P0 兼容, 保留 cosine 检索)"""
    def __init__(self):
        self._vectors: Dict[str, List[float]] = {}
        self._metadata: Dict[str, dict] = {}

    def upsert(self, key: str, vector: List[float], meta: Optional[dict] = None):
        self._vectors[key] = vector
        self._metadata[key] = meta or {}

    def query(self, vector: List[float], top_k: int = 10) -> List[Tuple[str, float]]:
        results: List[Tuple[str, float]] = []
        for key, vec in self._vectors.items():
            if len(vec) != len(vector):
                continue
            dot = sum(a * b for a, b in zip(vec, vector))
            norm_a = sum(a * a for a in vec) ** 0.5
            norm_b = sum(b * b for b in vector) ** 0.5
            if norm_a and norm_b:
                sim = dot / (norm_a * norm_b)
                results.append((key, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def count(self) -> int:
        return len(self._vectors)


class _MockTableStore:
    """模拟表存储 (P0 兼容)"""
    def __init__(self):
        self._rows: List[dict] = []
        self._schema: List[str] = []

    def create_table(self, schema: List[str]):
        self._schema = schema
        self._rows = []

    def insert(self, row: dict):
        self._rows.append(row)

    def query(self, filters: Optional[Dict[str, Any]] = None) -> List[dict]:
        if not filters:
            return self._rows
        results = []
        for row in self._rows:
            match = True
            for k, v in filters.items():
                if k in row and row[k] != v:
                    match = False
                    break
            if match:
                results.append(row)
        return results

    def sync(self, rows: List[dict]):
        self._rows = rows

    def count(self) -> int:
        return len(self._rows)


# ═══════════════════════════════════════════════════════════════════════════
#                      SmartFolder Rule (P0 兼容)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Rule:
    """智能文件夹规则"""
    field: str
    operator: str  # contains, eq, ne, gt, gte, lt, lte, in
    value: Any

    def matches(self, item: dict) -> bool:
        val = item.get(self.field)
        if val is None:
            return False

        if self.operator == "contains":
            if isinstance(val, str) and isinstance(self.value, str):
                return str(self.value).lower() in str(val).lower()
            return str(self.value) in str(val)
        elif self.operator == "eq":
            return val == self.value
        elif self.operator == "ne":
            return val != self.value
        elif self.operator == "gt":
            return val > self.value
        elif self.operator == "gte":
            return val >= self.value
        elif self.operator == "lt":
            return val < self.value
        elif self.operator == "lte":
            return val <= self.value
        elif self.operator == "in":
            return val in self.value
        return False


@dataclass
class SmartFolder:
    """智能文件夹 - 基于规则的动态文件夹"""
    name: str
    rules: List[Rule] = field(default_factory=list)
    _cached_items: List[dict] = field(default_factory=list)
    _last_update: float = 0.0

    def match_items(self, items: List[dict]) -> List[dict]:
        matched = []
        for item in items:
            if all(r.matches(item) for r in self.rules):
                matched.append(item)
        self._cached_items = matched
        self._last_update = time.time()
        return matched

    def auto_update(self, source_items: List[dict]) -> List[dict]:
        return self.match_items(source_items)


# ═══════════════════════════════════════════════════════════════════════════
#                       OSSTripleManager (主类)
# ═══════════════════════════════════════════════════════════════════════════

class OSSTripleManager:
    """三桶管理器 — object / vector / table。

    P2-1-W3 升级: object 桶支持真 oss2 / minio 后端, 通过 ``set_backend()`` 动态切换。
    vector / table 暂保持内存实现 (后续 P3 阶段接入 PG/pgvector)。
    """

    def __init__(self, backend_type: Optional[BackendType] = None, **kwargs):
        # 解析 backend
        if backend_type is None:
            backend_type, env_kwargs = _detect_backend_from_env()
            if not kwargs and env_kwargs:
                kwargs = env_kwargs
        # 给 _build_object_backend 提供默认值 — mock 路径不需要这些参数, 但函数签名要齐
        kwargs.setdefault("endpoint", os.environ.get("OSS_ENDPOINT", ""))
        kwargs.setdefault("bucket_name", os.environ.get("OSS_BUCKET", "imdf-objects"))
        kwargs.setdefault("access_key", os.environ.get("OSS_ACCESS_KEY_ID", ""))
        kwargs.setdefault("secret_key", os.environ.get("OSS_ACCESS_KEY_SECRET", ""))
        kwargs.setdefault("region", os.environ.get("OSS_REGION", "cn-hangzhou"))
        kwargs.setdefault("secure", _str2bool(os.environ.get("OSS_SECURE", "true")))
        self._requested_backend = backend_type
        self._init_error: Optional[str] = None
        self._object_store, self._init_error = _build_object_backend(
            backend_type=backend_type, **kwargs
        )
        self.configs: Dict[BucketType, OSSBucketConfig] = {}
        self._vector_store = _MockVectorStore()
        self._table_store = _MockTableStore()
        self._smart_folders: Dict[str, SmartFolder] = {}
        self._initialized: bool = False
        logger.info(
            f"[oss_triple_bucket] initialized: backend={self._object_store.name} "
            f"(requested={self._requested_backend.value})"
        )

    # ── initialization ──────────────────────────────────────────────────

    def init_triple_buckets(self, object_cfg: OSSBucketConfig,
                            vector_cfg: OSSBucketConfig,
                            table_cfg: OSSBucketConfig) -> bool:
        """初始化三桶配置 (P0 兼容 API) — 同时切换 object 后端。"""
        self.configs[BucketType.OBJECT] = object_cfg
        self.configs[BucketType.VECTOR] = vector_cfg
        self.configs[BucketType.TABLE] = table_cfg
        # 用 object 配置切换后端
        self._object_store, self._init_error = _build_object_backend(
            backend_type=object_cfg.backend_type,
            endpoint=object_cfg.endpoint,
            bucket_name=object_cfg.bucket_name,
            access_key=object_cfg.access_key,
            secret_key=object_cfg.secret_key,
            region=object_cfg.region,
            secure=object_cfg.secure,
        )
        self._initialized = True
        return True

    def is_initialized(self) -> bool:
        return self._initialized

    def set_backend(self, backend_type: BackendType, **kwargs) -> dict:
        """运行时切换 object 后端。返回 health 信息。"""
        self._requested_backend = backend_type
        # 给 _build_object_backend 兜底默认
        kwargs.setdefault("endpoint", os.environ.get("OSS_ENDPOINT", ""))
        kwargs.setdefault("bucket_name", os.environ.get("OSS_BUCKET", "imdf-objects"))
        kwargs.setdefault("access_key", os.environ.get("OSS_ACCESS_KEY_ID", ""))
        kwargs.setdefault("secret_key", os.environ.get("OSS_ACCESS_KEY_SECRET", ""))
        kwargs.setdefault("region", os.environ.get("OSS_REGION", "cn-hangzhou"))
        kwargs.setdefault("secure", _str2bool(os.environ.get("OSS_SECURE", "true")))
        self._object_store, self._init_error = _build_object_backend(
            backend_type=backend_type, **kwargs
        )
        # 同步更新 OBJECT 桶 config
        if BucketType.OBJECT in self.configs:
            cfg = self.configs[BucketType.OBJECT]
            cfg.backend_type = backend_type
            for k, v in kwargs.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        health = self.health_check()
        return health

    def get_backend_name(self) -> str:
        return self._object_store.name

    def health_check(self) -> dict:
        h = self._object_store.health_check()
        if self._init_error:
            h["init_error"] = self._init_error
            h["requested_backend"] = self._requested_backend.value
        return h

    # ── object bucket operations (P0 兼容) ──────────────────────────────

    def upload_to_object_bucket(self, key: str, data: bytes,
                                metadata: Optional[dict] = None) -> str:
        """上传数据到对象存储桶 — 返回 etag"""
        return self._object_store.put(key, data, metadata)

    def download_from_object_bucket(self, key: str) -> Optional[bytes]:
        return self._object_store.get(key)

    def list_object_bucket(self, prefix: str = "") -> List[str]:
        """列出对象 — P0 原版无 prefix 参数, 这里兼容 (默认 prefix='')"""
        return self._object_store.list_keys(prefix)

    # ── P2-1-W3 新增 object 操作 ────────────────────────────────────────

    def delete_object(self, key: str) -> bool:
        """删除对象 (P0 没有此方法)"""
        return self._object_store.delete(key)

    def head_object(self, key: str) -> Optional[dict]:
        """取对象元数据 / 大小 / ETag"""
        return self._object_store.head(key)

    def presign_url(self, key: str, expires: Optional[int] = None,
                    method: str = "GET") -> str:
        """生成带签名 URL

        :param key: 对象 key
        :param expires: 过期秒数 (None → 使用 OBJECT config 的 presign_expires, 默认 3600)
        :param method: HTTP method, ``GET`` (下载) 或 ``PUT`` (上传)
        """
        if expires is None:
            obj_cfg = self.configs.get(BucketType.OBJECT)
            if obj_cfg is not None:
                expires = obj_cfg.presign_expires
            else:
                expires = 3600
        return self._object_store.sign(key, expires, method)

    def get_object_url(self, key: str) -> str:
        """非签名 URL — 仅 mock 后端有 ``mock://`` 形式, 真后端返回占位 (走 presign_url 取真 URL)"""
        if self._object_store.name == "mock":
            return f"mock://{key}"
        return self.presign_url(key, expires=60, method="GET")

    # ── vector bucket operations (P0 兼容) ──────────────────────────────

    def upload_to_vector_bucket(self, key: str, vector: List[float],
                                metadata: Optional[dict] = None) -> bool:
        self._vector_store.upsert(key, vector, metadata or {})
        return True

    def query_vector_bucket(self, vector: List[float],
                            top_k: int = 10) -> List[Tuple[str, float]]:
        return self._vector_store.query(vector, top_k)

    # ── table bucket operations (P0 兼容) ───────────────────────────────

    def create_table(self, schema: List[str]):
        self._table_store.create_table(schema)

    def insert_into_table(self, row: dict):
        self._table_store.insert(row)

    def sync_table_bucket(self, rows: List[dict]) -> int:
        self._table_store.sync(rows)
        return len(rows)

    def query_table(self, filters: Optional[Dict] = None) -> List[dict]:
        return self._table_store.query(filters)

    # ── usage stats (P0 兼容) ───────────────────────────────────────────

    def get_usage_stats(self) -> dict:
        return {
            "initialized": self._initialized,
            "backend": self._object_store.name,
            "object_bucket": {
                "total_keys": len(self._object_store.list_keys()),
                "total_size_bytes": self._object_store.size(),
                "config": self.configs.get(BucketType.OBJECT),
            },
            "vector_bucket": {
                "total_vectors": self._vector_store.count(),
                "config": self.configs.get(BucketType.VECTOR),
            },
            "table_bucket": {
                "total_rows": self._table_store.count(),
                "config": self.configs.get(BucketType.TABLE),
            },
            "smart_folders": {
                "count": len(self._smart_folders),
                "folder_names": list(self._smart_folders.keys()),
            },
        }

    # ── smart folder (P0 兼容) ──────────────────────────────────────────

    def create_smart_folder(self, name: str, rules: List[Rule]) -> SmartFolder:
        sf = SmartFolder(name=name, rules=rules)
        self._smart_folders[name] = sf
        return sf

    def get_smart_folder(self, name: str) -> Optional[SmartFolder]:
        return self._smart_folders.get(name)

    def update_smart_folder(self, name: str, source_items: List[dict]) -> List[dict]:
        sf = self._smart_folders.get(name)
        if not sf:
            return []
        return sf.auto_update(source_items)


# ═══════════════════════════════════════════════════════════════════════════
#                       Module-level Singleton
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_MANAGER: Optional[OSSTripleManager] = None


def get_default_manager() -> OSSTripleManager:
    """懒加载默认 manager — 进程内单例。

    任何模块 ``from engines.oss_triple_bucket import get_default_manager`` 拿到的
    都是同一个实例, 避免每个请求都重新解析 env / 重建后端。
    """
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = OSSTripleManager()
        # P0 兼容: 同时填充 configs
        _DEFAULT_MANAGER.init_triple_buckets(
            object_cfg=OSSBucketConfig(
                bucket_type=BucketType.OBJECT,
                endpoint=os.environ.get("OSS_ENDPOINT", ""),
                bucket_name=os.environ.get("OSS_BUCKET", "imdf-objects"),
                region=os.environ.get("OSS_REGION", "cn-hangzhou"),
                access_key=os.environ.get("OSS_ACCESS_KEY_ID", ""),
                secret_key=os.environ.get("OSS_ACCESS_KEY_SECRET", ""),
                backend_type=_DEFAULT_MANAGER._requested_backend,
                secure=_str2bool(os.environ.get("OSS_SECURE", "true")),
                presign_expires=int(os.environ.get("OSS_PRESIGN_EXPIRES", "3600")),
            ),
            vector_cfg=OSSBucketConfig(
                bucket_type=BucketType.VECTOR,
                endpoint="",
                bucket_name="imdf-vectors",
            ),
            table_cfg=OSSBucketConfig(
                bucket_type=BucketType.TABLE,
                endpoint="",
                bucket_name="imdf-tables",
            ),
        )
    return _DEFAULT_MANAGER


def reset_default_manager() -> None:
    """测试用 — 重置 singleton 强制下次重新构造 (env 变更后调用)"""
    global _DEFAULT_MANAGER
    _DEFAULT_MANAGER = None


# ═══════════════════════════════════════════════════════════════════════════
#                       Backward-compat Exports
# ═══════════════════════════════════════════════════════════════════════════

# 旧代码可能直接 import ``OSSTripleBucket`` 之类; 这里兜底暴露
OSSTripleBucket = OSSTripleManager  # alias for typo-safe import
