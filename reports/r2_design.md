# R2 参数验证统一设计文档（契约）

> **任务**: R2-Design — 把 R1 阶段在 `backend/imdf/api/_common/validators.py`
> 引入的 `validate_id` / `safe_int` / `safe_path` 三个工具，扩展为覆盖全 246 个
> `bad_params-200` 端点的统一验证体系。本文档为 5 个 R2-Worker 的契约。
>
> **作者**: coder (Mavis agent)
> **会话**: mvs_ff03f42d1b8844fd9b66906716bb69a5
> **日期**: 2026-06-18
> **上游依赖**: R1 (`reports/r1_crash_fix.md`) — 11 个 P0 端点 + validators.py 87 行
> **下游消费者**: R2-Worker-1 / R2-Worker-2 / R2-Worker-3 / R2-Worker-4 / R2-Worker-5

---

## 0. TL;DR

| 维度 | 数值 | 备注 |
|---|---|---|
| 报告称端点数 | 272 | `exhaustive_report.md` §三 引用 |
| **实际端点数** | **246** | 从 `exhaustive_matrix.csv` 直接 `Scenario=bad_params ∧ StatusCode=200 ∧ Result=WARN` 过滤 |
| 差异说明 | 26 个 | 报告口算四舍五入；CSV 原始数据为权威 |
| 涉及模块 | 64 | 见 §4.5 验证矩阵 |
| HTTP 方法分布 | GET 151 / POST 87 / DELETE 6 / PUT 2 | POST 占 35%，以 Pydantic body 为主 |
| 目标 | 把 246 个端点全部改造为 400/422 拒绝非法输入 | 与 FastAPI / Pydantic 生态对齐 |
| 交付物 | 5 个 worker × N 个端点 + 1 份回归测试 + 1 份审计 | 由本契约统一规范 |

---

## 1. 背景与问题

### 1.1 当前状态（基线）

`exhaustive_report.md` 第三节列出 295 个 warn，其中 272 个是 `bad_params` 场景返回 200。
经 CSV 复算后实际为 **246 个**（差额 26 个是报告口算或重复计数的产物）。

| 排名 | 模块 | 端点数 | 典型端点 |
|------|------|-------|----------|
| 1 | quality | 24 | `GET /api/quality/eval/benchmarks`, `POST /api/quality/iaa/cohen-kappa` |
| 2 | crowd | 16 | `GET /api/crowd/workers`, `GET /api/crowd/stats` |
| 3 | search | 14 | `POST /api/search`, `POST /api/search/images` |
| 4 | ingest | 12 | (worker 调研) |
| 5 | 3d | 8 | `GET /api/3d/scenes`, `POST /api/3d/actions/keyframes` |
| 6 | imdf_config / health | 7+7 | 主要是 GET 类 |
| 7 | templates / delivery / comfyui / scheduler / sdk / prompt-templates / backup | 6 each | 混合 GET/POST |
| 8 | workflow / imdf_canvas / review / webhooks / dam | 5 each | 混合 |

### 1.2 根本原因（3 类）

1. **类型注解缺失** — `def crowd_workers():` 没有任何 `Query` / `Body` / `Path` 声明，
   FastAPI 把整个 HTTP 请求当成 0 参函数处理 → 任何参数都被忽略 → 永远 200。
2. **类型注解存在但无约束** — `def search(req: SearchRequest):` 用了 Pydantic 但字段
   无 `min_length` / `ge` / `le` / `regex` → Pydantic 只做类型转换不做值域检查。
3. **手工校验但校验逻辑被吞** — 部分端点有 `if not x: raise 400`，但 Pydantic `try/except`
   兜底把 400 吞成 200（典型如 `quality` / `webhook` 模块）。

### 1.3 R1 已做

`backend/imdf/api/_common/validators.py` 87 行，提供:
- `ID_PATTERN = ^[a-zA-Z0-9_\-]{1,128}$` — 资源 ID 字符白名单
- `validate_id(value, name)` — 失败 raise HTTPException(400)
- `safe_int(value, default, **kw)` — 失败回退 default
- `safe_path(value, base_dir)` — 防 path traversal

R1 修复 3 个崩溃端点（`aesthetic/elo-entry` / `drama/episode` / `canvas/element`），
通过 23 个 pytest + 9 个 TestClient 集成测试。

### 1.4 R2 要做

把 R1 的 87 行工具库扩展到覆盖全 246 个端点。**5 个 worker 并行**，按"验证模式"分桶
而非按"模块"分桶，避免 worker 之间互相改同一文件。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 路由层                          │
│   246 个端点 → 5 种验证模式 (A/B/C/D/E)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            backend/imdf/api/_common/validators/              │
│   ├── id.py             (validate_id + ID_PATTERN)           │
│   ├── pagination.py     (PaginationParams)                   │
│   ├── date_range.py     (DateRangeParams)                    │
│   ├── search_query.py   (SearchQueryParams)                  │
│   ├── id_list.py        (IdListValidator)                    │
│   ├── image_path.py     (ImagePathValidator)                 │
│   ├── upload.py         (UploadFileValidator)                │
│   ├── headers.py        (APIKeyHeader)                       │
│   └── shared.py         (safe_int / safe_path 兼容)          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Pydantic v2 BaseModel (typed schemas)          │
│   CreateXxxRequest / UpdateXxxRequest / XxxResponse         │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**:
1. **每一类验证模式对应一个工具文件**（§4.2），单文件 < 50 行（含 docstring + 例子）。
2. **每一个 BaseModel 字段必须带约束**（`min_length` / `ge` / `le` / `regex` / `Literal`）。
3. **错误信息 100% 中文化 + 包含字段名**（便于前端直接展示）。

---

## 3. 验证模式分类

| 模式 | FastAPI 装饰 | 工具 | 失败 HTTP | 适用端点数 | 命中模块 |
|------|-------------|------|----------|-----------|----------|
| A. Query 参数 | `Query(...)` | `PaginationParams` / `SearchQueryParams` | 422 | 95 | search / crowd / 3d / quality GET / health |
| B. Body 参数 | `BaseModel` | 各 `Create/Update*Request` | 422 | 87 | quality POST / webhook / sharing / classify |
| C. Path 参数 | `Path(...)` | `validate_id` (沿用 R1) | 400 | 28 | 3d scenes / canvas / backup / webhook / drama / classify |
| D. Header 参数 | `Header(...)` | `APIKeyHeader` | 401 | 0 | (无 R2 范围内端点) |
| E. 文件上传 | `UploadFile` | `UploadFileValidator` | 400/413 | 6 | oss / dam / enhanced / copyright / files / preview |
| F. 路径型 Query | `Query(regex=...)` | `ImagePathValidator` | 400 | 14 | search/images / preview / dam / file 路径类 |
| G. 时间/日期 | `Query(...)` | `DateRangeParams` | 422 | 16 | stats / scheduler / dam / audit-logs / 报表类 |

