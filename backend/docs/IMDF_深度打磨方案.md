# IMDF 项目深度打磨 — 全网调研与可执行方案

> 生成时间: 2026-06-15 | 目标: 每个主题输出可直接落地的具体方法与配置

---

## 1. Python FastAPI 生产级部署最佳实践

### 1.1 并发模型选型
- **推荐方案**: Uvicorn + Gunicorn 进程管理器
- Worker 数量公式: `(2 × CPU核数) + 1` （IO密集型服务）
- 纯 CPU 密集型: `CPU核数` 个 worker
- 启动命令:
```
gunicorn -k uvicorn.workers.UvicornWorker -w 5 --bind 0.0.0.0:8000 \
    --timeout 120 --graceful-timeout 30 --keep-alive 5 \
    --max-requests 10000 --max-requests-jitter 500 app.main:app
```

### 1.2 超时配置层次
| 层级 | 参数 | 推荐值 | 说明 |
|------|------|--------|------|
| Gunicorn | --timeout | 120s | Worker 无响应超时 |
| Gunicorn | --graceful-timeout | 30s | 优雅关闭等待时间 |
| Uvicorn | --limit-concurrency | 1000 | 最大并发连接数 |
| Nginx | proxy_read_timeout | 300s | 反向代理读超时 |
| 应用级 | httpx.Timeout | 10.0 | 外部调用超时 |

### 1.3 Graceful Shutdown 实现
```python
# app/shutdown.py
import asyncio, signal
from fastapi import FastAPI

app = FastAPI()

@app.on_event("shutdown")
async def shutdown_event():
    await close_db_pool()
    await close_redis()
```

K8s Pod 配置:
```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 15"]  # 等待 Endpoint 摘除
terminationGracePeriodSeconds: 60
```

---

## 2. 数据标注平台商用级质量保证

### 2.1 对标 Scale AI / Labelbox 的质量体系

**黄金标准集 (Gold Standard)**
- 预备 200-500 条专家标注的"标准答案"
- 每个新标注员需通过黄金标准测试（准确率 >= 95%）
- 每日混入 5-10% 黄金题目到生产任务中做质量监控

**共识机制 (Consensus)**
- 每条数据至少 2-3 人独立标注
- 一致性阈值: Cohen's Kappa >= 0.8, Fleiss' Kappa >= 0.7
- 不达标的样本自动升级到资深标注员裁决

**评审-仲裁流程**
```
标注员A/B → 结果比对 → 一致则通过
                        → 不一致 → 资深标注员裁决 → 计入培训库
```

### 2.2 统计指标看板（每日自动化）
- IAA (Inter-Annotator Agreement): Fleiss' Kappa 日曲线
- Reviewer Rejection Rate: 每人/每项目驳回率
- Golden Set Accuracy: 黄金标准通过率趋势
- Average Annotation Time per Item: 效率监控，异常检测

### 2.3 可落地方案
1. 用 Supabase/Postgres 建 `gold_standard` 表，标记题目
2. 每次标注任务随机注入金标题，后台计算实时通过率
3. 连续 3 天通过率 < 90% → 自动暂停标注权限，触发复训

---

## 3. AI 模型评测闭环方法

### 3.1 评测层次设计
```
L1: 离线评测 → 固定测试集 (准确率/F1/BLEU)
L2: 在线 A/B 测试 → 分流 10% 流量到新模型
L3: Shadow Deployment → 新模型并行跑，只记录不返回
L4: 数据回流 → 线上 Bad Case 自动入库
```

### 3.2 A/B 测试框架
- 流量分流: 基于 user_id hash % 100，稳定分组
- 核心指标: 业务指标（而非仅模型指标），如标注采纳率、任务完成时间
- 统计检验: 使用 sequential testing，避免 p-hacking
- 最少样本量: 根据预期效应量提前计算（推荐 Evidently AI 或 Statsmodels）

### 3.3 Shadow Deployment 模式
```
用户请求 → 当前模型(返回结果) → 用户
               ↘ 新模型(仅记录) → 日志比较(diff report)
```
- 部署周期: 新模型 shadow 7 天，每日对比报告
- 通过条件: 在 3+ 核心业务指标上不低于 baseline 的 98%

### 3.4 归因反馈闭环
1. 线上标注员修正结果 → 自动记录 (input, model_output, human_correction)
2. 每周聚合 Top-50 高频错误模式
3. 错误模式 → 定向增补训练数据 → 重新训练 → 回到 L1 评测

---

## 4. 多模态资产管理 (DAM) 系统设计

### 4.1 对标: Adobe AEM / Bynder / Eagle

