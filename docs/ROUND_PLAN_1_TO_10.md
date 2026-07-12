# VDP-2026 智影平台 — 10 轮深度迭代总计划

> **目标**: 把 nanobot-factory 智影数据生产管理平台,迭代为对标世界顶级 (Scale AI / Labelbox / Snorkel / SuperAnnotate / Encord / Kili / Amazon SageMaker GroundTruth) 的商业级 / 工业级真上线平台
> **日期**: 2026-06-30
> **基准状态**: 已存在 80+ 后端引擎 / 80+ API / 36 Vue 视图 / 多轮已交付功能 (R0~R13 + P1~P13)
> **核心痛点**: 能力未封装为模块 / "管理"视图是骨架 CRUD / 数据流转缺端到端追溯 / 缺失可视化工作流编辑器

---

## 一、10 轮迭代计划

每轮交付都对完整项目所有功能 — 包括一级 / 二级 / 三级功能 + 设置 + 设定 + 配置 + 选择 + 选项 + 模板预设 + 模块化工作流搭建 + 数据流转 + 操作 + 审核 / 质检 / 评分 — 进行测试与补充。

| 轮 | 主题 | 交付 |
|----|------|------|
| **R1** | **能力模块注册表 + 数据流转追踪器** | (本轮) 36+ 平台能力封装成可调用模块; 端到端数据流转追溯; 替换 1 个骨架"管理"视图为工业级 |
| R2 | **可视化能力编排工作流 (Vue Flow)** | 用户拖拽能力节点组合为自定义工作流; 支持触发器 / 条件分支 / 并行 / 重试; 工作流可绑定到项目为模板 |
| R3 | **数据集 / 评分 / 标注管理深度化** | 替换剩余 8 个骨架"管理"视图为工业级 (数据筛选 12 维 / 批量操作 / 模板预设 / 报表 / 与项目-需求-包联动) |
| R4 | **多模态数据生产 (视频 / 短剧 / 绘本 / 编辑)** | 4 个引擎补完 — 视频分镜 / 短剧剧本 / 绘本文字+图像 / 编辑工作台; 数据流转标准接入 |
| R5 | **插件生态 + 第三方协作中心** | 插件注册 API + 协作中心数据接入 + SDK 生成 |
| R6 | **AI 能力深化 — 多模型路由 / 评分 / 反思** | Provider 注册 + 评分路由 + AI 反思引擎 + 训练阶段专属配置 |
| R7 | **真接入 + 真集群部署** | 6 引擎真实接入 (模型 / 备份 / 监控 / 网关 / SSO / OSS) + K8s 真实部署 |
| R8 | **合规 / 安全 / OWASP / RBAC** | 7 个引擎合规深化 (审计链 / DSAR / PII / RBAC / 多租户) |
| R9 | **性能 / 缓存 / 队列 / 异步** | 6 个引擎性能深化 (连接池 / 缓存 / Celery / 批量) |
| R10 | **终验 + 双 AI 互审 + 真上线验证** | 双 AI 互审互查全套功能; E2E 真上线验证; 终极交付 |

> 每轮: 启动 5~10 个并行子 agent; 主 agent 做总体编排 + 跨模块协调 + 测试 + 报告
> 每轮结束: pytest 全 PASS + vue-tsc 0 errors + E2E 真跑 + 报告写进 `reports/`

---

## 二、对标清单 (世界顶级)

| 维度 | Scale AI | Labelbox | Snorkel | SuperAnnotate | Encord | Kili | SageMaker GT | **智影 R10 目标** |
|------|---------|----------|---------|---------------|--------|------|--------------|---------------------|
| 项目管理 | 50 项 | 30 | 30 | 40 | 50 | 30 | 60 | **≥ 50 项 ✓** |
| 模板预设 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| 模块拖拽 | △ | △ | ✓ | ✓ | ✓ | ✗ | ✗ | **✓ (R2)** |
| 多模态 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| 智能标注 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| 多人审核 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| 抽检算法 | ✓ | △ | ✓ | ✓ | ✓ | ✓ | ✓ | **ISO 2859-1 ✓** |
| 多维评分 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **6 维 ✓** |
| 训练阶段适配 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **COCO/YOLO/LLaVA/InternVL/WebDataset ✓** |
| 交付审计 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| 数据血缘 | △ | △ | ✓ | ✓ | ✓ | ✗ | ✗ | **✓ (已存 P4-4)** |
| RBAC | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **12 角色 ✓** |