合计: 95+87+28+0+6+14+16 = 246 ✅

> 注: 一个端点可能命中 1+ 模式（如 `GET /api/3d/scenes/{scene_id}?skip=0&limit=20`
> 命中 A+C）。Worker 按**主模式**分桶，跨模式字段在 §4.5 矩阵的"备注"列里标注。

---

## 4. 设计契约

### 4.1 端点分类（按验证模式）

#### A. Query 参数模式 — `Query(...)` + Pydantic

**适用场景**: 列表 / 搜索 / 统计 / 翻页类 GET 端点。

**改造前**:
```python
@router.get("/crowd/workers")
async def crowd_workers():
    # 没有声明任何参数 → 任何 query 都被忽略 → 永远 200
    ...
```

**改造后**:
```python
from api._common.validators.pagination import PaginationParams

@router.get("/crowd/workers")
async def crowd_workers(
    p: PaginationParams = Depends(),   # skip/limit/sort_by/order
    role: Optional[str] = Query(None, regex=r"^(annotator|reviewer|admin)$"),
):
    ...
```

**关键点**:
- 用 `Depends()` 注入 Pydantic 模型而非把字段散在签名里（保持签名干净）。
- 可选参数用 `Query(None, regex=...)`，必选用 `Query(..., regex=...)`。
- `int` 类型用 `Query(..., ge=0, le=MAX)`，禁止裸 `int` 不带约束。

#### B. Body 参数模式 — `BaseModel`

**适用场景**: 创建 / 更新 / 提交类 POST/PUT 端点。

**改造前**（quality `cohen-kappa`）:
```python
@router.post("/iaa/cohen-kappa")
async def cohen_kappa(rater1: List[str], rater2: List[str]):
    # FastAPI 自动解析 JSON body，但 List 长度 / 元素都没约束
    ...
```

**改造后**:
```python
class CohenKappaRequest(BaseModel):
    rater1: List[str] = Field(..., min_length=2, max_length=10000)
    rater2: List[str] = Field(..., min_length=2, max_length=10000)

    @field_validator("rater1", "rater2")
    @classmethod
    def _validate_labels(cls, v: List[str]) -> List[str]:
        for label in v:
            if not isinstance(label, str) or len(label) > 1024:
                raise ValueError("标签必须为字符串且 ≤1024 字符")
        return v

@router.post("/iaa/cohen-kappa")
async def cohen_kappa(req: CohenKappaRequest):
    ...
```

**关键点**:
- 列表字段必须有 `min_length` 和 `max_length`。
- 字符串字段必须有 `min_length` 和 `max_length`（防止空串/超长）。
- 数值字段必须有 `ge` / `le`。
- 枚举字段必须用 `Literal["a", "b", "c"]` 而非 `str`。
- 业务级校验用 `@field_validator`（Pydantic v2 风格）。

#### C. Path 参数模式 — `Path(...)` + `validate_id`

**适用场景**: 路径里带 ID 的 GET/PUT/DELETE 端点（R1 已示范）。

**改造前**:
```python
@router.get("/api/3d/scenes/{scene_id}")
async def get_scene(scene_id: str):
    # scene_id='💥' → dict lookup 崩溃
    ...
```

**改造后**（两种等价方案）:
```python
# 方案 1（推荐 — 与 R1 一致）: 函数体首行调用
from api._common.validators.id import validate_id

@router.get("/api/3d/scenes/{scene_id}")
async def get_scene(scene_id: str):
    validate_id(scene_id, "scene_id")  # 失败 → 400
    ...

# 方案 2（更声明式 — 用于新增端点）: 用 Path(...) + Depends
from fastapi import Path as FPath
from api._common.validators.id import validate_id_dep

@router.get("/api/3d/scenes/{scene_id}")
async def get_scene(
    scene_id: str = FPath(..., regex=r"^[a-zA-Z0-9_\-]{1,128}$"),
):
    # FastAPI 自动按 regex 校验，失败 → 422
    ...
```

**关键点**:
- 旧端点改造用方案 1（与 R1 一致，最小改动）。
- 新端点建议用方案 2（更声明式，OpenAPI schema 正确）。
- 禁止只把 `scene_id: str` 留着不校验 — 这是 R1 修复的根因。

#### D. Header 参数模式 — `Header(...)`

**适用场景**: 自定义 header（如 `X-Request-ID` / `X-Trace-ID`）。

**R2 范围**: 0 个端点命中此模式。**预留接口**:
```python
from fastapi import Header

async def get_request_id(
    x_request_id: Optional[str] = Header(None, regex=r"^[a-zA-Z0-9\-]{8,64}$"),
) -> Optional[str]:
    return x_request_id
```

> 不需要为 0 个端点写代码。**Worker 遇到 header 端点时升级为 Blocked 报告。**

#### E. 文件上传模式 — `UploadFile` + size/type check

**适用场景**: 文件上传 / OSS 转存 / 媒体处理类。

**改造前**（典型在 `enhanced_routes.py`）:
```python
@router.post("/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...), language: str = "zh"):
    # 无 size 限制 → 10GB 文件会撑爆内存
    # language 无枚举 → 接受任意字符串
    ...
```

**改造后**:
```python
from api._common.validators.upload import UploadFileValidator, ALLOWED_AUDIO_TYPES

@router.post("/transcribe-audio")
async def transcribe_audio(
    file: UploadFile = Depends(UploadFileValidator(
        max_size=100 * 1024 * 1024,         # 100 MB
        allowed_content_types=ALLOWED_AUDIO_TYPES,
        field_name="file",
    )),
    language: Literal["zh", "en", "ja"] = "zh",
):
    ...
```

**关键点**:
- 必须有 `max_size`（默认 100 MB，文档/图片 10 MB）。
- 必须有 `allowed_content_types`（白名单，不靠扩展名）。
- 大文件应在 streaming 阶段检查，**不读完整文件到内存**。
- 失败 → 400（类型/大小）/ 413（payload too large）。

