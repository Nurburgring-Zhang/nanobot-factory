# P5 — 智影 (ZhiYing) 商业级数据生产平台 10 轮深度迭代规划

> **项目**: D:\Hermes\生产平台\nanobot-factory (智影 ZhiYing · 智影数据工场)
> **规划时间**: 2026-06-28
> **执行模式**: 10 轮迭代 (P5-R1 ~ P5-R10),每轮 5-7 个 worker agent 并行 + 双 AI 互审互查 (verifier + auditor)
> **基线**: R0-R10.5 + P1-P4 (14 阶段, 194 算子 / 12 微服务 / 30+ view)
> **诊断报告**: `reports/p5_diagnostic_2026_06_28/*.json` (5 份)

---

## 0. 基线诊断结论 (2026-06-28)

### 0.1 五份诊断报告
| 模块 | 报告文件 | 大小 | 核心结论 |
|------|----------|------|----------|
| Dataset (数据集) | `dataset_diagnostic.json` | 32 KB | 后端 80+ 端点,前端只用 ≤3 个 |
| Annotation (标注) | `annotation_workbench_diagnosis.json` | 23 KB | 引擎 790 行满血,前端 0 画布 |
| Review (审核) | `review_center_diagnosis.json` | 37 KB | 7 端点只用 3 个,且 2 个只取聚合 |
| Scoring/Evaluation (评分/AI) | (内嵌在 5 份内) | - | 前端路径错位 + schema 错位 (BROKEN) |
| 数据流转链路 | `data_flow_linkage_diagnosis.json` | 38 KB | 11 处断裂, 8 个 view 缺失, 5 个 service 缺失 |
| 能力模块化+工作流 | `capability_workflow_diagnosis.json` | 37 KB | 60 分, 缺动态表单/版本/调度/共享 |

### 0.2 五大核心问题 (用户痛点)
1. **5 个核心模块被简化**:Dataset / Annotation / Review / Scoring / Tasks 都被砍到只剩 KPI+表格骨架
2. **数据流转链 11 处断裂**:ProjectCenter / RequirementCenter / PackManager / Collection / Workbench / InternalQC / RequesterAccept / Delivery 8 个 view 缺失 + 5 个 service 缺失
3. **能力模块化和工作流搭建不到位**:141 capability 静态注册 + 47 节点 + 186 算子,但 execute 全是 stub,VisualEditor 右栏是 JSON textarea
4. **双 AI 互审互查未制度化**:需要每轮固定 1 verifier + 1 auditor
5. **10 轮迭代的覆盖深度**:每轮都要覆盖"5 核心模块 + 数据流转 + 能力模块化 + 工作流搭建"全栈

### 0.3 关键发现
- **annotation_system.py (851 行) 完整标注管理系统没有任何路由引用** — 最大的浪费
- **VisualEditor.vue (557 行) 完整对标 ComfyUI 但右栏是 JSON textarea** — 缺动态表单
- **requirement_engine.py (673 行) 业务 Task 拆解完整,前端 0 入口** — 链路断在第一步
- **transfer_engine.py (523 行) HMAC 分享完整,前端 0 入口** — 交付断在最后一步

---

## 1. 10 轮迭代路线图 (P5-R1 ~ P5-R10)

### 总体节奏
| 轮次 | 主题 | 目标 | 关键交付 | Worker 数 |
|------|------|------|----------|-----------|
| **R1** | 链路打通 P0 | 数据流转链 11 处断裂修复 7 处 | 3 view + 3 service + 路径修复 | 6 |
| **R2** | 链路打通 P1 + 标注画布 | 链路全通 + AnnotationWorkbench | 4 view + 1 真画布 | 6 |
| **R3** | 5 核心模块 P0 补全 | Dataset/Annotation/Review/Scoring P0 | 4 view P0 补全 + 后端 | 5 |
| **R4** | 5 核心模块 P1 补全 | 标签 taxonomy / IAA / 黄金题 / 嵌入可视化 | 5 view P1 补全 | 5 |
| **R5** | 能力模块化补全 | 141 capability 真接 + 动态表单 | Capability SDK + UI | 5 |
| **R6** | 工作流搭建 P0 | 动态表单 + 调度 + 版本 | VisualEditor 大改 | 5 |
| **R7** | 工作流搭建 P1 | 调试 / 共享 / 自定义节点 | + 模板市场 | 5 |
| **R8** | 端到端 E2E + 性能 | Playwright 全链路 + Locust 1000 并发 | E2E + 性能报告 | 4 |
| **R9** | 商业化深度 | 计费 / 合同 / 客户 / SLA | P4-10 商业化补全 | 4 |
| **R10** | 全面验证 + 文档 | 双 AI 互审 + 30 文档更新 | 最终交付报告 | 4 |

