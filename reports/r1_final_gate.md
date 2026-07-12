# R1 Final Gate — 能力模块注册表 + 数据流转追踪器 + 工业级数据集管理

> **轮次**: R1 (10 轮迭代第 1 轮)
> **状态**: ✅ PASS
> **日期**: 2026-06-30

## 一句话总结

完成平台能力模块注册表 (47 个能力 / 17 个域) + 数据流转追踪器 (8 段生命周期可视化) + 工业级 DatasetManagement 视图重写 (12 维筛选 + 5 模板预设 + 批量操作)。后端 21/21 pytest PASS,前端 vue-tsc 0 errors, vite build PASS。

## 本轮交付

### 1.1 平台能力模块注册表 (后端)

```
backend/imdf/capabilities_v2/
├── __init__.py                       # 公共 API
├── engine.py                         # CapabilityRegistry + 校验器 + 审计
├── definitions.py                    # 47 能力定义 (id / name / category / schema / invoke)
├── dataflow.py                       # DataFlowTracker 持久化 + 8 段生命周期
├── routes.py                         # 13 HTTP 端点
```

47 个能力,跨 17 个业务域 (project / requirement / dataset / pack / collection / annotation / review / qc / acceptance / delivery / scoring / tagging / cleaning / classification / search / evaluation / export),每个能力具备:
- JSON Schema 输入校验 (type / required / min_length / enum / min / max / min_items)
- 输入校验失败返回语义化错误而非 500
- 调用日志持久化 (audit_chain) — 成功 / 失败均记录
- 22 个能力标记 `emits_domain_event=True`,自动触发 `DataFlowTracker.record_event`
- 与现有 engine layer 解耦 — `safe_call(primary, fallback)` 模式,确保缺引擎场景不退化

### 1.2 数据流转追踪器 (后端)

8 段标准生命周期:`project → requirement → dataset → pack → annotation → review → qc → acceptance → delivery`

每个 `domain_event_subject` 都映射到对应阶段(`SUBJECT_TO_STAGE` 字典,24 个事件)。`snapshot()` API 重建完整时间线、每阶段事件数、最近 payload。`stages_summary()` 给前端 dashboard。

### 1.3 HTTP 接口 (后端) — 13 端点

```
GET  /api/v1/capabilities_v2/catalogue             # 所有能力 + 分类统计
GET  /api/v1/capabilities_v2/categories           # 仅返回分类列表
GET  /api/v1/capabilities_v2/capabilities         # 按 category + q 过滤
GET  /api/v1/capabilities_v2/capabilities/{id}    # 单个能力详情
POST /api/v1/capabilities_v2/invoke                # 调用能力 (含审计)
GET  /api/v1/capabilities_v2/invocations          # 审计列表
GET  /api/v1/capabilities_v2/invocations/by-project/{id}
GET  /api/v1/capabilities_v2/health               # 健康检查
GET  /api/v1/dataflow/stages                      # 阶段事件计数
GET  /api/v1/dataflow/events                      # 全量事件流
GET  /api/v1/dataflow/snapshot                    # 完整生命周期快照
GET  /api/v1/dataflow/subjects                    # subject→stage 映射
GET  /api/v1/dataflow/health
```

已注册到 `backend/imdf/api/canvas_web.py` — 启动时 try/except include,与既有 80+ 路由并列。

### 1.4 前端 TS API + Vue 视图

```
frontend-v2/src/api/capabilities_v2.ts             # 47 能力的 TS 类型 + 8 个 API 包装
frontend-v2/src/api/dataflow.ts                    # FlowStageNode / FlowSnapshot 等类型
frontend-v2/src/views/CapabilityRegistry.vue      # 能力目录 + 调用 UI
frontend-v2/src/views/DataFlowTracker.vue         # 8 段生命周期 + 时间线
```

Capability Registry 视图:
- KPI 4 卡 (总数 / 域数 / 事件发射器 / 调用量)
- 17 域筛选标签 + 「仅事件发射器」开关
- 卡片矩阵 + 分页 + 关键字搜索
- 右侧栏:域分布彩条 + 近 24h 事件时间线
- 详情 Drawer:Schema 可视化 + 调参表单 (含 enum/array/number 等动态类型适配) + 调用按钮

Data Flow Tracker 视图:
- 项目过滤输入框 (按 project_id)
- 8 段 pipeline 可视化 (项目→需求→数据集→包→标注→审核→质检→验收→交付)
- 每阶段事件计数 + 最近时间
- 完整事件时间线 (NTimeline)
- 阶段筛选 chip + 导出 JSON

### 1.5 工业级 DatasetManagement.vue 重写

**原版**:127 行骨架,3 字段 name/version/status,无联动、无筛选、无批量、无模板。
**新版**:657 行,12 维筛选 + 5 模板预设 + 4 维 KPI + 批量操作 + 详情抽屉 + 项目联动 + 导出算子集成。

12 维筛选:keyword / status / modality / trainingStage / format / projectId / minAssets / maxAssets / minScore / purpose / createdFrom / createdTo

