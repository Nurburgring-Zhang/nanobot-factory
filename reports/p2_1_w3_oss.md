# P2-1-W3: OSS / MinIO 真接入 — 交付报告

> **Worker**: coder (mvs_1dc715dd88d74e9e9b15bfc4fdd35c34)
> **Plan**: plan_650d2978
> **Date**: 2026-06-22
> **Status**: ✅ DONE (50/50 tests PASS)

---

## 1. 目标

把 `oss_triple_bucket.py` (9KB 占位) 改成真 OSS 接入, 同时支持阿里云 OSS (`oss2` SDK) 和 MinIO / S3 (`minio` SDK), 通过环境变量一键切换。无凭证时自动 fallback 到内存 mock, 永不出 500。

---

## 2. 改动的文件

| 文件 | 操作 | 行数 | 摘要 |
|---|---|---|---|
| `backend/imdf/engines/oss_triple_bucket.py` | **重写** | 290 → 768 | 三后端 (`mock` / `oss2` / `minio`) + env 自动探测 + 9 个新方法 + 进程单例 |
| `backend/imdf/api/oss_routes.py` | **新建** | 0 → 360 | 11 个 FastAPI 端点: upload(2) / download / head / sign(2) / delete / list / exists / health |
| `backend/imdf/api/canvas_web.py` | **微改** | +9 | 在尾部增加 `oss_router` 挂载 (`app.include_router(oss_router)`) |
| `backend/imdf/api/p1_c_w1_routes.py` | **改造** | +120 / -30 | `/api/assets/upload` 改用 OSS 落对象, `/download` 优先 OSS 读, 新增 `/sign` 端点 |
| `backend/imdf/config/settings.py` | **新增** | +37 | OSS / MinIO 配置中心 (env → typed 字段) |
| `backend/imdf/requirements.txt` | **追加** | +3 | `oss2>=2.18.0` + `minio>=7.2.0` |
| `backend/tests/test_p2_1_w3_oss.py` | **新建** | 644 | 50 个测试覆盖 engine + API + 集成路径 |

---

## 3. 架构

### 3.1 Engine (`engines/oss_triple_bucket.py`)

```
                    ┌─────────────────────┐
                    │  OSSTripleManager   │  (进程单例: get_default_manager)
                    └─────────┬───────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     _MockObjectStore   _Oss2ObjectStore   _MinioObjectStore
     (内存 Dict)        (oss2 SDK)         (minio SDK)
```

所有后端实现同一接口:
```python
class _ObjectBackend(Protocol):
    def put(self, key, data, meta=None) -> str  # → etag
    def get(self, key) -> Optional[bytes]
    def delete(self, key) -> bool
    def list_keys(self, prefix='') -> List[str]
    def head(self, key) -> Optional[dict]      # etag/size/ct/last_modified
    def sign(self, key, expires=3600, method='GET') -> str
    def size(self) -> int
    def health_check(self) -> dict
```

### 3.2 环境变量 → 后端选择

| 变量 | 默认 | 用途 |
|---|---|---|
| `OSS_BACKEND` | `auto` | `oss2` / `minio` / `mock` / `auto` (env 探测) |
| `OSS_ENDPOINT` | `""` | 阿里云 endpoint, 如 `oss-cn-hangzhou.aliyuncs.com` |
| `OSS_BUCKET` | `imdf-objects` | 默认 bucket 名 |
| `OSS_REGION` | `cn-hangzhou` | 阿里云 region |
| `OSS_ACCESS_KEY_ID` | `""` | 阿里云 AccessKeyId / MinIO root user |
| `OSS_ACCESS_KEY_SECRET` | `""` | 阿里云 AccessKeySecret / MinIO root password |
| `OSS_SECURE` | `true` | `true` → https, `false` → http (MinIO) |
| `OSS_PRESIGN_EXPIRES` | `3600` | 默认签名 URL 过期秒数 |
| `MINIO_ENDPOINT` | `OSS_ENDPOINT` | MinIO 服务地址 (无 scheme) |
| `MINIO_BUCKET` | `OSS_BUCKET` | MinIO bucket 名 |
| `MINIO_ACCESS_KEY` | `OSS_ACCESS_KEY_ID` | MinIO root user (默认复用 OSS AK) |
| `MINIO_SECRET_KEY` | `OSS_ACCESS_KEY_SECRET` | MinIO root password |
| `MINIO_SECURE` | `false` | MinIO 通常 http (本地开发) |

**冷启动 fallback**: 缺凭证 / SDK 不可用 / 凭证错 → 自动降级 mock, `_init_error` 字段会记录原因, 端点继续返回 200。

