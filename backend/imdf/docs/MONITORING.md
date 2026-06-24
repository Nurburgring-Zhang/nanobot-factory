# IMDF 生产监控指南 (Prometheus + Grafana + Alertmanager)

## 概述

IMDF 项目内置了 Prometheus 指标端点 (`/metrics`)，导出以下核心指标：

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `imdf_uptime_seconds` | Gauge | 服务运行时间 |
| `imdf_requests_total` | Counter | 总请求数 |
| `imdf_requests_by_status` | Counter | 按 HTTP 状态码分类 (2xx/3xx/4xx/5xx) |
| `imdf_requests_by_endpoint` | Counter | 按端点分类 |
| `imdf_errors_total` | Counter | 错误总数 (status >= 400) |
| `imdf_active_connections` | Gauge | 当前活跃 HTTP 连接 |
| `imdf_active_ws_connections` | Gauge | 当前活跃 WebSocket 连接 |
| `imdf_queue_depth` | Gauge | 任务队列深度 |
| `imdf_running_tasks` | Gauge | 运行中任务数 |
| `imdf_memory_rss_bytes` | Gauge | 进程 RSS 内存 |
| `imdf_memory_percent` | Gauge | 进程内存占比 |
| `imdf_request_latency_seconds` | Summary | 请求延迟 (P50/P95/P99 + 分桶) |

---

## 1. Prometheus 配置

### 1.1 安装 Prometheus

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install prometheus prometheus-node-exporter -y

# 或使用 Docker
docker run -d --name prometheus \
  --network host \
  -v $(pwd)/deploy/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest
```

### 1.2 创建 Prometheus 配置文件

在 `deploy/prometheus.yml` 中配置 IMDF 抓取目标：

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 30s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - "deploy/prometheus-alerts.yml"

scrape_configs:
  # ── IMDF 应用指标 ──
  - job_name: 'imdf'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['localhost:8765']
        labels:
          service: 'imdf'
          env: 'production'

  # ── Node Exporter (系统指标: CPU/内存/磁盘) ──
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']

  # ── Prometheus 自身 ──
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### 1.3 启动

```bash
# systemd (推荐)
sudo cp deploy/prometheus.yml /etc/prometheus/prometheus.yml
sudo systemctl enable --now prometheus prometheus-node-exporter

# 验证
curl http://localhost:9090/api/v1/targets
curl http://localhost:8765/metrics | head -20
```

---

## 2. Grafana 配置

### 2.1 安装 Grafana

```bash
# Ubuntu/Debian
sudo apt install -y software-properties-common wget
sudo wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" \
  | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt update
sudo apt install grafana -y

# 或 Docker
docker run -d --name grafana \
  --network host \
  -v grafana-storage:/var/lib/grafana \
  grafana/grafana:latest
```

### 2.2 启动

```bash
sudo systemctl enable --now grafana-server
# Grafana 默认在 http://localhost:3000
# 初始登录: admin / admin (首次登录会要求修改密码)
```

### 2.3 添加 Prometheus 数据源

1. 登录 Grafana: `http://localhost:3000`
2. **Connections → Data Sources → Add data source → Prometheus**
3. 设置 URL: `http://localhost:9090`
4. 点击 **Save & test**

### 2.4 导入 IMDF 仪表盘

```bash
# 方法一: 通过 Grafana UI 导入
# 1. Dashboards → New → Import
# 2. 上传 deploy/grafana-dashboard.json 或粘贴 JSON 内容
# 3. 选择 Prometheus 数据源 → Import

# 方法二: 通过 API 导入
curl -X POST http://admin:YOUR_PASSWORD@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @deploy/grafana-dashboard.json
```

### 2.5 仪表盘概览

导入的 `IMDF 生产监控` 仪表盘有 4 行面板:

| 行 | 面板 | 监控内容 |
|----|------|----------|
| **Row 1: 服务健康** | 服务状态/Uptime/连接/队列/任务 + 请求速率/状态码 | 服务在线、流量分布 |
| **Row 2: API延迟** | P50/P95/P99 延迟 + 分位数趋势 | API性能、瓶颈检测 |
| **Row 3: 数据生产量** | 端点请求速率、错误率、累计请求 | 数据吞吐量 |
| **Row 4: 系统资源** | 进程内存/磁盘/CPU + 连接趋势 | 基础设施健康 |

---

## 3. Alertmanager 告警配置

### 3.1 安装 Alertmanager

