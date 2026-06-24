# Runbook — Nanobot Factory

> 值班 / SRE 必读。本文列出 **6 个高频故障** 的处置 SOP + 通用调试技巧。
>
> 紧急联系人：见内部值班表
> 监控面板：Grafana `nanobot-factory / Overview`
> 日志聚合：Loki / ELK

## 故障分级

| 级别 | 名称 | 含义 | 响应 SLA |
|------|------|------|----------|
| **P0** | 全站不可用 | 用户全部无法登录或 5xx > 50% | 立即响应 |
| **P1** | 部分功能不可用 | 单模块（如 AIGC 渲染）失败；单区域不可用 | 15 min |
| **P2** | 性能劣化 | 延迟 / 错误率升高但仍可用 | 1 h |
| **P3** | 体验问题 | UI 小 bug、文档不一致 | 24 h |

---

## 0. 通用排查工具

```bash
# 集群视图
kubectl -n nanobot-factory get all,ing,pvc,hpa,pdb
kubectl -n nanobot-factory describe deploy/nanobot-factory
kubectl -n nanobot-factory get pods -o wide -w

# 日志
kubectl -n nanobot-factory logs -f deploy/nanobot-factory --tail=200
kubectl -n nanobot-factory logs -f <pod> -c nanobot-factory --previous    # 上一个容器

# 端口转发
kubectl -n nanobot-factory port-forward svc/nanobot-factory 8080:80
curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz
curl -fsS http://localhost:8080/metrics | head -30

# 进容器
kubectl -n nanobot-factory exec -it <pod> -- sh

# 看事件
kubectl -n nanobot-factory get events --sort-by=.lastTimestamp | tail -30

# 资源使用
kubectl -n nanobot-factory top pods
```

---

## 故障 1 — `/healthz` 失败 (Pod 重启循环)

### 现象

- 监控告警：`probe failed`
- `kubectl get pods` 显示 `CrashLoopBackOff`
- 5xx 错误率上升

### 排查

```bash
# 1. 看当前状态
kubectl -n nanobot-factory get pods -l app.kubernetes.io/name=nanobot-factory

# 2. 看崩溃日志
kubectl -n nanobot-factory logs <pod> --previous --tail=300

# 3. 常见根因：
#    a) uvicorn 启动失败 (ImportError / 端口被占)
#    b) ConfigMap 字段错误 (Pydantic ValidationError)
#    c) PVC 挂载失败 (ReadOnlyMany → 实际是 RWO)
#    d) livenessProbe 太激进 (curl 报 "Connection refused" 因为 nginx 还没起)
```

### 修复 SOP

1. **扩大 startupProbe 容错**（已经在 chart 中给 30 次 × 5s = 150s 启动窗口）：
   ```yaml
   startupProbe:
     failureThreshold: 30
     periodSeconds: 5
   ```
2. **如果是 PVC 问题**：
   ```bash
   kubectl -n nanobot-factory describe pvc nanobot-factory-data
   # 若 accessModes 不匹配 → 改 values.yaml 后 helm upgrade
   ```
3. **如果是配置错误**：
   ```bash
   kubectl -n nanobot-factory get cm nanobot-factory-config -o yaml
   # 改 ConfigMap 后滚动重启
   kubectl -n nanobot-factory rollout restart deploy/nanobot-factory
   ```
4. **临时绕开**：把 `replicas` 调到 0，再 1，再正常：
   ```bash
   kubectl -n nanobot-factory scale deploy/nanobot-factory --replicas=0
   sleep 5
   kubectl -n nanobot-factory scale deploy/nanobot-factory --replicas=1
   # 验证后恢复
   ```

### 预防

- 镜像先在 staging 跑 24h 再升 prod
- 启用 `readinessProbe` 失败时优雅摘流量
- 任何 ConfigMap 改动先 dry-run：`helm template`

---

## 故障 2 — `/readyz` 失败 (DB / Redis 不可达)

### 现象

- Service 没有 ready endpoint → 流量被摘 → 5xx
- 监控：`readyz_status{check="database"} = 0`

### 排查

```bash
# 进容器
kubectl -n nanobot-factory exec -it <pod> -- sh

# 1. SQLite 检查
ls -la /app/data/
sqlite3 /app/data/nanobot.db "PRAGMA integrity_check;"
# → ok 表示健康；disk I/O error → 存储问题

# 2. Redis (如果在用)
apk add redis    # 或 apt-get install redis-tools
redis-cli -h <redis-host> ping
# → PONG 健康

# 3. 磁盘空间
df -h /app/data /app/logs
# → 满 (>90%) 立刻扩 PVC
```