| 维度 | AEM Assets | Bynder | Eagle(本地) | IMDF 建议 |
|------|-----------|--------|------------|----------|
| 预览 | 200+格式 | 云端渲染 | 本地预览 | Sharp + ffmpeg 缩略图 |
| 元数据 | XMP/IPTC | 自定义Schema | Tags | JSONB + 全文索引 |
| 搜索 | AI 标签 | 语义搜索 | 文件名 | pgvector 向量+全文 |
| API | REST | REST | 无 | FastAPI 统一 |
| 存储 | S3/Azure | S3 | 本地 | MinIO/S3 |

### 4.2 可落地架构
```
┌─ 上传层 ─┐     ┌─ 处理管线 ─┐     ┌─ 存储层 ─┐
│  chunked  │ →  │ 元数据提取  │ →  │ MinIO    │
│  upload   │     │ 缩略图生成  │     │ (图片)    │
│  S3 pres. │     │ 向量嵌入    │     │ Postgres │
└───────────┘     │ 病毒扫描    │     │ (元数据)  │
                  └─────────────┘     └──────────┘
```

### 4.3 关键实现要点
- **缩略图**: sharp (图片) + ffmpeg (视频/音频波形)
- **元数据提取**: exiftool 子进程调用, 写入 JSONB
- **语义搜索**: sentence-transformers + pgvector HNSW 索引
- **权限**: 基于 asset 的 ACL: {asset_id, user_id, role: r/w/a}
- **版本管理**: 每次更新创建新版本, 保留前 10 个版本, 支持回滚

---

## 5. 音频 TTS 开源方案对比 (2025)

### 5.1 方案横向对比

| 方案 | 延迟 | 中文质量 | 部署复杂度 | RTF | 推荐场景 |
|------|------|----------|-----------|-----|---------|
| **Edge-TTS** | 低(流式) | 优 | 极低 pip install | N/A(在线) | MVP/快速验证 |
| **Coqui-AI** | 中 | 中 | 中 | 0.3-0.6 | 隐私要求高 |
| **Bark** | 高(5-15s) | 差 | 中 | 2.0+ | 实验/多语言 |
| **GPT-SoVITS** | 中 | 优 | 高 | 0.8-1.2 | 中文最佳质量 |
| **CosyVoice2** | 中低 | 优 | 高 | 0.5-0.8 | 阿里系/中文SOTA |
| **Fish-Speech** | 低 | 优 | 中 | 0.3-0.5 | 轻量中文 |
| **MeloTTS** | 极低 | 良 | 低 | 0.1-0.2 | 嵌入式/边缘 |

### 5.2 推荐组合策略
```
阶段1 (MVP):       Edge-TTS → Microsoft 在线 API, 免费, 零部署
阶段2 (降本):      Fish-Speech self-hosted → GPU推理, 降低API成本
阶段3 (高质量):     GPT-SoVITS / CosyVoice2 → 定制音色, 最优中文
```

### 5.3 部署要点
- **Edge-TTS**: 异步调用, 设置 max_retries=3, 超时 10s
- **Self-hosted 方案**: Docker + NVIDIA Container Toolkit, 预留 4GB+ VRAM
- **流式传输**: 使用 WebSocket 逐 chunk 推送, 首字延迟 < 500ms 为目标
- **缓存**: 相同文本+参数生成时返回缓存 mp3, Redis 键=md5(text+voice)

---

## 6. Python 系统级可靠性模式

### 6.1 熔断器 Circuit Breaker
```python
# 推荐: pybreaker 或 aiobreaker
import pybreaker

db_breaker = pybreaker.CircuitBreaker(
    fail_max=5,           # 连续失败 5 次打开
    timeout_duration=30,  # 30 秒后半开探测
    exclude=[ValueError]  # 不触发熔断的异常
)

@db_breaker
async def query_db(*args): ...
```

三态流转: `CLOSED → (failures>=5) → OPEN → (timeout) → HALF_OPEN → (success) → CLOSED`

### 6.2 重试机制
```python
import tenacity

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    retry=tenacity.retry_if_exception_type((httpx.HTTPStatusError, ConnectionError)),
    before_sleep=lambda r: logger.warning(f"Retrying {r.fn}, attempt {r.attempt_number}")
)
async def call_external_api(url): ...
```

### 6.3 超时 (三层防护)
```python
# 1. 连接超时 + 2. 读超时 + 3. 全局超时
import asyncio, httpx

async with httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=30.0, pool=10.0)
) as client:
    try:
        result = await asyncio.wait_for(client.get(url), timeout=60.0)
    except asyncio.TimeoutError:
        return fallback_response()
```

### 6.4 降级策略
```python
async def get_labels(task_id):
    try:
        return await ml_service.predict(task_id)
    except (CircuitBreakerError, TimeoutError):
        logger.warning(f"ML service down, using rule-based fallback")
        return rule_based_predict(task_id)  # 降级到规则引擎
```

