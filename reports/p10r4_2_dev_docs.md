# P10R4-2: 开发文档 (AGENTS.md + 贡献指南 + 代码规范 + 测试规范 + 提交流程)

> **Date**: 2026-06-26 13:55 (Asia/Shanghai)
> **Author**: coder (P10R4-2 worker)
> **Note**: 项目原本没有 AGENTS.md (P10R4-2 补建), 本文档作为权威开发指南

---

## 1. 项目级 AGENTS.md (建议在项目根创建)

```markdown
# AGENTS.md — Nanobot Factory 开发指南

> For OpenCode / Codex / Cursor / Aider / Devin / Gemini CLI
> Last updated: 2026-06-26 (P10R4-2)

## 1. 项目一句话定位
商业级全模态数据生成管理平台 (智影 / ZhiYing), 12 微服务 + 194+ 算子 + 15+ Agent, 部署形态为裸机 systemd.

## 2. 技术栈 (硬性约束)
- 后端: Python 3.11 + FastAPI 0.110+ + uvicorn 0.27+
- 数据库: PostgreSQL 15 + pgvector (主从), Redis 7 (缓存 + broker)
- 存储: MinIO (S3-compatible OSS)
- 异步: Celery 5 (5 queues) + aio_pika
- LLM: OpenAI / Anthropic / DeepSeek / 本地模型 (multi-provider via LiteLLM)
- 追踪: OpenTelemetry + Jaeger
- 日志: structlog + Sentry + Loki
- 前端: Vue 3 (Naive UI) + React 18 (Electron) + Vite 5
- 监控: Prometheus + Grafana + Alertmanager
- 测试: pytest 8 + httpx + locust
- 部署: systemd (裸机) — **NOT Docker / NOT K8s**

## 3. 项目结构 (核心)
```
nanobot-factory/
├── backend/
│   ├── services/         # 12 微服务 (gateway + 11 业务)
│   ├── gateway/          # API gateway (:8000)
│   ├── auth/             # JWT / RBAC
│   ├── billing/          # 订阅 + 支付 (Stripe/Alipay/WeChat)
│   ├── contracts/        # 合同
│   ├── invoices/         # 发票
│   ├── crm/              # CRM
│   ├── tickets/          # 工单
│   ├── common/           # 共享库 (auth/db/logging/config/health/metrics)
│   ├── agent/            # BaseAgent + PluginRegistry + MemoryPalace + Hindsight + MCP
│   ├── nodes/            # DAG 节点 (7 文件)
│   ├── functions/        # LLM 能力 (6 文件)
│   ├── capabilities/     # 能力 (2 文件)
│   ├── skills/           # 内置技能 (10) + Obsidian (2) + runtime (21)
│   ├── imdf/             # 核心 imdf 模块 (api / core / data / agents / multimodal)
│   └── tests/            # 测试
├── frontend/             # Vue 2 (旧)
├── frontend-v2/          # Vue 3 + Naive UI (新)
├── deploy/
│   ├── bare_metal/       # systemd + scripts + configs
│   ├── helm/             # DEPRECATED
│   └── k8s/              # DEPRECATED
├── docs/                 # 8 份文档 (api / architecture / runbook / sla / security / ...)
├── monitoring/           # Prometheus / Grafana / Loki / Jaeger / Alertmanager
└── reports/              # 历次 P 报告
```

## 4. 开发循环
1. 启动本地 venv: `python -m venv venv && venv\Scripts\Activate.ps1 && pip install -r backend/requirements.txt`
2. 启动 gateway: `uvicorn backend.gateway.main:app --reload --port 8000`
3. 启动依赖 svc (按需): `uvicorn backend.services.<svc>.main:app --reload --port 800X`
4. 跑测试: `pytest backend/<module>/tests -v`
5. 提 PR: 见 §8

## 5. 代码规范 (强制)
- PEP 8 + Black (line-length=100) + isort + flake8 + mypy --strict
- 类型注解: 100% 覆盖 (mypy --strict 必须 PASS)
- Docstring: Google style (重要函数必须)
- 错误处理: 自定义异常 + 统一中间件 (backend/common/error_handler.py)
- 日志: structlog (NOT print) + bind contextvars (request_id / tenant_id)
- 数据库: SQLAlchemy 2.0 async + Alembic (任何 schema 变更必须 alembic revision)
- API: FastAPI + Pydantic v2 (Response model 必须声明)
- 测试: pytest + httpx AsyncClient + 覆盖率 > 80%

## 6. 提交前 checklist (CI 强制)
- [ ] `pytest backend/<module>/tests -v` 全 PASS
- [ ] `mypy backend/<module>` 0 errors
- [ ] `black --check backend/<module>` PASS
- [ ] `flake8 backend/<module>` 0 critical
- [ ] `bandit -r backend/<module>` 0 high
- [ ] 新代码含 pytest (覆盖率 +5%)
- [ ] 无 print / 无 pdb / 无 commit comment
- [ ] 文档同步更新 (api.md / runbook.md / CHANGELOG.md)
- [ ] 数据库变更含 alembic revision (upgrade + downgrade 测试)

## 7. 禁止 (CI 拒绝)
- ❌ 修改 deploy/k8s/ 或 deploy/helm/ (DEPRECATED)
- ❌ 硬编码 secret / API key / password
- ❌ 引入新 framework (Django / Flask / 其他 ORM)
- ❌ 改 backend/common/ 公共 API 不通知
- ❌ 修改生产 .env 不走 PR
- ❌ 引入新 SDK 不走 SECURITY review

## 8. PR 流程
1. fork → feature branch (`feat/<short-name>`)
2. 写代码 + 测试 + 文档
3. CI 必过 (test + lint + type + security)
4. 2 reviewer approval (1 maintainer + 1 peer)
5. squash merge
6. 自动 deploy 到 staging
7. 24h 监控无异常 → cherry-pick 到 main

## 9. 紧急联系
- 平台 on-call: 见 wiki/Oncall-Roster
- 安全事件: security@nanobot-factory.example.com (24/7)
- 生产事故: PagerDuty `imdf-oncall`
```