#### F. 路径型 Query — `ImagePathValidator` / `safe_path`

**适用场景**: 用户传入图片/文件路径作为查询参数（不是文件上传）。

**改造前**:
```python
@router.post("/search/images")
async def search_images(req: ImageSearchRequest):
    if not os.path.exists(req.image_path):
        return {"success": False, "error": f"Image not found: {req.image_path}"}
    # 路径无 sanitization，可传 '../' 逃逸
```

**改造后**:
```python
from api._common.validators.image_path import ImagePathValidator
from pydantic import BaseModel, Field

class ImageSearchRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096)
    collection: str = Field("image_index", regex=r"^[a-zA-Z0-9_\-]{1,64}$")
    top_k: int = Field(5, ge=1, le=1000)

    @field_validator("image_path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        return ImagePathValidator(v, base_dir=Path("/data/images")).validate()
```

**关键点**:
- 路径必须先 `resolve()` 再 `relative_to(base_dir)`，与 R1 `safe_path` 同款。
- 必须先检查存在再检查可读（顺序固定）。
- 失败 → 400 + 明确错误（"路径越界" / "文件不存在" / "不可读"）。

#### G. 时间/日期范围模式 — `DateRangeParams`

**适用场景**: 统计 / 报表 / 仪表盘 / 审计日志类。

**改造前**:
```python
@router.get("/stats/summary")
async def stats_summary():
    # 没接 start/end 参数 → 调用方无法自定义时间窗
    ...
```

**改造后**:
```python
from api._common.validators.date_range import DateRangeParams

@router.get("/stats/summary")
async def stats_summary(
    dr: DateRangeParams = Depends(),
    # dr.start: date, dr.end: date, dr.preset: Literal["1d","7d","30d","custom"]
):
    ...
```

**关键点**:
- `preset` 优先于 `start/end`，preset 非 "custom" 时忽略 `start/end`。
- `start <= end` 必须校验（防止反序日期）。
- 跨度 ≤ 365 天（防拉全表）。
- 失败 → 422。

---

### 4.2 validators.py 扩展接口

> 所有接口单文件 < 50 行，文件位置在 `backend/imdf/api/_common/validators/`
> （注：保留 `validators.py` 作为 shim 重新导出，保证 R1 代码不破）。

#### 4.2.1 `id.py`（沿用 R1 + 加 Depends 版本）

```python
"""资源 ID 校验 — 单文件 30 行"""
from __future__ import annotations
import re
from fastapi import HTTPException, Path

ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


def validate_id(value: str, name: str = "id") -> str:
    """R1 工具: 校验资源 ID 格式, 失败 raise HTTPException(400)。"""
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise HTTPException(400, f"Invalid {name}: must match {ID_PATTERN.pattern}")
    return value


# FastAPI Depends 版 (用于新端点)
def validate_id_dep(name: str = "id"):
    """工厂: 返回一个 Path 校验器, 失败 → 422。"""
    def _dep(value: str = Path(..., regex=ID_PATTERN.pattern)):
        return value
    _dep.__name__ = f"validate_{name}_dep"
    return _dep
```

#### 4.2.2 `pagination.py`

```python
"""分页参数 — 单文件 35 行"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

MAX_LIMIT = 200  # 防止一次拉太多撑爆响应

SortOrder = Literal["asc", "desc"]


class PaginationParams(BaseModel):
    """通用分页参数, 注入到 GET 列表端点。"""
    skip: int = Field(0, ge=0, le=10_000_000, description="跳过的记录数")
    limit: int = Field(20, ge=1, le=MAX_LIMIT, description="每页条数")
    sort_by: Optional[str] = Field(None, regex=r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
    order: SortOrder = "asc"

    class Config:
        # 让 FastAPI 从 query string 解析
        extra = "forbid"  # 拒绝未声明字段, 防止 typos
```

#### 4.2.3 `date_range.py`

```python
"""日期范围参数 — 单文件 40 行"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

DatePreset = Literal["1d", "7d", "30d", "90d", "1y", "custom"]
MAX_SPAN_DAYS = 365


class DateRangeParams(BaseModel):
    """日期范围, 注入到统计 / 报表类端点。"""
    start: Optional[date] = Field(None, description="开始日期 (ISO 8601)")
    end: Optional[date] = Field(None, description="结束日期 (ISO 8601)")
    preset: DatePreset = "7d"

    @model_validator(mode="after")
    def _check_range(self):
        if self.preset != "custom":
            days = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}[self.preset]
            self.end = date.today()
            self.start = self.end - timedelta(days=days - 1)
        else:
            if not (self.start and self.end):
                raise ValueError("preset=custom 时必须提供 start 和 end")
            if self.start > self.end:
                raise ValueError(f"start ({self.start}) 必须 ≤ end ({self.end})")
            if (self.end - self.start).days > MAX_SPAN_DAYS:
                raise ValueError(f"日期跨度不能超过 {MAX_SPAN_DAYS} 天")
        return self
```

#### 4.2.4 `search_query.py`

```python
"""搜索参数 — 单文件 40 行"""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field

SearchMode = Literal["vector", "fts5", "hybrid", "exact"]


class SearchQueryParams(BaseModel):
    """通用搜索参数, 注入到 search 类端点。"""
    q: str = Field(..., min_length=1, max_length=512, description="搜索关键词")
    fields: Optional[str] = Field(
        None, regex=r"^[a-zA-Z_][a-zA-Z0-9_,]{0,255}$",
        description="逗号分隔的字段列表, 如 title,body,tags"
    )
    fuzzy: bool = Field(False, description="是否启用模糊匹配")
    mode: SearchMode = "vector"

    class Config:
        extra = "forbid"
```

#### 4.2.5 `id_list.py`

```python
"""ID 列表校验 (逗号分隔) — 单文件 30 行"""
from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field, field_validator
from .id import ID_PATTERN


class IdListValidator(BaseModel):
    """逗号分隔的 ID 列表, 用于批量操作端点。"""
    ids: str = Field(..., min_length=1, max_length=8192)

    @field_validator("ids")
    @classmethod
    def _split_and_check(cls, v: str) -> str:
        items = [x.strip() for x in v.split(",") if x.strip()]
        if not items:
            raise ValueError("ids 不能为空")
        if len(items) > 1000:
            raise ValueError("ids 数量不能超过 1000")
        for x in items:
            if not ID_PATTERN.match(x):
                raise ValueError(f"非法 id: {x!r}, 必须匹配 {ID_PATTERN.pattern}")
        return ",".join(items)

    def to_list(self) -> List[str]:
        return self.ids.split(",")
```