每轮:5-7 个 worker 并行 (coder),1 个 verifier 验证,1 个 auditor 审计 → **双 AI 互审互查互监督**

---

## 2. Round 1 详细规划 (P5-R1)

### 主题: **数据流转链路打通 P0**
**目标**: 把项目→需求→任务排期→数据包/任务包→数据集→标注→审核→质检→需求方→交付的链路打通到 P0 程度

### 2.1 Round 1 的 6 个并行 Worker

| Worker | 任务 ID | 负责范围 | 预计工时 | 验收 |
|--------|---------|----------|----------|------|
| **W1** | p5-r1-t1 | ProjectCenter (前端 + 后端 project_engine + project_routes) | 1.5-2 天 | View + CRUD + 成员管理 + 3 测试 |
| **W2** | p5-r1-t2 | RequirementCenter (前端 + 后端补 project_id + 任务拆解 UI) | 1.5-2 天 | View + 拆解按钮 + 状态机 + 3 测试 |
| **W3** | p5-r1-t3 | PackManager + CollectionCenter (前端 + 后端 pack_engine + collection UI 化) | 2-2.5 天 | 2 view + pack 模型 + 采集流 + 4 测试 |
| **W4** | p5-r1-t4 | AnnotationWorkbench 真画布 (前端 + 后端 workbench_engine) | 2-2.5 天 | 画布 + 工具栏 + 提交 + 4 测试 |
| **W5** | p5-r1-t5 | Review/Scoring/Evaluation 路径修复 + 5 核心模块 P0 quick wins | 1-1.5 天 | 路径对 + 按钮接 + 3 测试 |
| **W6** | p5-r1-t6 | InternalQC + RequesterAccept + Delivery (前后端) | 2-2.5 天 | 3 view + 3 service + 4 测试 |

### 2.2 验收标准 (Pass/FAIL 量化指标)
每轮结束后必须满足:
1. **功能完整度**: 修复断点数 ≥ 5/11,R1 目标 ≥ 7/11
2. **代码质量**: vue-tsc 0 error + 后端 pytest 0 fail + 至少 1 个 E2E 用例通过
3. **前后端连通**: 6 个新 view 至少 4 个能真实调通后端 (非 mock)
4. **互审通过**: verifier PASS + auditor PASS 双签
5. **文档**: Round 1 交付报告 1 篇 (CHANGELOG + 新增文件 + 端到端演示截图)

### 2.3 Round 1 后状态
- 数据流转链 11 处断裂中修复 7 处
- 8 个缺失 view 中新建 8 个
- 5 个缺失 service 中新建 5 个
- 5 核心模块路径错误全部修复
- 标注工作台从"表格"变成"真画布"
- Round 1 交付报告 + Round 2 详细规划

---

## 3. Round 2-10 详细规划 (概述)

### Round 2 (W6): 链路打通 P1 + Workbench
- 4 view 修补 (ProjectCenter 详情/时间线, RequirementCenter 验收, PackManager 派发/路由, CollectionCenter 实时监控)
- AnnotationWorkbench: 多人协同 / 标签 taxonomy / 智能辅助 (SAM prelabel)
- 后端: annotation_system.py 851 行真正接入路由
- 验收: 链路 11/11 全部通, 标注从"单人单图"到"多人协同"

### Round 3 (W5): 5 核心模块 P0
- Dataset: 样本浏览器 / 标签 taxonomy / 标签分布 / train-val-test 拆分 / 12 export 算子全接
- Annotation: IAA 看板 / 任务分配 / 任务锁定 / 黄金题
- Review: 抽检/AQL / 多级 / 审核员绩效 / 黄金题
- Scoring: 维度雷达图 / 异步任务 / 真实算子全接 / 8 metric
- Tasks: 任务日历 / 排期甘特图 / 跨源聚合
- 验收: 5 view 全部 P0 完整, 对标 Roboflow / Encord Active 70%

### Round 4 (W5): 5 核心模块 P1
- Dataset: 嵌入可视化 (UMAP/t-SNE) / 重复检测 / 数据漂移
- Annotation: 视频标注 / 3D 标注 / 行业 schema 切换
- Review: 共识/仲裁/申诉 / 盲审 / SLA
- Scoring: 阈值规则引擎 / 主动学习采样 / 错误分析
- Tasks: 任务依赖图 / 自动派发策略
- 验收: 5 view 全部 P1 完整, 对标 Scale AI / Labelbox 60%