---

## 2. 贡献指南 (CONTRIBUTING.md 草案)

### 2.1 我可以贡献什么?

| 类型 | 难度 | 适合 |
|------|------|------|
| Bug fix | 🟢 易 | 新人 |
| 文档改进 (typo / 翻译) | 🟢 易 | 任何人 |
| 测试覆盖率提升 | 🟡 中 | 熟悉代码 |
| 新 endpoint | 🟡 中 | 熟悉 FastAPI |
| 新算子 (DAG node) | 🟡 中 | 熟悉数据流 |
| 新 Agent 类型 | 🟠 难 | 熟悉 agent framework |
| 新微服务 | 🔴 难 | 核心团队 |
| 性能优化 | 🔴 难 | 资深 |
| 安全修复 | 🔴 难 | 安全团队 |

### 2.2 第一次贡献流程

```bash
# 1) Fork (GitHub)
gh repo fork MiniMax-AI/nanobot-factory --clone

# 2) Clone + setup
git clone https://github.com/<you>/nanobot-factory.git
cd nanobot-factory
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt  # 含 pytest/black/mypy

# 3) 创建 branch
git checkout -b fix/typo-in-readme

# 4) 编辑 + 测试
$EDITOR README.md
pytest backend/tests -v  # 跑全部测试 (应该 PASS)

# 5) Commit (conventional commits)
git add README.md
git commit -m "docs(readme): fix typo in 'bare-metal' section"

# 6) Push + PR
git push origin fix/typo-in-readme
gh pr create --title "docs(readme): fix typo" --body "..."
```

### 2.3 Commit message 规范 (Conventional Commits)

```
<type>(<scope>): <subject>

<body>

<footer>

# type:
feat:     新功能
fix:      bug 修复
docs:     仅文档
style:    格式 (无逻辑变更)
refactor: 重构 (无功能变更)
perf:     性能优化
test:     测试
chore:    杂项 (依赖 / 配置)
ci:       CI 变更
revert:   回滚

# scope:
gateway / user / asset / annotation / cleaning / scoring / dataset /
evaluation / agent / workflow / notification / search / collection /
billing / contracts / invoices / crm / tickets / common / agent / deploy

# 示例:
feat(asset): add bulk upload endpoint
fix(gateway): handle 502 from upstream correctly
docs(api): add example for /api/v1/auth/token
```

---

## 3. 代码规范详解

### 3.1 Python (PEP 8 + Black + isort)