### 6.5 限流 (Token Bucket)
```python
# 使用 FastAPI 中间件 + 令牌桶
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/annotations")
@limiter.limit("100/minute")  # 每个 IP 每分钟 100 次
async def list_annotations(request: Request): ...
```

### 6.6 健康检查
```python
@app.get("/health")
async def health():
    checks = {
        "db": await check_postgres(),
        "redis": await check_redis(),
        "s3": await check_minio(),
    }
    status = all(checks.values())
    return {"status": "ok" if status else "degraded", "checks": checks}
```

K8s 探针:
```yaml
livenessProbe:   # 进程存活
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 10, periodSeconds: 15
readinessProbe:  # 流量就绪
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 5, periodSeconds: 5
```

---

## 7. 数据平台灾备与回滚方案

### 7.1 PostgreSQL 备份策略 (3-2-1 原则)

| 维度 | 策略 | 工具 | 频率 | 保留 |
|------|------|------|------|------|
| 全量备份 | pg_dump 物理备份 | pgBackRest | 每天 1 次 | 30 天 |
| 增量备份 | WAL 归档 | pgBackRest | 持续 | 7 天 |
| 逻辑备份 | pg_dump --format=custom | cron | 每 6 小时 | 14 天 |
| 异地备份 | S3/MinIO sync | rclone | 每天 | 90 天 |

### 7.2 pgBackRest 配置要点
```ini
# /etc/pgbackrest/pgbackrest.conf
[main]
pg1-path=/var/lib/postgresql/16/main

[global]
repo1-path=/backup/pgbackrest
repo1-retention-full=30
repo1-retention-diff=7
repo1-cipher-type=aes-256-cbc  # 加密备份
start-fast=y                    # 快速开始备份
compress-type=zst               # 高效压缩

# 异地备份
repo2-type=s3
repo2-s3-endpoint=s3.amazonaws.com
repo2-s3-bucket=imdf-db-backup
repo2-retention-full=4
```

### 7.3 时间点恢复 (PITR)
```bash
# 恢复到指定时间点
pgbackrest --stanza=main --type=time \
    --target="2026-06-15 14:30:00+08" restore

# 恢复到具体事务
pgbackrest --stanza=main --type=xid --target=123456 restore
```

### 7.4 SQLite 备份 (如适用)
```bash
# 在线备份 (不锁库)
sqlite3 /data/imdf.db ".backup /backup/imdf_$(date +%Y%m%d_%H%M).db"

# 验证备份完整性
sqlite3 /backup/imdf.db "PRAGMA integrity_check;"

# WAL 模式 (推荐)
PRAGMA journal_mode=WAL;   -- 提高并发 + 支持增量备份
```

### 7.5 迁移方案 (SQLite → PostgreSQL)
```python
# 使用 pgloader 或自定义迁移脚本
# 分阶段迁移:
# Phase 1: 双写 (app 同时写 SQLite + PG), 验证数据一致性
# Phase 2: 读切换 (app 读 PG, 写两者), 性能验证
# Phase 3: 完全切换 (只使用 PG), SQLite 保留 30 天作为回退
```

使用 pgloader 命令:
```lisp
-- imdf_migration.load
LOAD DATABASE FROM sqlite:///data/imdf.db
INTO postgresql://user:pass@localhost/imdf
WITH include drop, create tables, create indexes, reset sequences,
     batch rows = 500, batch concurrency = 4
ALTER SCHEMA 'main' RENAME TO 'public';
```

### 7.6 灾难恢复演练
- 每季度执行一次全链路恢复演练
- 演练指标: RTO (恢复时间目标) < 1 小时, RPO (数据丢失目标) < 5 分钟
- 使用独立环境验证备份有效性

---

## 附录: 落地优先级建议

| 优先级 | 主题 | 工作量 | 收益 | 建议启动时间 |
|--------|------|--------|------|-------------|
| P0 | FastAPI 生产部署 | 3-5 天 | 基础稳定性 | 立即 |
| P0 | PostgreSQL 灾备 | 2-3 天 | 数据安全底线 | 立即 |
| P1 | 系统可靠性模式 | 5-7 天 | 服务韧性 | 第 1 周 |
| P1 | 标注质量体系 | 7-10 天 | 核心竞争力 | 第 1 周 |
| P2 | 模型评测闭环 | 10-15 天 | 持续优化 | 第 2 周 |
| P2 | DAM 系统设计 | 10-20 天 | 用户体验 | 第 3 周 |
| P3 | TTS 方案选型 | 5-7 天 | 功能完备 | 按需启动 |