```bash
sudo apt install prometheus-alertmanager -y

# 或 Docker
docker run -d --name alertmanager \
  --network host \
  -v $(pwd)/deploy/alertmanager.yml:/etc/alertmanager/alertmanager.yml \
  prom/alertmanager:latest
```

### 3.2 配置 Alertmanager

创建 `deploy/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m

# ── 通知路由 ──
route:
  group_by: ['alertname', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'critical'

# ── 通知接收器 ──
receivers:
  # 默认: 控制台输出
  - name: 'default'
    webhook_configs:
      - url: 'http://localhost:8765/api/v1/alerts/webhook'

  # 严重告警: 邮件 + Webhook
  - name: 'critical'
    email_configs:
      - to: 'ops@your-domain.com'
        from: 'imdf-alerts@your-domain.com'
        smarthost: 'smtp.your-domain.com:587'
        auth_username: 'imdf-alerts@your-domain.com'
        auth_password: 'YOUR_SMTP_PASSWORD'
    webhook_configs:
      - url: 'http://localhost:8765/api/v1/alerts/webhook'
```

### 3.3 告警规则说明

`deploy/prometheus-alerts.yml` 包含以下告警规则:

| 告警名 | 条件 | 严重度 | for |
|--------|------|--------|-----|
| `IMDFHighErrorRate` | API 错误率 > 5% (5m rate) | critical | 2m |
| `IMDFHighLatency` | P95 延迟 > 2s | warning | 3m |
| `IMDFCriticalLatency` | P99 延迟 > 5s | critical | 2m |
| `IMDFServiceDown` | 服务不可达 (up==0) | critical | 1m |
| `IMDFFrequentRestarts` | 10min 内重启 > 2 次 | warning | 0m |
| `IMDFQueueBacklog` | 队列深度 > 100 | warning | 5m |
| `IMDFHighConnections` | 活跃连接 > 1000 | warning | 3m |
| `IMDFLowDiskSpace` | 磁盘可用 < 10GB | critical | 5m |
| `IMDFDiskAlmostFull` | 磁盘使用率 > 90% | critical | 5m |
| `IMDFHighMemoryUsage` | 系统内存 > 90% | warning | 5m |
| `IMDFHighCPUUsage` | CPU > 90% | warning | 5m |
| `IMDFMemoryLeak` | 进程内存增长 > 10MB/h | warning | 30m |

---

## 4. 完整部署步骤

### 4.1 一键部署脚本

```bash
#!/bin/bash
# deploy/setup-monitoring.sh
set -e

echo "=== IMDF 监控栈部署 ==="

# 1. 安装组件
sudo apt update
sudo apt install -y prometheus prometheus-node-exporter prometheus-alertmanager grafana

# 2. 配置 Prometheus
sudo cp deploy/prometheus.yml /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus

# 3. 配置 Node Exporter
sudo systemctl enable --now prometheus-node-exporter

# 4. 配置告警规则
sudo mkdir -p /etc/prometheus/rules
sudo cp deploy/prometheus-alerts.yml /etc/prometheus/rules/

# 5. 启动 Alertmanager
sudo systemctl enable --now prometheus-alertmanager

# 6. 启动 Grafana
sudo systemctl enable --now grafana-server

# 7. 健康检查
sleep 5
echo ""
echo "Prometheus:  http://localhost:9090/targets"
echo "Grafana:     http://localhost:3000 (admin/admin)"
echo "Alertmanager: http://localhost:9093"
echo "IMDF Metrics: http://localhost:8765/metrics"
echo ""
echo "导入仪表盘: curl -X POST http://admin:PASSWORD@localhost:3000/api/dashboards/db -H 'Content-Type: application/json' -d @deploy/grafana-dashboard.json"
```

### 4.2 Docker Compose (可选)

```yaml
# deploy/docker-compose-monitoring.yml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    network_mode: host
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus-alerts.yml:/etc/prometheus/rules/alerts.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  alertmanager:
    image: prom/alertmanager:latest
    network_mode: host
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml

  node-exporter:
    image: prom/node-exporter:latest
    network_mode: host
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'

  grafana:
    image: grafana/grafana:latest
    network_mode: host
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}

volumes:
  prometheus_data:
  grafana_data:
```

```bash
# 启动监控栈
docker-compose -f deploy/docker-compose-monitoring.yml up -d
```

---

## 5. 验证与测试

### 5.1 验证 Prometheus 抓取

```bash
# 检查 targets 状态
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -E '"job"|"health"'

# 查询 IMDF 指标
curl -s 'http://localhost:9090/api/v1/query?query=imdf_uptime_seconds' | python3 -m json.tool
```

### 5.2 验证 Grafana 数据源