```toml
# pyproject.toml (建议在项目根创建)
[tool.black]
line-length = 100
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 100
known_first_party = ["backend", "common"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true  # 暂开, 后续逐步收紧

[tool.pytest.ini_options]
testpaths = ["backend"]
asyncio_mode = "auto"
addopts = "-v --tb=short --strict-markers"
markers = [
    "integration: integration tests (require live DB)",
    "e2e: end-to-end tests (slow)",
    "slow: slow tests (>5s)",
]
```

### 3.2 FastAPI 模式

```python
# 好的例子 (backend/services/asset_service/routes.py)
from typing import Annotated
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from pydantic import BaseModel, Field

from common.auth import get_current_user, UserContext
from common.error_handler import APIError
from .schemas import AssetResponse
from .service import AssetService

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


class UploadResponse(BaseModel):
    id: str
    sha256: str
    size_bytes: int
    url: str


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: Annotated[UploadFile, File(description="Asset file (≤1GB)")],
    kind: Annotated[str, Form()] = "image",
    user: Annotated[UserContext, Depends(get_current_user)] = ...,
) -> UploadResponse:
    """上传资产文件.

    - **file**: multipart/form-data file (max 1GB)
    - **kind**: image | video | audio | text
    - **return**: AssetResponse with id + signed URL
    """
    if file.size and file.size > 1_000_000_000:
        raise APIError("FILE_TOO_LARGE", "max 1GB", status_code=413)

    svc = AssetService(user.tenant_id)
    asset = await svc.upload(file, kind=kind)
    return UploadResponse(
        id=asset.id, sha256=asset.sha256, size_bytes=asset.size_bytes,
        url=f"/api/v1/assets/{asset.id}/raw",
    )
```

### 3.3 数据库 (SQLAlchemy 2.0 async)

```python
# backend/common/db.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,  # postgresql+asyncpg://...
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### 3.4 日志 (structlog + Sentry)

```python
# backend/common/logging.py
import structlog
import sentry_sdk

def configure_logging(service_name: str, env: str = "production"):
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=env,
        traces_sample_rate=0.1,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger(service_name)
    logger.info("logging.configured", env=env)


