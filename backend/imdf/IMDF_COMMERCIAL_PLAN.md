# IMDF 商用化修复完善计划 v1.0

基于全网调研(Scale AI/Labelbox/CVAT/FastAPI最佳实践)的本项目差距分析结果。

---

## 阶段优先级划分

### P0 — 基础设施（必须优先做，不改这些不能上线）
1. **PostgreSQL迁移** — SQLite→PostgreSQL + Alembic迁移脚本
2. **JWT认证加固** — argon2密码哈希 + refresh token + token黑名单
3. **API版本控制** — 所有路由前缀改为 `/api/v1/`
4. **HTTPS + CORS** — Nginx反代 + 证书 + CORS策略
5. **Rate Limiting** — slowapi + 内存/Redis限流
6. **健康检查** — `/health` + `/ready` 端点
7. **Graceful Shutdown** — 信号处理 + 正在执行的任务恢复

### P1 — 工程化（架构升级，可运维）
8. **异步任务队列** — Celery + Redis，所有耗时操作异步化
9. **结构化日志** — structlog + request ID链路追踪
10. **错误追踪** — 统一异常处理器 + Sentry接入
11. **监控指标** — Prometheus metrics（QPS/延迟/错误率/内存/并发）
12. **Docker多阶段构建** — 生产镜像从350MB降到100MB以下
13. **集成测试** — pytest + httpx.AsyncClient + 覆盖率目标70%+

### P2 — 功能完善（补齐商用功能）
14. **对象存储** — MinIO接入，文件上传/下载走预签名URL
15. **前端重写** — React/Vue + 路由 + 独立代码库
16. **数据隔离** — 多租户数据行级隔离
17. **审计日志** — 所有API写操作记录操作人/时间/内容
18. **数据生产管线编排** — DAG工作流引擎（引擎链可视化编排）
19. **运营看板** — 生产统计/质量趋势/人员效率

### P3 — 差异化（商业竞争力）
20. **AI预标注** — 接入SAM/CLIP/YOLO自动标注
21. **计费/配额** — 按API调用量/存储量/用户数计费
22. **Python SDK** — pip install imdf
23. **数据版本控制增强** — 分支/合并/回滚
24. **数据备份恢复** — 自动定期dump + 恢复流程

---

## 实施顺序

P0 → P1 → (P2 前3项) → P0加固 → P2剩余 → P3

每个阶段完成后必须通过双AI审核 + 端到端测试。