### Round 5 (W5): 能力模块化补全
- 141 capability 真实 execute (OpenClaw / MCP / Browser / Search / Monitor / AI 31 类型)
- Capability SDK + 文档
- 能力模块市场 (评分/收藏/最近使用/推荐)
- Plugin Manager 动态加载
- 验收: capability 真接通, 对标 AutoGen / CrewAI 80%

### Round 6 (W5): 工作流搭建 P0
- VisualEditor 右栏 JSON textarea 替换为动态表单 (基于 operator input_schema)
- 工作流版本控制 / fork / diff
- 调度器 (cron / webhook / event)
- 自定义节点 (Python / JS / HTTP / Function)
- 验收: 对标 n8n / Flowise / Langflow 70%

### Round 7 (W5): 工作流搭建 P1
- 节点级调试 (单步/断点/重放/输入注入)
- 节点级日志/IO inspector/重试
- 工作流共享 + 团队 + 公开市场
- 模板市场 (评分/收藏/fork)
- 验收: 对标 ComfyUI 80%

### Round 8 (W4): 端到端 E2E + 性能
- Playwright 全链路 11 步 E2E
- Locust 1000 并发
- 性能调优 (慢查询/缓存/连接池)
- 安全渗透测试 (OWASP Top 10)
- 验收: E2E 全通 + 1000 并发 SLA OK

### Round 9 (W4): 商业化深度
- 计费 (5 套餐 + 12 限额 + Stripe/Alipay/WeChat)
- 合同 (PDF 模板 + 签字 + 存档)
- 发票 (国标格式 + 申领 + 核验)
- CRM + 工单 (4 SLA + 自动派单)
- 验收: 商业闭环

### Round 10 (W4): 全面验证 + 文档
- 双 AI 互审互查 (verifier + auditor)
- 30 文档更新 (架构/API/部署/安全/用户指南/Runbook)
- 性能/安全/合规/可观测性综合报告
- 最终交付报告 (Round 1-10 累计)
- 验收: 商用级交付

---

## 4. 双 AI 互审互查互监督机制 (每轮)

```
Round N 启动
    ↓
6 worker 并行 (coder)
    ↓
每个 worker 完成后
    ↓
[verifier] 验证 (read-only, 跑测试/查代码/造用例)
    ↓ PASS / FAIL
[auditor] 审计 (独立审查, 关注架构/安全/可维护性)
    ↓ PASS / FAIL
[orchestrator] 决定 accept/reject
    ↓
下一轮准备
```

**双 AI 互审互查**:
- verifier 关注"是否真的工作" (跑测试,造边界用例, 反向攻击)
- auditor 关注"是否真的对" (代码质量, 架构一致, 安全合规, 性能)
- 两者**不可同时通过同一个 worker 的产出** — 必须独立判断
- 任意一个 FAIL → 退回 worker 修复, 重新进入验证循环

---

## 5. Round 1 启动 (本轮)

### 5.1 启动 plan
- plan 名称: "P5-R1 智影平台链路打通 P0"
- 6 个并行 task (T1-T6), max_concurrency 6
- 每个 task: coder (impl) + verifier (verify) + auditor (audit) 三签
- 1 个 final integration gate

### 5.2 预计时间
- Round 1 总耗时: 2-3 天 (6 worker 并行 + 双 AI 互审)
- 后续 9 轮每轮 2-3 天
- 10 轮累计: 20-30 天

### 5.3 退出条件
每轮结束时:
- 6 worker 全部 PASS
- verifier 全部 PASS
- auditor 全部 PASS
- integration gate PASS
- 交付报告生成
- 下一轮 plan 文件就绪

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| Worker 间文件冲突 | 中 | 每个 worker 限定目录, 通过接口契约隔离 |
| 前后端 API 契约不一致 | 中 | 先写 OpenAPI schema, worker 严格按 schema |
| 引擎代码改动破坏现有 | 高 | 严格写新文件, 不修改已通过测试的旧文件 |
| 性能/并发问题 | 中 | Round 8 统一处理, 之前以功能完整为先 |
| 用户临时变更 | - | steer 命令实时调整 |
| Plan 超时 | - | extend-timeout 提前 5 分钟 |

---

**负责人**: Mavis (root orchestrator)
**第一轮计划**: 见 `plans/p5_r1_plan.yaml`
**状态**: 启动中