```bash
# 测试 Prometheus 数据源连接
curl -s http://admin:YOUR_PASSWORD@localhost:3000/api/datasources/proxy/1/api/v1/query?query=up
```

### 5.3 验证告警

```bash
# 查看当前活跃告警
curl -s http://localhost:9093/api/v2/alerts | python3 -m json.tool

# 或通过 Prometheus
curl -s http://localhost:9090/api/v1/alerts | python3 -m json.tool
```

### 5.4 运行健康验证脚本

```bash
python3 scripts/validate.py
```

输出示例:
```
  [✓] 磁盘空间 — 可用 45.2GB / 总量 100.0GB (55%已用)
  [✓] 系统内存 — 可用 8.3GB / 总量 16.0GB (48%已用)
  [✓] CPU 使用率 — 12% (cores: 8)
  [✓] fastapi — v0.111.0 (>= 0.110.0)
  [✓] prometheus_client — v0.20.0 (>= 0.19.0)
  ...
  [✓] 健康检查 (Basic) — HTTP 200 v2.0.0 uptime=3600s
  [✓] Prometheus 指标 — HTTP 200
```

---

## 6. 日常运维

### 6.1 日志路径

| 组件 | 日志位置 |
|------|----------|
| IMDF API | `logs/access.log`, `logs/error.log` |
| IMDF systemd | `journalctl -u imdf` |
| Prometheus | `journalctl -u prometheus` 或 `/var/log/prometheus/` |
| Grafana | `/var/log/grafana/grafana.log` |
| Alertmanager | `journalctl -u prometheus-alertmanager` |

### 6.2 常用命令

```bash
# 查看所有服务状态
sudo systemctl status imdf prometheus grafana-server prometheus-alertmanager

# 重启监控栈
sudo systemctl restart prometheus grafana-server

# 查看 Prometheus 存储空间
du -sh /var/lib/prometheus/

# 检查 metrics 端点
curl -s http://localhost:8765/metrics | grep -E "^imdf_" | sort
```

### 6.3 清理 Prometheus 数据

```bash
# 保留策略: 30天 (在 prometheus.yml 中设置)
# --storage.tsdb.retention.time=30d
```

### 6.4 备份 Grafana 仪表盘

```bash
# 导出所有仪表盘
curl -s http://admin:PASSWORD@localhost:3000/api/search?type=dash-db | python3 -m json.tool

# 导出特定仪表盘 (通过 UID)
DASHBOARD_UID="imdf-production-monitoring"
curl -s http://admin:PASSWORD@localhost:3000/api/dashboards/uid/${DASHBOARD_UID} \
  | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['dashboard'], indent=2))" \
  > deploy/grafana-dashboard-backup.json
```

---

## 7. 故障排查

| 问题 | 检查方法 | 解决方案 |
|------|----------|----------|
| `up{job="imdf"} == 0` | `curl http://localhost:8765/metrics` | 确认 IMDF 服务在运行 |
| Grafana 无数据 | Grafana → Explore → 选 Prometheus → 查询 `up` | 检查数据源 URL 是否正确 |
| 告警不触发 | Prometheus → Alerts 页面 | 检查 `for` 持续时间是否满足 |
| Node metrics 缺失 | `curl http://localhost:9100/metrics` | 启动 node_exporter |
| 告警未发送邮件 | Alertmanager 日志 | 检查 SMTP 配置和网络连接 |

---

## 8. 扩展

### 8.1 自定义告警通知

支持的通知渠道:

- **Email**: SMTP (见 `alertmanager.yml`)
- **Slack**: `slack_configs`
- **Webhook**: `webhook_configs` → IMDF 自带 `/api/v1/alerts/webhook`
- **PagerDuty**: `pagerduty_configs`
- **Telegram**: 通过 webhook → bot API

### 8.2 添加自定义指标

在 `engines/metrics.py` 中扩展 `MetricsRegistry`:

```python
# 添加新指标
self._custom_metric: int = 0

# 在 snapshot() 和 prometheus_text() 中导出
```

### 8.3 添加 Grafana 面板

编辑 `deploy/grafana-dashboard.json`，或通过 Grafana UI 添加面板后导出。

---

## 参考端口

| 服务 | 端口 | URL |
|------|------|-----|
| IMDF API | 8765 | http://localhost:8765 |
| IMDF Metrics | 8765 | http://localhost:8765/metrics |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3000 | http://localhost:3000 |
| Alertmanager | 9093 | http://localhost:9093 |
| Node Exporter | 9100 | http://localhost:9100/metrics |