# Usage:
log = structlog.get_logger(__name__)
log.info("asset.uploaded", asset_id=asset.id, sha256=sha, size=size, tenant_id=user.tenant_id)
```

### 3.5 测试 (pytest + httpx)

```python
# backend/services/asset_service/tests/test_upload.py
import pytest
from httpx import AsyncClient
from backend.gateway.main import app
from backend.common.auth import create_test_token


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    token = create_test_token(user_id="u_test", tenant_id="t_test")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_upload_image_success(client, auth_headers):
    files = {"file": ("test.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "image/png")}
    data = {"kind": "image"}

    r = await client.post(
        "/api/v1/assets/upload",
        files=files, data=data, headers=auth_headers,
    )

    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("a_")
    assert body["sha256"]
    assert body["size_bytes"] > 0
    assert body["url"].endswith("/raw")


@pytest.mark.asyncio
async def test_upload_unauthorized(client):
    r = await client.post("/api/v1/assets/upload", files={"file": ("x", b"x", "text/plain")})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_upload_too_large(client, auth_headers):
    big = b"\x00" * (1024 * 1024 * 1025)  # 1GB + 1KB
    r = await client.post(
        "/api/v1/assets/upload",
        files={"file": ("big.bin", big, "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 413
```

---

## 4. 测试规范

### 4.1 测试金字塔

```
                /\
               /  \           E2E (locust 1000 concurrent)  ~10 tests
              /────\
             /      \         Integration (TestClient + Test DB)  ~100 tests
            /────────\
           /          \       Unit (function/method)  ~1000 tests
          /────────────\
```

| 层 | 工具 | 覆盖 | 运行时间 |
|----|------|------|---------|
| Unit | pytest + pytest-asyncio | 函数 / 类 / 边界条件 | < 5s |
| Integration | pytest + httpx + TestClient + Test PG | 多模块协同 + DB | 10-30s |
| E2E | pytest + httpx (full stack) | 完整业务流 | 1-5 min |
| Load | locust 1000 concurrent | 性能 / 限流 / SLA | 5 min |

### 4.2 测试命名

```python
# 文件: test_<module>.py
# 函数: test_<func>_<scenario>_<expected>

def test_upload_image_success():
    """正常上传 PNG, 应返回 201 + asset_id."""

def test_upload_unauthorized_no_token():
    """无 token 上传, 应返回 401."""

def test_upload_too_large_413():
    """上传 1GB+ 文件, 应返回 413."""

def test_upload_invalid_kind_422():
    """kind 不在白名单, 应返回 422 Pydantic 校验错误."""
```

### 4.3 Mock 模式

```python
# Mock 外部依赖 (Stripe / LLM / OSS)
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_stripe():
    with patch("stripe.checkout.Session.create") as mock:
        mock.return_value = AsyncMock(
            id="cs_test_xxx",
            url="https://checkout.stripe.com/...",
        )
        yield mock


@pytest.fixture
def mock_openai():
    with patch("openai.AsyncOpenAI") as Mock:
        client = Mock.return_value
        client.chat.completions.create = AsyncMock(return_value={
            "choices": [{"message": {"content": "test response"}}]
        })
        yield client
```

### 4.4 Coverage 目标

| 模块 | 最低 | 目标 |
|------|------|------|
| `backend/services/<svc>/routes.py` | 85% | 95% |
| `backend/services/<svc>/service.py` | 80% | 90% |
| `backend/billing/payments/*.py` (live) | 75% | 90% |
| `backend/common/` | 90% | 100% |
| `backend/agent/` | 70% | 85% |
| **整体** | **80%** | **90%** |

```bash
# 本地 coverage
pytest --cov=backend/services/asset_service --cov-report=html --cov-report=term

# CI coverage (必须 ≥ baseline)
pytest --cov=backend --cov-fail-under=80 --cov-report=xml
```

---

## 5. 数据库迁移 (Alembic)

### 5.1 新建 migration

```bash
# 自动生成 (基于 model diff)
cd backend
venv/bin/alembic -c alembic.ini revision --autogenerate -m "add user preferences"

# 手动生成 (复杂场景)
venv/bin/alembic -c alembic.ini revision -m "add composite index on annotations"
```

### 5.2 编写 migration (upgrade + downgrade 必须测)

```python
# backend/alembic/versions/2026_06_26_1200_add_user_preferences.py
"""add user preferences

Revision ID: abc123def456
Revises: xyz789
Create Date: 2026-06-26 12:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("preferences", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
    )
    op.create_index("ix_user_preferences_tenant_user", "user_preferences", ["tenant_id", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_preferences_tenant_user", table_name="user_preferences")
    op.drop_table("user_preferences")
```

### 5.3 双向验证 (CI 必跑)

```bash
# upgrade
venv/bin/alembic -c backend/alembic.ini upgrade head

# downgrade 回上一个
venv/bin/alembic -c backend/alembic.ini downgrade -1

# 再 upgrade 验证幂等
venv/bin/alembic -c backend/alembic.ini upgrade head
```

---

## 6. CI/CD 流程

### 6.1 CI Pipeline (.github/workflows/ci.yml 草案)

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-22.04
    strategy:
      matrix:
        python: ['3.11']
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        options: --health-cmd "redis-cli ping"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - run: pytest backend/ -v --cov=backend --cov-fail-under=80
      - run: mypy backend/ --strict
      - run: black --check backend/
      - run: isort --check-only backend/
      - run: flake8 backend/
      - run: bandit -r backend/ -ll
      - run: pip-audit

  build:
    needs: test
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t nanobot-factory:${{ github.sha }} .
      - run: docker push nanobot-factory:${{ github.sha }}
```

### 6.2 CD Pipeline (deploy 到 staging)

```yaml
name: CD

on:
  push:
    branches: [main]

jobs:
  deploy-staging:
    runs-on: ubuntu-22.04
    steps:
      - name: SSH to staging + upgrade
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: imdf
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/nanobot-factory
            ./deploy/bare_metal/scripts/upgrade.sh
            ./deploy/bare_metal/scripts/healthcheck.sh
```

---

## 7. Onboarding Checklist (新人入职)

- [ ] 读完 README.md + AGENTS.md (本文件)
- [ ] 阅读 deploy/bare_metal/README.md (部署权威)
- [ ] 阅读 docs/api.md + docs/architecture.md (系统全景)
- [ ] 阅读 docs/runbook.md + docs/sla.md (运维)
- [ ] 阅读 docs/security.md + P10R4-1 报告 (安全)
- [ ] 本地启动 gateway (Windows + Git Bash)
- [ ] 跑通测试: `pytest backend/tests/test_smoke.py -v`
- [ ] 看 Grafana: https://grafana.imdf.example.com (8 dashboard)
- [ ] 加入 oncall 轮值 (PagerDuty)
- [ ] 1 周内完成 1 个 Good First Issue

---

## 8. 决策记录 (ADR 草案)

```markdown
# ADR-001: 部署形态选 systemd 而非 Docker/K8s

## Status: Accepted (2026-06)

## Context
- 12 微服务 + 6 监控 + 3 数据 + 2 async = 23 单元
- 团队 SRE 5 人, K8s 经验 < 1 人/年
- 业务: B2B SaaS, 5-50 客户 / DC, 单客户 1-3 实例
- 性能要求: P95 < 1000ms

## Decision
采用 **裸机 systemd unit** 部署, 不上 K8s.

## Consequences
### 正面
- 简单: 1 个 install.sh + 23 个 unit, 5 min 部署
- 透明: systemctl status 一目了然
- 性能: 无 container overhead (P95 -5~10%)
- 维护成本低: SRE 培训 < 1 周

### 负面
- 横向扩展手动: 加节点需 rsync + 启停
- 自动扩缩容缺失: 需自己写脚本 (over-engineered for current scale)
- 故障转移手动: 主备切换需 5 min (RTO 5min, 当前 SLA 99.9% 容忍)

## 备选
### Docker Compose
- 拒绝原因: 仍需编排, 但失去 systemd 透明性

### Kubernetes
- 拒绝原因: 复杂度超出当前规模, 团队 K8s 经验不足

### Nomad
- 备选但未选: 未来 100+ svc 时可考虑

## 何时复审
- 客户数 > 50 → 重评 K8s
- svc 数 > 30 → 重评 K8s
- SRE 团队 > 10 人 → 重评 K8s
```

---

## 9. 工具链版本锁定

| 工具 | 版本 | 锁定文件 |
|------|------|----------|
| Python | 3.11.6 | `.python-version` |
| FastAPI | 0.110.0 | `backend/requirements.txt` |
| uvicorn | 0.27.2 | `backend/requirements.txt` |
| SQLAlchemy | 2.0.30 | `backend/requirements.txt` |
| Pydantic | 2.6.4 | `backend/requirements.txt` |
| Alembic | 1.13.1 | `backend/requirements.txt` |
| Celery | 5.4.0 | `backend/requirements.txt` |
| pytest | 8.1.1 | `backend/requirements-dev.txt` |
| mypy | 1.10.0 | `backend/requirements-dev.txt` |
| black | 24.4.0 | `backend/requirements-dev.txt` |
| flake8 | 7.0.0 | `backend/requirements-dev.txt` |
| bandit | 1.7.8 | `backend/requirements-dev.txt` |
| locust | 2.25.0 | `backend/requirements-dev.txt` |
| Node.js | 20.12.0 | `.nvmrc` |
| Vue | 3.4.x | `frontend-v2/package.json` |

---

## 10. 改进建议 (P10R4-2 self-review)

| 缺失文档 | 当前 | 建议 | 优先级 |
|---------|------|------|--------|
| AGENTS.md | ❌ 缺失 | **本报告建议补建 (见 §1)** | **P0** |
| CONTRIBUTING.md | ❌ 缺失 | 本报告草案 (§2) | P1 |
| ADR 目录 | ❌ 缺失 | docs/adr/ | P2 |
| .editorconfig | ❌ | 加 | P2 |
| pyproject.toml | ⚠️ 部分 | 加 [tool.black/isort/mypy] | P1 |
| .pre-commit-config.yaml | ❌ | 加 (black/isort/mypy/flake8) | P2 |
| .github/ISSUE_TEMPLATE | ❌ | 加 (bug_report.md / feature_request.md) | P2 |
| .github/PULL_REQUEST_TEMPLATE.md | ❌ | 加 | P2 |
| CHANGELOG.md | ⚠️ 有 | 规范化 (Keep a Changelog) | P1 |
| LICENSE | ⚠️ 提到 | 实际添加 LICENSE 文件 | P1 |

---

## 11. 关键引用

- 本报告建议补建的 AGENTS.md (§1)
- `CONTRIBUTING.md` 草案 (§2)
- `pyproject.toml` 推荐配置 (§3.1)
- `.github/workflows/ci.yml` 草案 (§6.1)
- `deploy/bare_metal/README.md` — 部署权威

