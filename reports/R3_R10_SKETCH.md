# R3: 前端 P0 - 导航死链与缺失渲染器

## 基线问题(AUDIT_REPORT.md 第六节)

10 个导航项缺 PAGE_RENDERERS 映射 → 点击显示占位符:
1. oss-storage
2. quality-center
3. model-manager
4. scheduler-center
5. audio-tools
6. enhanced-tools
7. crowd-platform
8. transfer-center
9. audit-logs
10. aesthetic-center

+ app.js 重复 PAGE_RENDERERS 条目
+ navigate() 双套 camelCase 转换冲突

## 10 轮作战图(R3-R10 骨架)

| 轮次 | 主题 | 范围 | worker 数 | 审计员 |
|------|------|------|----------|--------|
| R1 | 后端 P0 止血 | aesthetic 8 端点 + 3 崩溃端点 | 3 | 3 |
| R2 | 后端 P1 参数验证 | 272 端点 Pydantic 化 | 5+1 设计 | 3 |
| R3 | 前端 P0 导航+渲染 | 10 缺映射 + 重复条目 | 3 | 3 |
| R4 | 前端 P0 mock 数据 | business/stats/dashboard/team 等 | 4 | 3 |
| R5 | 前端 P1 死按钮 | settings/team/delivery/datasets 等 22 个 | 3 | 3 |
| R6 | 前端 P2 UX | 错误处理/loading/empty/权限/无障碍 | 2 | 3 |
| R7 | 后端 P2 性能与可观测 | 慢查询/缓存/日志/metrics | 2 | 3 |
| R8 | E2E 端到端联调 | 登录→标注→审核→交付 完整链路 | 2 | 3 |
| R9 | 安全与合规 | OWASP Top10/越权/认证/CSRF | 2 | 3 |
| R10 | 商业化打磨+压测+文档 | SLA/压测/部署/文档/培训 | 3 | 3 |

每一轮的标准结构:
- 1-5 个 worker (按子系统或功能拆分)
- 1 个依赖链上的设计任务(契约)
- 3 个 AI 审计员 (业务正确性 / 安全 / 质量)
- 1 个 final gate

## 启动条件

每一轮 launch 前:
- 上一轮 final gate PASS
- 读上一轮所有 R*_final_gate.md 报告
- 把 R*_*.md 中的"必修复项"纳入下一轮 prompt