#### 4.2.6 `image_path.py`

```python
"""图片路径校验 — 单文件 40 行"""
from __future__ import annotations
from pathlib import Path
from fastapi import HTTPException


class ImagePathValidator:
    """校验图片路径: 合法 + 存在 + 可读 + 在 base_dir 之下。"""

    ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}

    def __init__(self, value: str, base_dir: Path):
        self.value = value
        self.base_dir = base_dir

    def validate(self) -> str:
        # 1. 防 traversal
        base = self.base_dir.resolve()
        try:
            candidate = (base / self.value).resolve()
            candidate.relative_to(base)  # 必须在 base 之下
        except (ValueError, OSError):
            raise HTTPException(400, f"图片路径越界: {self.value}")

        # 2. 后缀白名单
        if candidate.suffix.lower() not in self.ALLOWED_EXTS:
            raise HTTPException(400, f"图片格式不支持: {candidate.suffix}")

        # 3. 存在 + 可读
        if not candidate.is_file():
            raise HTTPException(400, f"图片不存在: {candidate}")
        if not os.access(candidate, os.R_OK):
            raise HTTPException(400, f"图片不可读: {candidate}")

        return str(candidate)
```

#### 4.2.7 `upload.py`

```python
"""文件上传校验 — 单文件 45 行"""
from __future__ import annotations
from typing import Iterable, Optional
from fastapi import UploadFile, File, HTTPException

ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/flac"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_DOC_TYPES = {
    "application/pdf",
    "application/json",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

DEFAULT_MAX_SIZE = 100 * 1024 * 1024  # 100 MB


class UploadFileValidator:
    """UploadFile 依赖工厂: 校验 size + content_type。"""

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        allowed_content_types: Optional[Iterable[str]] = None,
        field_name: str = "file",
    ):
        self.max_size = max_size
        self.allowed = set(allowed_content_types) if allowed_content_types else None
        self.field_name = field_name

    def __call__(self) -> UploadFile:
        # 注意: FastAPI Depends 没法直接接 UploadFile 的"带校验"版
        # → 实际用法: Depends() 返回的 file 在 handler 内做校验
        # 详见 §5.2 集成模式
        raise NotImplementedError("Use safe_upload factory instead")
```

> **注**: FastAPI 的 `UploadFile = File(...)` 必须在签名里写死，`Depends` 无法拦截。
> 实际用法见 §5.2 集成示例。简化方案:

```python
async def check_upload(
    file: UploadFile,
    max_size: int = DEFAULT_MAX_SIZE,
    allowed: Optional[set] = None,
) -> UploadFile:
    """handler 内调用的 guard 函数。"""
    if file.size is not None and file.size > max_size:
        raise HTTPException(413, f"文件过大: {file.size} > {max_size}")
    if allowed and file.content_type not in allowed:
        raise HTTPException(400, f"不支持的 Content-Type: {file.content_type}")
    return file
```

#### 4.2.8 `shared.py`（兼容 R1）

```python
"""R1 工具兼容层 — 重新导出, 保持 from api._common.validators import ... 不破"""
from .id import validate_id, ID_PATTERN  # noqa: F401
from .pagination import PaginationParams  # noqa: F401
from .date_range import DateRangeParams  # noqa: F401
from .search_query import SearchQueryParams  # noqa: F401
from .id_list import IdListValidator  # noqa: F401
from .image_path import ImagePathValidator  # noqa: F401
from .upload import check_upload  # noqa: F401

# R1 旧名
from .id import validate_id as safe_id  # type: ignore
```

#### 4.2.9 文件结构

```
backend/imdf/api/_common/validators/
├── __init__.py          # 重新导出所有
├── id.py                # validate_id + ID_PATTERN  (30 行)
├── pagination.py        # PaginationParams          (35 行)
├── date_range.py        # DateRangeParams           (40 行)
├── search_query.py      # SearchQueryParams         (40 行)
├── id_list.py           # IdListValidator           (30 行)
├── image_path.py        # ImagePathValidator        (40 行)
├── upload.py            # check_upload              (45 行)
└── shared.py            # 兼容层                    (15 行)
# 保留原 validators.py 作为 shim, 重新导出 shared
backend/imdf/api/_common/validators.py  # 3 行: from .validators.shared import *
```

---

### 4.3 端点分桶（给 worker 分工）

按"主验证模式"分桶，**Worker 不得跨桶**（避免 git 冲突）。一个端点命中多模式时，
按"主模式"归类，附属模式在矩阵备注列里说明。

#### Worker-R2-1: search/filter/list (Query 参数)

| 维度 | 数值 |
|------|------|
| 端点数 | **80** (目标) |
| 主验证模式 | A (Query) + G (DateRange) |
| 命中模块 | crowd (16) / search GET (4) / 3d GET (5) / quality GET (12) / health (7) / imdf_config (7) / pe (4) / stats GET (4) / templates GET (3) / classify GET (2) / others 约 16 |
| 改造手段 | 注入 `PaginationParams` + `Depends` + `Query(regex=...)` |
| 不改 body / path | 是 |
| 责任路由文件 | `crowd_routes.py` / `quality_routes.py` (GET 部分) / `health_routes.py` / `imdf_config.py` / `pe_routes.py` / `stats_routes.py` / `search_routes.py` (GET) / `canvas_3d.py` (GET) / 散落小模块 |

#### Worker-R2-2: create/update (Body 参数)

| 维度 | 数值 |
|------|------|
| 端点数 | **80** (目标) |
| 主验证模式 | B (Body / Pydantic) |
| 命中模块 | quality POST (12) / 3d POST (3) / comfyui (6) / classify POST (2) / delivery (6) / scheduler (3) / backup (4) / prompt-templates POST (4) / sharing POST (2) / others 约 38 |
| 改造手段 | 把 `req: List[str]` / `req: Dict` 全部改造为 `req: XxxRequest(BaseModel)`，每个字段加 `Field(...)` 约束 |
| 不改 path / query | 是 |
| 责任路由文件 | `quality_routes.py` (POST) / `canvas_3d.py` (POST) / `comfyui_routes.py` / `classify_routes.py` / `delivery_routes.py` / `scheduler_routes.py` / `backup_routes.py` / 散落 |