### 3.3 API 端点 (`api.oss_routes.py`)

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/oss/health` | GET | 后端连通性 + endpoint / bucket 信息 |
| `/api/v1/oss/list?prefix=...` | GET | 按 prefix 列对象 (max 10000) |
| `/api/v1/oss/upload` | POST (multipart) | 上传文件, 自动 uuid 生成 key |
| `/api/v1/oss/upload-bytes` | POST (JSON) | SDK 风格上传, body 含 `data_b64` |
| `/api/v1/oss/download/{key:path}` | GET | 拉取对象 (content-type 透传) |
| `/api/v1/oss/head/{key:path}` | GET / HEAD | 元数据 (size/etag/ct) |
| `/api/v1/oss/object/{key:path}` | DELETE | 删除 (幂等, 不存在 200) |
| `/api/v1/oss/sign/{key:path}` | GET | 生成 GET 签名 URL |
| `/api/v1/oss/sign/{key:path}` | POST | 生成 PUT 签名 URL (method=GET/PUT) |
| `/api/v1/oss/exists/{key:path}` | GET | exists / size / etag 探测 |

**安全**:
- `_validate_key` 拒绝 `..` / 控制字符 / 超长 key, 防路径穿越
- 上传 size 限制 200 MB (413)
- 签名 URL 过期 1..86400 秒
- 空文件 / 非法 b64 → 400, 不进 500

### 3.4 P1-C-W1 `/api/assets/*` 集成

| 端点 | 行为 |
|---|---|
| `POST /api/assets/upload` | **优先 OSS** (`storage: "oss"`, `oss_key: "p1_c_w1/assets/{id}_{name}"`); 失败降级本地 |
| `GET /api/assets/{id}/download` | **优先 OSS** (响应头 `X-Storage: oss`, `X-OSS-Backend: <name>`); OSS 不可用降级本地 FileResponse |
| `DELETE /api/assets/{id}` | 同步清理 OSS 对象 + 本地文件 |
| `GET /api/assets/{id}/sign?expires=N` | **新增** — 生成 OSS 签名 URL (无 oss_key 时 400) |

向后兼容: 老 asset (无 `oss_key` 字段) 仍能 list / download (走本地 fallback), sign 报 400 而非 500。

---

## 4. 验证结果

### 4.1 测试覆盖 (50 cases, ALL PASS)

```
$ pytest backend/tests/test_p2_1_w3_oss.py -v
============================= 50 passed in 0.90s =============================
```

| 测试类 | 用例 | 状态 |
|---|---|---|
| `TestMockBackend` | 12 | ✅ CRUD / head / presign / health / usage_stats |
| `TestBackendSelection` | 10 | ✅ oss2 / minio fallback + env 探测 + set_backend + SDK import |
| `TestVectorTableBuckets` | 3 | ✅ vector cosine 查询 + table filter + sync |
| `TestSmartFolder` | 2 | ✅ 多 rule 组合 + 8 种 operator 边界 |
| `TestSingleton` | 2 | ✅ 进程单例 + env 自动 init |
| `TestOssApiRoutes` | 16 | ✅ 9 端点 + 路径穿越 + 4xx 校验 + 空文件 / 非法 b64 |
| `TestAssetsIntegration` | 5 | ✅ upload/download/sign/delete 全路径 + legacy asset 兼容 |

### 4.2 端到端冒烟

```
$ python -c "from api.oss_routes import router as oss_router; ..."
oss_routes imported OK, 11 routes:
  ['GET']    /api/v1/oss/health
  ['GET']    /api/v1/oss/list
  ['POST']   /api/v1/oss/upload
  ['POST']   /api/v1/oss/upload-bytes
  ['GET']    /api/v1/oss/download/{key:path}
  ['HEAD']   /api/v1/oss/head/{key:path}
  ['GET']    /api/v1/oss/head/{key:path}
  ['DELETE'] /api/v1/oss/object/{key:path}
  ['GET']    /api/v1/oss/sign/{key:path}
  ['POST']   /api/v1/oss/sign/{key:path}
  ['GET']    /api/v1/oss/exists/{key:path}
Default manager backend: mock
Downloaded: b'OK'
Health: {'backend': 'mock', 'status': 'ok', 'mode': 'in-memory', 'object_count': 1, 'total_bytes': 2}
```

### 4.3 import 链验证

```
$ python -c "from api import p1_c_w1_routes, oss_routes; from config import settings"
p1_c_w1_routes loaded: 27 routes
oss_routes loaded: 11 routes
OSS_BACKEND: mock
Settings ok
```

### 4.4 真凭证端到端 (部署时)

无真凭证 (CI 沙箱无 AK), 仅验证 SDK 导入 + fallback 路径。真部署时:

1. 设 `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` / `OSS_ENDPOINT` / `OSS_BUCKET`
2. 启动服务, 观察 `get_default_manager().health_check()` 返回 `status: ok`
3. 调 `POST /api/v1/oss/upload` → 应返回 `backend: oss2` + 真实 etag
4. 调 `GET /api/v1/oss/sign/{key}` → 拿到阿里云签名 URL
5. 在浏览器/curl 用该 URL 下载, 200 + bytes

---

## 5. 已知约束

1. **vector / table 桶仍是内存**: 后续 P3 阶段接 PG + pgvector (本次范围外)
2. **mock 后端数据不持久**: 重启进程清空, 仅用于 dev/CI
3. **OSS endpoint 验证**: 健康检查对真阿里云会调 `get_bucket_info()`, 这是有网络调用的; 无网络时降级 mock 不影响端点
4. **max upload 200 MB**: 单次请求限制, 大文件建议走 PUT 签名 URL 直传

---

## 6. 文件清单 (供 verifier 核对)

```
backend/imdf/engines/oss_triple_bucket.py          768 行 (重写)
backend/imdf/api/oss_routes.py                    360 行 (新建)
backend/imdf/api/canvas_web.py                   4763 行 (+9 行, include_router)
backend/imdf/api/p1_c_w1_routes.py                798 → 895 行 (改造)
backend/imdf/config/settings.py                  257 → 294 行 (+OSS 字段)
backend/imdf/requirements.txt                       +3 行
backend/tests/test_p2_1_w3_oss.py                 644 行 (新建, 50 用例)
```
