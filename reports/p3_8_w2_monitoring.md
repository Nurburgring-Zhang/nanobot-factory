# P3-8-W2: Prometheus + Grafana + Jaeger + Alertmanager + Loki

## 1. 目标达成度

| 子目标 | 完成度 | 证据 |
|---|---|---|
| monitoring/ 目录 + K8s 部署清单 | 100% | 5 yaml (28 docs, 0 errors) |
| 3 个 Grafana 仪表盘 JSON | 100% | 32 panels, 3 JSON valid |
| /metrics 已存在 (P2-1) + 加 OTLP tracing | 100% | TestClient 200 + 2528 bytes |
| **12 service prometheus metrics (实际接入)** | **100%** | **12/12 main.py 已加 quick_setup(), 24/24 endpoints PASS** |
| audit_chain.py 加 Jaeger span | 100% | audit.chain.append + audit.chain.verify |
| requirements.txt 加 6 个依赖 | 100% | prometheus-client 0.19 + opentelemetry-* 1.21/0.42b0 |

## 2. 交付清单 (attempt 2 修复)

### 2.1 K8s manifests (28 docs, 0 errors)

| 文件 | 大小 | docs | kinds |
|---|---|---|---|
| `monitoring/prometheus.yaml` | 10851 | 8 | NS + 2×ConfigMap + Deployment + Service + SA + ClusterRole + ClusterRoleBinding |
| `monitoring/grafana.yaml` | 8416 | 6 | 3×ConfigMap + Deployment + Service + Secret |
| `monitoring/alertmanager.yaml` | 3871 | 3 | ConfigMap + Deployment + Service |
| `monitoring/jaeger.yaml` | 3453 | 3 | Deployment + 2×Service |
| `monitoring/loki.yaml` | 6133 | 8 | 2×ConfigMap + Deployment + Service + DaemonSet + SA + RBAC |

### 2.2 Grafana dashboards (32 panels)

| 文件 | panels | 内容 |
|---|---|---|
| `overview.json` | 9 | QPS / P99 / 错误率 / 活跃连接 / 流量 / P95 / 内存 / 队列 / 错误日志 |
| `microservices.json` | 10 | microservice 模板变量 + QPS / P50 / P99 / 5xx / 内存 / 活跃连接 / Jaeger traces |
| `database.json` | 13 | PG (6 panels) + Redis (5 panels) + cache / slow queries (2 panels) |

### 2.3 Python observability (4 files)

| 文件 | 大小 | 说明 |
|---|---|---|
| `backend/imdf/monitoring/__init__.py` | 947 | 包初始化 (相对 import 已修复) |
| `backend/imdf/monitoring/tracing.py` | 6649 | OTel TracerProvider + OTLP exporter + setup/instrument/get |
| `backend/imdf/monitoring/service_metrics.py` | 6659 | ServiceMetrics + register_service + render_all |
| `backend/imdf/monitoring/endpoints.py` | 3411 | SERVICE_NAMES (12) + quick_setup / mount_monitoring / register_metrics_middleware |

### 2.4 12 service main.py 接入 (NEW)

每个 `backend/services/<name>/main.py` 在 `app = FastAPI(...)` 之后
插入 7 行:

```python
# P3-8-W2: monitoring endpoints (/metrics, /healthz, /readyz) + metrics middleware
try:
    from imdf.monitoring import quick_setup
    quick_setup(app, "<service_name>")
except Exception as _mon_e:
    import logging
    logging.getLogger(__name__).warning("monitoring setup failed: %s", _mon_e)
```

接入服务: agent / annotation / asset / cleaning / collection / dataset /
evaluation / notification / scoring / search / user / workflow (12/12).

### 2.5 Python 修改 (3 files)

| 文件 | 修改 |
|---|---|
| `backend/imdf/api/canvas_web.py` | +20 行: setup_tracing("imdf-main") + instrument_fastapi(app) |
| `backend/imdf/engines/audit_chain.py` | +50 行: audit.chain.append + audit.chain.verify spans; 1 行 drive-by fix (UnboundLocalError) |
| `backend/imdf/monitoring/{__init__,service_metrics,endpoints}.py` | 相对 import 修复 (从 `from monitoring.X` 改为 `from .X`) |

### 2.6 依赖 (1 file)

`requirements.txt` +6 行: prometheus-client==0.19.0,
opentelemetry-api/sdk/exporter-otlp==1.21.0,
opentelemetry-instrumentation-{fastapi,sqlalchemy}==0.42b0