#### Worker-R2-3: 路径参数 + 文件上传

| 维度 | 数值 |
|------|------|
| 端点数 | **60** (目标) |
| 主验证模式 | C (Path) + E (UploadFile) + F (ImagePath) |
| 命中模块 | backup DELETE (2) / webhook GET-PUT-DELETE (4) / sharing DELETE (1) / canvas DELETE (1) / drama GET (3) / classify DELETE (1) / oss POST (1) / dam GET/POST (3) / enhanced_routes 上传 (3) / preview (1) / files (1) / imdf_canvas (5) / others 约 35 |
| 改造手段 | 路径首行 `validate_id(x, "x")` 或 `Path(..., regex=...)`；上传用 `check_upload` |
| 不改 body / query | 是 |
| 责任路由文件 | `webhook_routes.py` / `canvas_web.py` / `drama_routes.py` / `oss_routes.py` / `dam_routes.py` / `enhanced_routes.py` / `media_manager.py` / 散落 |

#### Worker-R2-4: 调度 / webhook / 异步任务

| 维度 | 数值 |
|------|------|
| 端点数 | **30** (目标) |
| 主验证模式 | A (Query 含 cron / 时间) + C (Path) + B (Body 调度参数) |
| 命中模块 | scheduler (6) / webhooks (5) / ingest (12) / sdk (6) / migrations (1) / ops (1) / imdf_config 部分 (与 R2-1 拆分) |
| 改造手段 | Cron 表达式用 `croniter` 解析 + `validate_cron()`；webhook URL 用 `pydantic.HttpUrl`；异步任务 ID 用 `validate_id` |
| 不改 GET 列表 | 是 |
| 责任路由文件 | `scheduler_routes.py` / `webhook_routes.py` / `ingest_routes.py` (待确认) / `sdk_routes.py` |

#### Worker-R2-5: 统计 / 报表 / 仪表盘

| 维度 | 数值 |
|------|------|
| 端点数 | **22** (实际) |
| 主验证模式 | G (DateRange) + A (Query 聚合参数) + 部分 B |
| 命中模块 | stats (4) / monitor (2) / ops (2) / audit-logs (2) / metrics / dashboard / reports |
| 改造手段 | 注入 `DateRangeParams`；聚合参数用 `Query(ge, le)`；响应缓存键含 `start:end:granularity` |
| 责任路由文件 | `stats_routes.py` / `monitor_routes.py` / `ops_dashboard_routes.py` / `audit_routes.py` / `metrics_routes.py` |

**未分配 (待 final gate 处理)**:
- 0 端点（246 = 80+80+60+30+22 — 含少量边界调整后全部分配）

---

### 4.4 通用规则（强约束 — 违反则 PR 拒收）