### 修复 SOP

1. **磁盘满**：
   ```bash
   # 短期：清理日志
   kubectl -n nanobot-factory exec <pod> -- sh -c 'find /app/logs -name "*.log.*" -mtime +7 -delete'
   # 长期：扩 PVC
   kubectl -n nanobot-factory edit pvc nanobot-factory-data
   # spec.resources.requests.storage: 100Gi → 200Gi
   ```
2. **SQLite 损坏**：
   ```bash
   # 备份并尝试恢复
   kubectl -n nanobot-factory exec <pod> -- cp /app/data/nanobot.db /app/data/nanobot.db.bak
   sqlite3 /app/data/nanobot.db ".recover" | sqlite3 /app/data/nanobot-recovered.db
   mv /app/data/nanobot-recovered.db /app/data/nanobot.db
   ```
3. **Redis 不可达**：
   - 检查 redis pod / service 是否 alive
   - 检查防火墙 / NetworkPolicy
   - 必要时切到 `DEV_MODE=true` 暂时绕过 cache

### 预防

- 监控 `disk_free_mb` 指标，> 80% 触发扩容
- SQLite 定期 `VACUUM` (建议每周 cron job)
- Redis 部署成 cluster (3 master + 3 replica)

---

## 故障 3 — 502 / 504 Bad Gateway (nginx → uvicorn)

### 现象

- 监控：`http_status{code="502"}` 上升
- 用户：登录后页面空白或 API 长时间无响应

### 排查

```bash
# 1. uvicorn 进程是否在容器内活着
kubectl -n nanobot-factory exec <pod> -- ps -ef | grep uvicorn
# 应有: /opt/venv/bin/uvicorn backend.server:app ...

# 2. 端口监听
kubectl -n nanobot-factory exec <pod> -- netstat -tlnp
# 应有 127.0.0.1:8001 + 0.0.0.0:8080

# 3. 直接打后端
kubectl -n nanobot-factory exec <pod> -- curl -fsS http://127.0.0.1:8001/healthz
```

### 修复 SOP

1. **uvicorn 启动失败**：
   - 看 logs (`kubectl logs <pod>` 找 stack trace)
   - 常见：模块导入失败、磁盘满、OOM killed
2. **uvicorn OOM**：
   - 减少 `UVICORN_WORKERS`（chart 默认 2，可降到 1）
   - 提高 memory limit (`values.yaml` → `resources.limits.memory`)
3. **nginx upstream 连接不上**：
   - 重启容器：`kubectl delete pod <pod>` (Deployment 会拉新)
4. **后端慢导致超时**：
   - `proxy_read_timeout` 已设 120s (`deploy/nginx/nginx.conf`)；ComfyUI 长任务调 300s

### 预防

- 给 pod 加 `resources.limits.memory` 触发 OOM kill 后再起新 pod
- 监控 `process_start_time_seconds` 抓异常重启

---

## 故障 4 — ComfyUI 任务卡死 / 队列堆积

### 现象

- 监控：`comfyui_queue_remaining` 持续 > 10
- 用户：渲染 5 分钟没进度

### 排查

```bash
# 1. ComfyUI 健康
kubectl -n nanobot-factory exec <pod> -- curl -fsS http://<comfyui-host>:8188/system_stats
# 或在 Pod 内
apk add curl && curl http://comfyui.omni.svc:8188/queue

# 2. 看 GPU
kubectl -n nanobot-factory exec <pod> -- nvidia-smi
# 若 GPU 被别的进程占 → OOM kill 或 OOM 等待
```

### 修复 SOP

1. **清 ComfyUI 队列**：
   ```bash
   # 调用 ComfyUI API 清空
   curl -X POST http://<comfyui-host>:8188/queue -H 'Content-Type: application/json' -d '{}'
   curl -X DELETE http://<comfyui-host>:8188/queue
   ```
2. **取消堆积的 nanobot batch**：
   ```bash
   curl -X POST https://nanobot.example.com/omni/comfy/render/<batch_id>/cancel \
        -H "X-API-Key: $KEY"
   ```
3. **重启 ComfyUI**（最后手段）：
   ```bash
   kubectl -n comfyui delete pod -l app=comfyui
   ```
4. **限流**：
   - 在 chart values 里设 `RATE_LIMIT_REQUESTS=50` 临时削峰
   - 或把渲染 endpoint 从 ingress 临时拿掉

### 预防

- 设 `MAX_CONCURRENT_BATCHES=4`，超过排队
- 监控 ComfyUI 队列长度 + GPU mem
- 每个 batch 加超时（默认 5min）

---

## 故障 5 — WebSocket 断连风暴