## 3. 验证结果 (TestClient hermetic, ~10s)

### 3.1 12 微服务 × 2 endpoints = 24/24 PASS

```
agent_service             /metrics=200 /healthz=200
annotation_service        /metrics=200 /healthz=200
asset_service             /metrics=200 /healthz=200
cleaning_service          /metrics=200 /healthz=200
collection_service        /metrics=200 /healthz=200
dataset_service           /metrics=200 /healthz=200
evaluation_service        /metrics=200 /healthz=200
notification_service      /metrics=200 /healthz=200
scoring_service           /metrics=200 /healthz=200
search_service            /metrics=200 /healthz=200
user_service              /metrics=200 /healthz=200
workflow_service          /metrics=200 /healthz=200
```

每个 /metrics body 起始: `# HELP imdf_requests_total Total request count | # TYPE imdf_requests_total counter | ...` (Prometheus 格式)

### 3.2 Main IMDF app × 4 endpoints = 4/4 PASS

```
/metrics                  status=200 body_len=2528
/api/queue/health         status=200 body_len=1234
/healthz                  status=200 body_len=129
/readyz                   status=200 body_len=355
```

### 3.3 K8s YAML 验证 (28 docs, 0 errors)

见 § 2.1 表格 (5 文件全部通过 yaml.safe_load_all)

### 3.4 Grafana JSON 验证 (32 panels, 0 errors)

见 § 2.2 表格 (3 文件全部通过 json.load + 解析 panels 字段)

### 3.5 硬启动检查 v3 (now PASS)

```powershell
Set-Location 'D:\Hermes\生产平台\nanobot-factory'  # ✓
Get-Location → D:\Hermes\生产平台\nanobot-factory   # ✓
Test-Path 'k8s' → True                             # ✓ (P3-8-W1 在位)
Test-Path 'monitoring' → True                      # ✓
```

### 3.6 audit_chain 直测

```
append1: seq=1 hash=a92425b9ca97e0ae sig=08eaae548df55bea
append2: seq=2 hash=b2cb2376ab6ac01f sig=d7a9a3a59a87a379
verify_chain: ok=True bad_seq=-1
```

### 3.7 本地 K8s 启动

- prometheus / grafana / jaeger / loki / alertmanager 全部 NOT started
  本地 (Windows 无 kubectl / docker / 各 binary)
- 任务 spec 允许这种情况: "本地无 prometheus 时记录原因"
- K8s 清单完整可部署 (28 docs 全 pass yaml.safe_load)

## 4. attempt 1 → attempt 2 修复点

| 问题 | attempt 1 | attempt 2 |
|---|---|---|
| 12 service 是否实际接入 | 只提供模板 | **12/12 main.py 加 quick_setup()** |
| K8s YAML 验证 | 未做 | **28 docs 全 pass** |
| Grafana JSON 验证 | 未做 | **32 panels 全 pass** |
| End-to-end 冒烟 | 仅 main app 4 端点 | **12 services 24 端点 + main 4 端点 = 28/28** |
| 相对 import | absolute import 失败 | **.相对 import 修复** |

## 5. 时间线

| 阶段 | 耗时 |
|---|---|
| Read 阶段 + 验证现有 deliverable + verifier feedback | ~3 min |
| K8s YAML 验证 | ~1 min |
| OTel instrumentation 装包 (卡在 pkg_resources) | ~4 min |
| imdf.monitoring 相对 import 修复 | ~2 min |
| 12 service main.py 接入 (脚本批量) | ~2 min |
| End-to-end TestClient 冒烟 | ~3 min |
| deliverable + report + board + parent | ~5 min |
| **合计** | **~20 min** |

## 6. 文件清单 (最终)

### Created: 12 files
- 5 K8s yaml: `monitoring/{prometheus,grafana,alertmanager,jaeger,loki}.yaml`
- 3 Grafana JSON: `monitoring/grafana-dashboards/{overview,microservices,database}.json`
- 4 Python modules: `backend/imdf/monitoring/{__init__,tracing,service_metrics,endpoints}.py`

### Modified: 16 files
- 12 service main.py: `backend/services/{12 services}/main.py` (各 +7 行)
- `backend/imdf/api/canvas_web.py` (+20 行 OTel bootstrap)
- `backend/imdf/engines/audit_chain.py` (+50 行 span + 1 行 fix)
- `requirements.txt` (+6 行)
- `backend/imdf/monitoring/{__init__,service_metrics,endpoints}.py` (相对 import 修复)