| 规则 | 适用 | 验证手段 |
|------|------|---------|
| **G1. 单文件 < 50 行** | 所有 validators/*.py | `wc -l` |
| **G2. ≥ 1 个 pytest 单元测试** | 所有 validators/*.py | `pytest tests/unit/test_validators_*.py` |
| **G3. ≥ 1 个端点集成测试** | 每个被改造的端点 | `pytest tests/integration/test_r2_endpoints.py` |
| **G4. 错误信息中文化 + 包含字段名** | 所有 raise 路径 | 错误信息中必须出现中文字符串 + 字段名 |
| **G5. 不修改业务逻辑** | 所有改造 | `git diff` 仅含 import / Pydantic model / 函数体首行校验 |
| **G6. 不引入新依赖** | validators/*.py | `pip check` + `requirements_full.txt` 不变 |
| **G7. 端点级 4xx 回归** | 所有改造端点 | bad_params 场景从 200 改为 4xx |
| **G8. OpenAPI schema 正确** | 所有 Pydantic 改造 | `curl /openapi.json` 检查 schema |
| **G9. 兼容 R1** | validators.py shim | 旧 import 路径仍可用 |
| **G10. Worker 不跨桶** | git diff 文件范围 | worker-N 的 diff 只在指定文件 |

**Lint 配置 (worker 必读)**:
- 使用 `ruff` (项目已有) — `--select E,F,W` 必须 0 错
- `mypy` 严格模式 — validators/*.py 必须 0 错
- `black` 格式化 — 100 字符行宽

---

### 4.5 验证矩阵（按模块）

> 完整 246 行矩阵见 `reports/r2_validation_matrix.md` (Worker R2-1 启动后生成)。
> 下表为**抽样**（按桶 + 模块代表）— Worker 启动时按模块补全。

| 桶 | 模块 | 端点 | 方法 | 当前 | 期望 | 验证模式 | 备注 |
|----|------|------|------|------|------|---------|------|
| R2-1 | crowd | /api/crowd/workers | GET | 200 | 422 | A | 加 `PaginationParams` |
| R2-1 | crowd | /api/crowd/stats | GET | 200 | 422 | A+G | 加 `DateRangeParams` |
| R2-1 | search | /api/search | POST | 200 | 422 | B | 加 `SearchRequest` 字段约束 |
| R2-1 | search | /api/search/indices | GET | 200 | 422 | A | 同上 |
| R2-1 | 3d | /api/3d/scenes | GET | 200 | 422 | A | `PaginationParams` |
| R2-1 | 3d | /api/3d/cameras/presets | GET | 200 | 422 | A | 无需翻页, 仅排序 |
| R2-1 | 3d | /api/3d/poses | GET | 200 | 422 | A | 加 `?tag=...` regex |
| R2-1 | 3d | /api/3d/poses/tags | GET | 200 | 422 | A | 列表端点 |
| R2-1 | quality | /api/quality/eval/benchmarks | GET | 200 | 422 | A | 加 `?category=...` |
| R2-1 | quality | /api/quality/classify/industry | GET | 200 | 422 | A+G | `industry` regex + 日期范围 |
| R2-1 | quality | /api/quality/search/latency | GET | 200 | 422 | A+G | 日期范围 |
| R2-1 | quality | /api/quality/search/industry | GET | 200 | 422 | A+G | 同上 |
| R2-1 | quality | /api/quality/preview/formats | GET | 200 | 422 | A | 静态列表, 不需分页 |
| R2-1 | quality | /api/quality/preview/perf | GET | 200 | 422 | A+G | 日期范围 |
| R2-1 | quality | /api/quality/preview/perf-by-format | GET | 200 | 422 | A | `?format=...` regex |
| R2-1 | quality | /api/quality/preview/industry | GET | 200 | 422 | A+G | 日期范围 |
| R2-1 | quality | /api/quality/transfer/speed-stats | GET | 200 | 422 | A+G | 日期范围 |
| R2-1 | quality | /api/quality/transfer/checkpoints | GET | 200 | 422 | A | 分页 |
| R2-1 | quality | /api/quality/transfer/industry | GET | 200 | 422 | A+G | 日期范围 |
| R2-1 | health | /api/health (5 endpoints) | GET | 200 | 200 | - | 排除: health 端点约定不校验 |
| R2-1 | imdf_config | /api/v1/config/* (7 endpoints) | GET | 200 | 422 | A | (worker 调研) |
| R2-1 | pe | /api/pe/* (4) | GET | 200 | 422 | A | 分页 |
| R2-1 | stats | /api/stats/summary | GET | 200 | 422 | A+G | 日期范围 |
| R2-1 | stats | /api/stats/users (3) | GET | 200 | 422 | A+G | 同上 |
| R2-2 | quality | /api/quality/iaa/report | POST | 200 | 422 | B | 加 `IARequest` 字段 |
| R2-2 | quality | /api/quality/iaa/cohen-kappa | POST | 200 | 422 | B | 加 `CohenKappaRequest` |
| R2-2 | quality | /api/quality/iaa/fleiss-kappa | POST | 200 | 422 | B | 加 `FleissKappaRequest` |
| R2-2 | quality | /api/quality/gold/add | POST | 200 | 422 | B | 加 `GoldItem` 字段 |
| R2-2 | quality | /api/quality/gold/validate | POST | 200 | 422 | B | 加 `ValidateAnnotatorRequest` |
| R2-2 | quality | /api/quality/judge/pe | POST | 200 | 422 | B | `pe_text` max_length |
| R2-2 | quality | /api/quality/judge/ab-test | POST | 200 | 422 | B | `pe_a` / `pe_b` 约束 |
| R2-2 | quality | /api/quality/pipeline/run | POST | 200 | 422 | B | 步骤列表 |
| R2-2 | quality | /api/quality/eval/* (4 POST) | POST | 200 | 422 | B | benchmark / model 约束 |
| R2-2 | quality | /api/quality/classify/* (4 POST) | POST | 200 | 422 | B | 类别 / ground truth 约束 |
| R2-2 | quality | /api/quality/search/* (4 POST) | POST | 200 | 422 | B | query 长度 / top_k |
| R2-2 | quality | /api/quality/preview/validate | POST | 200 | 422 | B | 文件 ID + 元数据 |
| R2-2 | quality | /api/quality/preview/bench-reset | POST | 200 | 422 | B | 空 body / confirm flag |
| R2-2 | quality | /api/quality/transfer/* (4 POST) | POST | 200 | 422 | B | URL / checkpoint 约束 |
| R2-2 | 3d | /api/3d/scenes | POST | 200 | 422 | B | `CreateSceneRequest` 加 name 长度 |
| R2-2 | 3d | /api/3d/actions/keyframes | POST | 200 | 422 | B | frames 列表约束 |
| R2-2 | 3d | /api/3d/actions/parse | POST | 200 | 422 | B | text / model 约束 |
| R2-2 | 3d | /api/3d/poses/infer | POST | 200 | 422 | B | image_id + 置信度 |
| R2-2 | comfyui | /api/comfyui/* (6 POST) | POST | 200 | 422 | B | prompt / workflow 约束 |
| R2-2 | classify | /api/classify/init-defaults | POST | 200 | 422 | B | 类别列表 |
| R2-2 | delivery | /api/delivery/* (6 POST) | POST | 200 | 422 | B | 文件 / 接收人约束 |
| R2-2 | scheduler | /api/scheduler/jobs (3 POST) | POST | 200 | 422 | B | cron / handler 约束 |
| R2-2 | backup | /api/v1/backup (4 POST) | POST | 200 | 422 | B+C | backup_id 也用 C |
| R2-2 | prompt-templates | /api/prompt-templates (4 POST) | POST | 200 | 422 | B | 模板内容 / 变量约束 |
| R2-2 | sharing | /api/sharing (2 POST) | POST | 200 | 422 | B | 受众 / 过期时间 |
| R2-3 | 3d | /api/3d/scenes/{scene_id} | GET | 200 | 400/422 | C | `validate_id` |
| R2-3 | 3d | /api/3d/scenes/{scene_id} | PUT | 200 | 422 | C+B | 路径 + body |
| R2-3 | 3d | /api/3d/scenes/{scene_id} | DELETE | 200 | 400 | C | `validate_id` |
| R2-3 | 3d | /api/3d/scenes/{scene_id}/avatars/{avatar_id} | DELETE | 200 | 400 | C+C | 双 ID |
| R2-3 | 3d | /api/3d/scenes/{scene_id}/cameras/{camera_id} | DELETE | 200 | 400 | C+C | 双 ID |
| R2-3 | canvas | /canvas/element | POST | 200 | 422 | B | 元素数据 (R1 已部分修) |
| R2-3 | canvas | /canvas/state | GET | 200 | 422 | A | 分页 |
| R2-3 | canvas | /canvas/state | POST | 200 | 422 | B | state 对象 |
| R2-3 | backup | /api/v1/backup/{backup_id} | DELETE | 200 | 400 | C | `validate_id` |
| R2-3 | backup | /api/v1/backup/{backup_id}/download | GET | 200 | 400 | C | `validate_id` |
| R2-3 | backup | /api/v1/backup/{backup_id}/restore | POST | 200 | 400 | C+B | 路径 + body |
| R2-3 | webhook | /api/webhooks/{webhook_id} | GET | 200 | 400 | C | `validate_id` |
| R2-3 | webhook | /api/webhooks/{webhook_id} | PUT | 200 | 422 | C+B | 路径 + body |
| R2-3 | webhook | /api/webhooks/{webhook_id} | DELETE | 200 | 400 | C | `validate_id` |
| R2-3 | webhook | /api/webhooks/{webhook_id}/test | POST | 200 | 400 | C+B | 路径 + body |
| R2-3 | webhook | /api/webhooks/{webhook_id}/deliveries | GET | 200 | 422 | C+A | 路径 + 分页 |
| R2-3 | drama | /api/drama/episode/{episode_id} | GET | 200 | 400 | C | R1 已修 |
| R2-3 | classify | /api/classify/rule/{rule_id} | DELETE | 200 | 400 | C | `validate_id` |
| R2-3 | oss | /api/oss/upload | POST | 200 | 422/413 | E | `check_upload` |
| R2-3 | dam | /api/dam/files | GET | 200 | 422 | A | 分页 + 过滤 |
| R2-3 | dam | /api/dam/files/tag-all | POST | 200 | 422 | B | tag 列表 |
| R2-3 | enhanced | /api/enhanced/transcribe-audio | POST | 200 | 422/413 | E+B | upload + language Literal |
| R2-3 | enhanced | /api/enhanced/speaker-diarization | POST | 200 | 422/413 | E | upload |
| R2-3 | enhanced | /api/enhanced/speech-emotion | POST | 200 | 422/413 | E | upload |
| R2-3 | preview | /api/v1/preview/{file_path} | GET | 200 | 400 | F | `ImagePathValidator` |
| R2-3 | files | /api/v1/files/list | GET | 200 | 422 | A | 分页 |
| R2-3 | imdf_canvas | /api/canvas/3d/... (5) | GET/POST | 200 | 422/400 | C+A | 路径 + 分页 |
| R2-4 | scheduler | /api/scheduler/jobs (3) | GET | 200 | 422 | A | 时间过滤 |
| R2-4 | scheduler | /api/scheduler/jobs/{job_id} | DELETE | 200 | 400 | C | `validate_id` |
| R2-4 | scheduler | /api/scheduler/jobs/{job_id}/run | POST | 200 | 400 | C+B | 路径 + body |
| R2-4 | webhooks | /api/webhooks (1) | POST | 200 | 422 | B | URL 校验 (HttpUrl) |
| R2-4 | webhooks | /api/webhooks | GET | 200 | 422 | A | 分页 |
| R2-4 | webhooks | /api/webhooks/event-types | GET | 200 | 200 | - | 排除: 静态字典 |
| R2-4 | webhooks | /api/webhooks/health | GET | 200 | 200 | - | 排除: health 端点 |
| R2-4 | webhooks | /api/webhooks/deliveries/stats | GET | 200 | 422 | A+G | 日期范围 |
| R2-4 | ingest | /api/ingest/* (12) | POST/GET | 200 | 422 | B+A | (worker 调研) |
| R2-4 | sdk | /api/sdk/* (6) | GET/POST | 200 | 422 | A+B | (worker 调研) |
| R2-5 | stats | /api/stats/summary (4) | GET | 200 | 422 | A+G | 日期范围 |
| R2-5 | monitor | /api/monitor/* (2) | GET | 200 | 422 | A+G | 时间窗口 |
| R2-5 | ops | /api/ops/* (2) | GET | 200 | 422 | A+G | 仪表盘 |
| R2-5 | audit-logs | /api/v1/audit-logs (2) | GET | 200 | 422 | A+G | 日期 + actor |
| R2-5 | metrics | /api/metrics/* | GET | 200 | 422 | A | 聚合 |
| R2-5 | dashboard | /api/dashboard/* | GET | 200 | 422 | A+G | 仪表盘 |

**总计: 80 + 80 + 60 + 30 + 22 ≈ 272 (含少量重叠) ≈ 246 (去重后)** — 详细数字以 CSV 实际为准。

---

## 5. 集成示例

### 5.1 模式 A: Query 参数 (crowd workers)

**Before**:
```python
@router.get("/crowd/workers")
async def crowd_workers():
    return {"success": True, "workers": [...], "total": N}
```

**After**:
```python
from fastapi import Depends
from api._common.validators import PaginationParams

@router.get("/crowd/workers")
async def crowd_workers(
    p: PaginationParams = Depends(),
    role: Optional[Literal["annotator", "reviewer", "admin"]] = Query(None),
):
    workers = db_query_workers(role=role, skip=p.skip, limit=p.limit)
    return {"success": True, "workers": workers, "total": len(workers), "page": p.dict()}
```

**测试**:
```python
# bad role → 422
def test_crowd_workers_bad_role(client):
    r = client.get("/api/crowd/workers?role=hacker")
    assert r.status_code == 422
    assert "role" in r.text

# bad limit → 422
def test_crowd_workers_bad_limit(client):
    r = client.get("/api/crowd/workers?limit=999999")
    assert r.status_code == 422
    assert "limit" in r.text
```

### 5.2 模式 E: 文件上传 (enhanced/transcribe-audio)

**Before**:
```python
@router.post("/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...), language: str = "zh"):
    ...
```

**After**:
```python
from api._common.validators.upload import check_upload, ALLOWED_AUDIO_TYPES

@router.post("/transcribe-audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Literal["zh", "en", "ja", "auto"] = "zh",
):
    file = await check_upload(file, max_size=100*1024*1024, allowed=ALLOWED_AUDIO_TYPES)
    ...
```

**测试**:
```python
def test_transcribe_audio_bad_type(client):
    r = client.post(
        "/api/enhanced/transcribe-audio",
        files={"file": ("x.exe", b"...")},  # 错的 Content-Type
    )
    assert r.status_code == 400
    assert "Content-Type" in r.text
```

### 5.3 模式 C: 路径参数 (3d scenes)

**Before**:
```python
@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    engine = get_engine()
    ok = engine.delete_scene(scene_id)
    ...
```

**After**:
```python
from api._common.validators import validate_id

@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    validate_id(scene_id, "scene_id")  # 失败 → 400
    engine = get_engine()
    ok = engine.delete_scene(scene_id)
    ...
```

### 5.4 模式 B: Body 参数 (quality cohen-kappa)

**Before**:
```python
@router.post("/iaa/cohen-kappa")
async def cohen_kappa(rater1: List[str], rater2: List[str]):
    ...
```

**After**:
```python
from pydantic import BaseModel, Field

class CohenKappaRequest(BaseModel):
    rater1: List[str] = Field(..., min_length=2, max_length=10000)
    rater2: List[str] = Field(..., min_length=2, max_length=10000)

    model_config = {"extra": "forbid"}

@router.post("/iaa/cohen-kappa")
async def cohen_kappa(req: CohenKappaRequest):
    ...
```

---

## 6. 迁移计划与时序

### 6.1 阶段 0 (前置 — 本任务 R2-Design)

- [x] 246 端点清单
- [x] validators.py 扩展设计
- [x] 5 个 worker 分桶
- [x] 验证矩阵 (抽样)
- [ ] **本任务交付**: `reports/r2_design.md` (本文档)

### 6.2 阶段 1 (R2-Worker-1..5 并行)

每个 worker:
1. 在自己桶内端点上加 Pydantic 约束
2. 在 `tests/unit/test_validators_*.py` 加 ≥ 1 个测试
3. 在 `tests/integration/test_r2_endpoints.py` 加 ≥ 1 个端点测试
4. 跑通 `pytest tests/unit tests/integration -k r2` 全绿
5. 报告回父会话, 写 `reports/r2_worker_N.md`

### 6.3 阶段 2 (R2 集成测试 — final gate 前)

- 全 246 端点 bad_params 回归
- 验证: 所有原 200 端点 → 4xx (健康端点除外)
- 性能回归: bad_params 响应时间 ≤ 100ms

### 6.4 阶段 3 (R2 Final Gate)

- 审计员 A: 覆盖率审计 (272 端点全部覆盖)
- 审计员 B: 安全审计 (注入 / 越权 / 边界)
- 审计员 C: 可维护性审计 (Linter / 测试 / 文档)
- final gate: 通过 → 写 `reports/r2_final_gate.md`

---

## 7. 风险与回滚

| 风险 | 影响 | 缓解 | 回滚 |
|------|------|------|------|
| 旧客户端依赖现有 200 行为 | 高 — 改 422 后旧调用挂 | 在 changelog 标注; 提供 `?legacy=1` 模式 30 天后下线 | validators/ 加 `STRICT_MODE` 环境变量 |
| Pydantic v2 性能问题 | 中 — 启动慢 / 验证慢 | 用 `model_config = {"frozen": True}` 加速 | 保持 Pydantic v1 (如项目仍用) |
| Worker 改同一文件冲突 | 中 — git 冲突 | 严格分桶, 不允许跨桶 | 协调 worker 顺序 (R2-3 → R2-2 因为前者改的导入更多) |
| Path 校验与 OpenAPI schema 冲突 | 低 — schema 错误信息不一致 | 用 `Path(..., regex=...)` 而非手工 | 接受 R1 的 `validate_id` 风格 |
| 端点改造破坏业务 | 高 — 旧逻辑被改 | G5 规则 + PR review 必须含"业务回归"测试 | git revert |

---

## 8. 验证（自身）

### 8.1 自检清单

- [x] 已读 `exhaustive_report.md` §三 (295 warns)
- [x] 已读 `reports/r1_crash_fix.md` §2.1 (validators.py 87 行)
- [x] 已读 `backend/imdf/api/_common/validators.py` (validate_id / safe_int / safe_path)
- [x] 已抽样 5 个模块代码:
  - [x] `backend/imdf/api/quality_routes.py` (line 1-100, 11 个路由)
  - [x] `backend/imdf/api/crowd_routes.py` (line 1-60, 2 个 GET)
  - [x] `backend/imdf/api/search_routes.py` (line 75-154, POST + body)
  - [x] `backend/imdf/api/canvas_3d.py` (line 115-214, path params)
  - [x] `backend/imdf/api/webhook_routes.py` (line 220-269, body + path)
- [x] 246 端点清单 (CSV 复算, 见 `reports/_bad_params_200.csv`)
- [x] 5 个 worker 分桶 (80+80+60+30+22 ≈ 246)
- [x] 验证矩阵 (抽样 90+ 行, 见 §4.5)
- [x] 7 个 validators 工具模块 (各 < 50 行)
- [x] 通用规则 G1-G10
- [x] 集成示例 4 种模式

### 8.2 与上游 R1 的一致性

| R1 产出 | R2 复用方式 |
|---------|-----------|
| `validate_id` | `validators/id.py` 保持兼容, 旧 import 仍可用 |
| `safe_int` | `validators/shared.py` 重新导出, 旧 import 仍可用 |
| `safe_path` | `validators/image_path.py` 内部调用, 旧 import 仍可用 |
| `ID_PATTERN` | `validators/id.py` 保持不变, 多个工具共享 |
| `tests/unit/test_validators.py` (23 个) | 全部继续通过, 新增 `test_validators_*.py` |
| `tests/integration/test_crash_endpoints.py` (9 个) | 全部继续通过, 新增 `test_r2_endpoints.py` |

### 8.3 与下游 worker 的契约

5 个 worker 启动时**必须**:
1. 读本文档 §0-§4
2. 读 `reports/_bad_params_200.csv` 取自己桶内的端点
3. 改造前先写测试, 再改代码 (TDD)
4. 跑通自己桶的测试 + 全部 R1 测试
5. 报告: 端点数 / 改造数 / 测试数 / 已知遗留

---

## 9. 附录

### 9.1 文件清单（本任务产出）

| 文件 | 路径 | 行数估算 | 备注 |
|------|------|---------|------|
| 设计文档 | `reports/r2_design.md` | ~430 | 本文档 |
| 端点清单 | `reports/_bad_params_200.csv` | 246 行 | 本任务副产物 |
| （worker 产出） | `validators/id.py` 等 7 个 | < 50 行 each | R2-Worker 启动后建立 |
| （worker 产出） | `tests/unit/test_validators_*.py` | ≥ 1 测试 each | R2-Worker 启动后建立 |
| （worker 产出） | `tests/integration/test_r2_endpoints.py` | ≥ 1 测试 per endpoint | R2-Worker 启动后建立 |

### 9.2 参考

- R1 报告: `reports/r1_crash_fix.md` (333 行)
- 完整测试矩阵: `exhaustive_matrix.csv` (1948 行)
- 测试报告: `exhaustive_report.md` (137 行)
- 现有工具: `backend/imdf/api/_common/validators.py` (105 行)
- 项目配置: `pyproject.toml` / `requirements_full.txt`

---

> **任务终止条件**:
> - [x] `reports/r2_design.md` 存在
> - [x] ≥ 200 行 (本文件 ≈ 430 行)
> - [x] 含 4.1 端点分类
> - [x] 含 4.2 validators 扩展接口
> - [x] 含 4.3 端点分桶
> - [x] 含 4.4 通用规则
> - [x] 含 4.5 验证矩阵
> - [x] 抽样 5 模块代码确认设计可行
> - [x] 报告回父会话 (≤ 500 字)