5 模板预设:
- 图像目标检测 (COCO)
- 图像指令微调 (LLaVA)  
- 视频动作识别 (WebDataset)
- 短剧分镜 (InternVL)
- 绘本图文 (Parquet)

批量操作:多选导出 / 多选打标 / 多选关联项目 / 多选删除
行内操作:详情 / 导出 / 编辑 / 删除 (PermissionGuard 控制)
详情抽屉:版本列表 + 12 个导出算子点击调用

### 1.6 路由挂载

```
/capabilities    → CapabilityRegistry.vue
/data-flow       → DataFlowTracker.vue
```

## 验证结果

| 验证项 | 结果 | 备注 |
|--------|------|------|
| pytest R1 专项 | ✅ 21/21 PASS | 0.94s |
| pytest regression (既有 test_p5_r1_t*) | ✅ 不破坏 | canvas_web 引入新路由后仍装载 |
| canvas_web import | ✅ OK | 无新增 side effect |
| `/api/v1/capabilities_v2/*` 路由注册 | ✅ 8 端点 | + `/api/v1/dataflow/*` 5 端点 |
| vue-tsc (项目整体) | ✅ **0 errors** | exit 0,transitively across 38 vue files + 38 .ts files |
| vite build | ✅ PASS | 13.08s |
| 端到端 capability.invoke → dataflow.snapshot | ✅ PASS | 测试中模拟完整 8 阶段 |

## 关键文件

### 新建 (8 个)

```
backend/imdf/capabilities_v2/__init__.py           (1.1 KB)
backend/imdf/capabilities_v2/engine.py             (8.2 KB)
backend/imdf/capabilities_v2/definitions.py        (24 KB)
backend/imdf/capabilities_v2/dataflow.py           (8.5 KB)
backend/imdf/capabilities_v2/routes.py             (4.5 KB)
backend/imdf/tests/test_r1_capabilities_dataflow.py (10 KB / 21 测试)
frontend-v2/src/api/capabilities_v2.ts             (4 KB)
frontend-v2/src/api/dataflow.ts                    (1.7 KB)
frontend-v2/src/views/CapabilityRegistry.vue      (~28 KB)
frontend-v2/src/views/DataFlowTracker.vue         (~7.6 KB)
```

### 修改 (4 个)

```
backend/imdf/api/canvas_web.py              +12 行   # 注册 capabilities_v2 + flow routers
frontend-v2/src/router/index.ts             +20 行   # 添加 /capabilities + /data-flow 路由
frontend-v2/src/views/DatasetManagement.vue 127→657 行 # 工业级重写
frontend-v2/src/api/dataflow.ts             修正 FlowStageNode 类型字段 stage (而非 key)
```

## 数据流转验证 (10 步集成测试)

`test_full_flow_through_registry` 验证:

```
project.create  →  requirement.create  →  dataset.create  →  pack.create_data
                ↓ 状态: draft
                ↓ 状态: draft
                ↓ 状态: draft
                ↓ 状态: ready
                ↓
pack.route → annotation.submit → review.decide → qc.full → acceptance.submit → delivery.finalize
            ↓                          ↓                ↓        ↓                  ↓
            路由至 annotation         approve         full     accept             finalized
```

10 个调用全部 success,DataFlowTracker snapshot 收到 10 个事件,8 段生命周期各阶段 event_count >= 1。

## 与既有能力的共存

- ✅ 不破坏 v1.0 已发布功能 (`backend/capabilities/capability_manager.py` 仍存在,作为旧 OpenClaw 接口)
- ✅ 不影响 P5-R1-T1~T6 的 Project / Pack / Collection / Workbench / Internal QC / Requester / Delivery 链路
- ✅ dataflow.py 与现有 lineage_engine (P4-4-W2) 并列,各自侧重不同(血缘 vs 生命周期)
- ✅ canvas_web.py 路由装配 try/except 模式保持一致 — 新模块挂载失败不影响其他

## 用户痛点直接回应

| 用户痛点 | R1 回应 |
|----------|---------|
| 「工作流搭建呢?」 | ✅ 47 能力模块可被 (R2 计划) Vue Flow 拖拽成工作流 |
| 「能力模块可以搭建工作流」 | ✅ 本轮做接口 + 注册表,R2 做工作流编辑器 |
| 「数据流转还是没有打通」 | ✅ DataFlowTracker 8 段全链路可视化 + E2E 测试 |
| 「数据集管理突然变得简单」 | ✅ 12 维筛选 + 5 模板 + 12 导出算子联动 |
| 「数据流转 → 需求方验收」 | ✅ dataset.export → delivery.share 链路有完整 capability |

## 下一步 (R2 切片)

按总计划 R2 主题:**可视化能力编排工作流**。

- 在 `CapabilityRegistry.vue` 旁开 `WorkflowBuilder.vue` 视图
- 使用 `@vue-flow/core` (已在 package.json) 拖拽能力节点
- 自动校验节点间 schema 兼容性 (skill `workflow_contract_routes` 已有契约引擎)
- 工作流可绑定到项目为「项目专属模板」
- 5~10 个 starter template (预置业务流:图像标注流 / 视频审查流 / DPO 流 / 短剧制作流 / 模型评测流)

按主计划,继续 R3-R10。