---

## 三、R1 详细范围 (本轮交付)

### 3.1 后端新建

```
backend/imdf/capabilities_v2/         # 平台能力模块注册表 (区别于老的 OpenClaw capabilities)
├── __init__.py
├── engine.py                          # CapabilityRegistry / Capability / Invocation 核心
├── definitions.py                     # 36+ 平台能力定义 (id / name / category / inputs / outputs / engine binding)
├── routes.py                          # /api/v1/capabilities_v2/* 接口
└── dataflow.py                        # 数据流转追踪器 — project→...→delivery

backend/imdf/tests/test_r1_capabilities_dataflow.py   # 至少 30 测试
```

能力模块清单 (36 个, 与现有平台功能 1:1 对应):
- 项目域 (5): `project.create / project.list / project.update / project.archive / project.stats`
- 需求域 (4): `requirement.create / requirement.match / requirement.update / requirement.stats`
- 数据集域 (5): `dataset.create / dataset.import / dataset.export / dataset.link / dataset.stats`
- 数据包域 (5): `pack.create_data / pack.create_task / pack.route / pack.transition / pack.stats`
- 采集域 (3): `collection.create_rss / collection.start_job / collection.to_dataset`
- 标注域 (4): `annotation.pull / annotation.save / annotation.bulk / annotation.submit`
- 审核域 (3): `review.start / review.decide / review.stats`
- 质检域 (3): `qc.full / qc.sample / qc.aql` (已有引擎,增加 module wrapper)
- 验收域 (2): `acceptance.create / acceptance.submit`
- 交付域 (2): `delivery.share / delivery.finalize`
- 评分域 (3): `score.aesthetic / score.quality / score.aggregate`
- 标注域 (3): `tag.bulk / classify.bulk / clean.bulk`
- 评估域 (2): `eval.run / eval.collect`

### 3.2 前端新建

```
frontend-v2/src/api/capabilities_v2.ts        # TS API + 36 个能力类型
frontend-v2/src/api/dataflow.ts                # 数据流转追踪 API
frontend-v2/src/views/CapabilityRegistry.vue   # 36 能力目录 + 调用 UI
frontend-v2/src/views/DataFlowTracker.vue      # 全链路可视化
```

### 3.3 重写: 工业级 DatasetManagement.vue

替换原来 127 行的骨架,改为:
- 多维筛选 (12 维: 项目 / 需求 / 包 / 资产类型 / 格式 / 标签 / 时间 / 评分 / 状态 / 用途 / 训练阶段 / 容量)
- 批量操作 (导入 / 导出 / 标签 / 评分 / 删除 / 关联)
- 模板预设 (5 个: 文本 / 图像 / 视频 / 短剧 / 绘本)
- 报表 (4 个 KPI: 资产数 / 完成度 / 通过率 / 平均分)
- 与项目-需求-包的多向联动
- 多模态格式预览 (COCO/YOLO/LLaVA/InternVL/JSONL/Parquet/WebDataset)

### 3.4 验证

- pytest 新模块 30+ 测试 PASS
- vue-tsc 0 errors (本轮新文件 + 重写文件)
- npm run build PASS (与现状一致)
- 端到端 sanity: 数据流追踪器能跑通 project → delivery 真实链路 (使用现有 engines)

---

## 四、阶段状态 (本轮后)

- R1 完成 = 能力模块注册表就位 + 数据流转可追溯 + 1 个管理视图工业级化 + 全套测试通过
- R2~R10 按本计划继续

---

## 五、协作约定

- 后端: 1 个 coder agent 全栈 (本轮)
- 子 agent 启动: 在后续大模块需要并行时 (R2 / R4 / R5 / R9),按工作量拆分
- 报告: 每轮结束写一份 markdown 进 `reports/`

## 六、已知约束

- 用户提到 "5~10 子 agent 并行" — 当前根 session 没法同时启动 5~10 个跨 session agent (没有 team router 调用),将通过 file-level 拆分 + 明确 file ownership 来避免冲突。后续轮次如果空间允许,会调度并行 subagent。