### 现象

- 用户反馈：实时画布不更新
- 服务端日志：`WebSocketDisconnect` 大量刷屏
- 监控：`ws_active_connections` 突降到 0

### 排查

```bash
# 1. 看 WS handler
kubectl -n nanobot-factory logs <pod> --tail=500 | grep -i websocket

# 2. 看 ingress 是否限流
kubectl -n nanobot-factory describe ingress
# 找 nginx.ingress.kubernetes.io/affinity 配置

# 3. 客户端 → 服务端连通性
kubectl -n nanobot-factory exec <pod> -- curl -i -N \
    -H "Connection: Upgrade" -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGVzdA==" \
    http://localhost:8080/ws/test
```

### 修复 SOP

1. **nginx-ingress 缓冲**：在 annotations 加：
   ```yaml
   nginx.ingress.kubernetes.io/proxy-buffering: "off"
   nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
   ```
2. **session affinity** 已在 chart 启用 (`affinity-mode: persistent`)；如丢失需检查 cookie 是否被浏览器拒。
3. **服务端**：增加 ping/pong 间隔（默认 30s）。如频率太高可调 60s。
4. **客户端**：在 `docs/user-guide.md` 提示用户不要长时间挂闲置；实现 reconnect-with-backoff。

### 预防

- WS 心跳监控：客户端 ping 失败率 > 5% 报警
- 单 pod 上限：5,000 连接（详见 `architecture.md`）

---

## 故障 6 — 数据库迁移 / 升级失败

### 现象

- 升级到 v1.1.0 后启动报错 `column 'xxx' does not exist`
- 监控：`/readyz` 数据库 check 失败

### 排查

```bash
# 看 alembic / 自研迁移脚本输出
kubectl -n nanobot-factory logs <pod> | grep -i migrat

# 看 schema 版本
kubectl -n nanobot-factory exec <pod> -- sqlite3 /app/data/nanobot.db \
    "SELECT * FROM schema_version ORDER BY version DESC LIMIT 5;"
```

### 修复 SOP

1. **回滚到上一个版本**：
   ```bash
   helm history nanobot-factory -n nanobot-factory
   helm rollback nanobot-factory <prev-revision> -n nanobot-factory
   ```
2. **手动补 schema**（如果不能回滚）：
   ```bash
   # 备份
   kubectl -n nanobot-factory exec <pod> -- cp /app/data/nanobot.db /app/data/nanobot.db.bak
   # 进入容器补字段
   kubectl -n nanobot-factory exec -it <pod> -- sh
   sqlite3 /app/data/nanobot.db "ALTER TABLE ..."
   ```
3. **触发再次迁移**：
   - 通常迁移脚本是启动时自动跑的；改代码确保 idempotent
   - 或手动 `python -m imdb.migrate`

### 预防

- 所有迁移脚本**先备份**再 ALTER（程序内自动）
- 灰度：先 1 个 replica 跑新版本 → 看日志 → 全量 rollout
- Chart 里 `strategy.rollingUpdate.maxSurge=1, maxUnavailable=0` 保证零停机

---

## 附录 A — 紧急关停

```bash
# 把整个 chart 缩到 0（不删 PVC）
kubectl -n nanobot-factory scale deploy/nanobot-factory --replicas=0

# 完全卸载（保留 PVC）
helm uninstall nanobot-factory -n nanobot-factory

# 完全清理（含 PVC — 数据丢失！）
helm uninstall nanobot-factory -n nanobot-factory
kubectl -n nanobot-factory delete pvc -l app.kubernetes.io/instance=nanobot-factory
kubectl delete namespace nanobot-factory
```

## 附录 B — 升级流程（标准）

1. 阅读 release notes / breaking changes
2. **备份**：PVC snapshot / `kubectl get pvc -o yaml > pvc-backup.yaml`
3. 改 `values.yaml` → `helm upgrade --dry-run` 先看 diff
4. staging 灰度：`helm upgrade ... --reuse-values --set image.tag=v1.1.0-rc1`
5. 验证：`curl /readyz`，看 metrics
6. 推 prod：`helm upgrade ... --set image.tag=v1.1.0` (production environment 需 manual approve)
7. 监控 30 min：`error rate`、`p99 latency`、`restart count`
8. 出问题 → `helm rollback`

## 附录 C — 联系升级

- 数据库迁移破坏 → 联系后端 owner（@db-lead）
- 镜像构建失败 → 联系 DevOps（@devops）
- ComfyUI / GPU 问题 → 联系 ML 平台（@ml-platform）

---

_最后更新：2026-06-21 — 适用版本 appVersion 1.0.0_