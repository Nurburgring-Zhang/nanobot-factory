# R2 Final Gate — 可视化能力工作流搭建器

> **轮次**: R2 (10 轮迭代第 2 轮)
> **状态**: ✅ PASS
> **日期**: 2026-06-30

## 一句话总结

完成可视化工作流搭建器 (Vue Flow 拖拽) — 用户可拖拽 R1 的 47 个能力模块组合成工作流,自动拓扑排序 + 变量引用 + 6 个 starter 模板一键加载。前端 vue-tsc 0 errors, vite build PASS, 后端 R1+R2 共 38/38 pytest PASS。

## 本轮交付

### 2.1 后端工作流引擎 (新)

```
backend/imdf/workflow_builder/
├── __init__.py                       # 公共 API
├── engine.py                         # WorkflowEngine + topo-sort + 变量替换 + 持久化
├── routes.py                         # 11 HTTP 端点
```

核心能力:
- **持久化**:SQLite + WAL,workflows + workflow_runs 2 张表,任意重启可恢复
- **拓扑排序** `_topo_sort(wf)` — DFS 风格,环检测明确报 `ValueError`
- **变量替换** `${node_id.output_key}` — 支持整字段引用、嵌入字符串 (`prefix-${n.x}-suffix`)、未解析回退 (保 `${...}` 不替换)
- **执行引擎** `WorkflowEngine.run_workflow(wf)` — 拓扑序调用 `CapabilityRegistry.invoke`,输出自动传给下游 (setdefault),失败即时中断
- **6 starter 模板** `build_starter_templates()`:
  1. 图像标注生产流 (7 节点) — 项目→需求→数据集→包→标注→审核→QC
  2. 视频审查流 (6 节点) — RSS→采集→数据集→包→评分→审核
  3. DPO 偏好对生产流 (7 节点) — 项目→需求→数据集→批量标注→打标→AQL 抽检→验收
  4. 短剧分镜制作流 (5 节点) — 项目→数据集→拉标→提交→多模态导出
  5. 模型评测流 (4 节点) — 数据集→评测→聚合→导出
  6. AI 预标注 + 人审流 (7 节点) — 项目→数据集→批量分类→review→sample QC→需求方验收→交付

引擎启动时自动 `save_workflow(tpl)` 注入 6 个模板,首次访问 `/api/v1/workflow_builder/templates` 即可使用。

### 2.2 HTTP 接口 (11 端点)

```
GET    /api/v1/workflow_builder/templates                 # 6 个 starter
POST   /api/v1/workflow_builder/templates/reload          # 强制重载
GET    /api/v1/workflow_builder/workflows                 # 列出 (含 starter)
POST   /api/v1/workflow_builder/workflows                 # 保存 / upsert
GET    /api/v1/workflow_builder/workflows/{id}
DELETE /api/v1/workflow_builder/workflows/{id}
POST   /api/v1/workflow_builder/workflows/{id}/run        # 同步执行
GET    /api/v1/workflow_builder/runs                      # 最近运行
GET    /api/v1/workflow_builder/runs/{id}
GET    /api/v1/workflow_builder/health
```

集成到 `backend/imdf/api/canvas_web.py`。

### 2.3 前端 TS API + Vue Flow 视图

```
frontend-v2/src/api/workflow_builder.ts    # 11 端点 + VFNode/VFEdge 适配器
frontend-v2/src/views/WorkflowBuilder.vue   # 完整可视化搭建器 (~700 行)
```

**视图布局**:三栏 (Vue Flow 工业级拖拽布局)
- **左**:能力目录 (47 域过滤 + 关键字搜索 + 卡片 + HTML5 拖拽)
- **中**:Vue Flow 画布 (节点拖入 + 连线 + Background/Controls/MiniMap)
- **右上**:节点/工作流属性面板 (JSON inputs 编辑器 + 名称/标签/项目绑定)
- **右下**:最近运行历史 (10 步 + 状态 + 耗时)

**核心交互**:
- 拖拽能力卡片到画布即创建节点 (含 catalog 自动填默认输入)
- 节点连线自动建边 (`data` 边)
- 节点点击展开 inputs JSON 编辑器
- 顶部按钮:模板 / 新建 / 保存 / 运行
- 模板 Modal 一键加载 6 个 starter
- 运行 Modal 显示每步耗时 / 状态 / 错误
- 自动保存 (用户点保存或运行时):绑定 project_id 即可项目专属

### 2.4 路由挂载

```
/workflow-builder → WorkflowBuilder.vue
```

## 验证结果

| 验证项 | 结果 |
|--------|------|
| pytest R2 (新) | **17/17 PASS** (topo sort / var expansion / persistence / 6 templates bootstrap / run / failure abort / HTTP) |
| pytest R1 (回归) | **21/21 PASS** |
| pytest 累计 | **38/38 PASS** in 4.66s |
| vue-tsc (项目整体) | **0 errors** exit 0 |
| vite build | PASS 12.87s |
| canvas_web import | OK — 新路由已被 include |
| workflows bootstrap | 6 starter 模板经 `get_engine()` 自动注入 |

## 关键测试覆盖

```
TestTopoSort::test_linear            PASSED  # a→b→c
TestTopoSort::test_branching        PASSED  # a→b→d, a→c→d
TestTopoSort::test_cycle_raises     PASSED  # a↔b ValueError

TestVarExpansion::test_simple_reference            PASSED
TestVarExpansion::test_nested_reference_missing   PASSED  # 保 ${n.x} 不替换
TestVarExpansion::test_nested_input                PASSED

TestPersistence::test_save_and_load      PASSED
TestPersistence::test_list_workflows     PASSED
TestPersistence::test_delete_workflow    PASSED

TestStarterTemplates::test_six_templates_present       PASSED
TestStarterTemplates::test_no_cycle_in_any_template    PASSED
TestStarterTemplates::test_templates_bootstrap_into_engine PASSED

TestRunEndToEnd::test_run_a_simple_workflow                    PASSED  # 2 步
TestRunEndToEnd::test_run_image_annotation_template             PASSED  # 7 步
TestRunEndToEnd::test_run_ai_annotation_template_records_7_steps PASSED  # 7 步
TestRunEndToEnd::test_failed_node_aborts_run                   PASSED  # 失败中断

TestHTTPRoutes::test_templates_endpoint             PASSED  # 6 模板 + reload + run + 404
```

## 关键文件

### 新建 (4 个)

```
backend/imdf/workflow_builder/__init__.py                  (1.2 KB)
backend/imdf/workflow_builder/engine.py                    (12 KB)
backend/imdf/workflow_builder/routes.py                    (3 KB)
backend/imdf/tests/test_r2_workflow_builder.py             (10 KB / 17 测试)
frontend-v2/src/api/workflow_builder.ts                    (5.6 KB)
frontend-v2/src/views/WorkflowBuilder.vue                  (~28 KB)
```

### 修改 (2 个)

```
backend/imdf/api/canvas_web.py                +10 行   # 注册 workflow_builder 路由
frontend-v2/src/router/index.ts               +12 行   # /workflow-builder 路由
```

## 与既有能力的共生

- ✅ 不破坏 R1 — workflow builder 通过 `CapabilityRegistry` 调用,数据流转追踪器自动接收域事件
- ✅ 不破坏 v1.0 `/api/v1/workflow/*` — 新路由挂在 `/api/v1/workflow_builder/*` 前缀隔离
- ✅ 不破坏 Vue Flow 的 `Workflows.vue` — 那个视图保留(AI 生成 DAG)
- ✅ DFS 拓扑校验 + ${...} 字符串解析与既有的 `workflow_contract_routes.py` 互不干扰
- ✅ 测试隔离:`tmp_path` SQLite,每个测试用独立存储

## 用户痛点回应

| 用户痛点 | R2 回应 |
|----------|---------|
| 「工作流搭建呢?能力模块可以搭建工作流?」 | ✅ 47 能力 + Vue Flow 拖拽 + 6 starter 模板 |
| 「工作流 = 自定义组合」 | ✅ 任意能力自由组合 + 保存 + 重跑 + 标记 dirty |
| 「工作流 vs 项目绑定」 | ✅ workflow 含 `project_id` 字段,用户可绑定 |
| 「失败时中断 / 跳过」 | ✅ failed_node_aborts_run 测试 + 错误捕获在 StepResult.error |
| 「AI 流程 vs 数据流程」 | ✅ WorkflowBuilder 是数据生产专用,Workflows.vue 仍是 AI 生成专用 |

## R3 计划预览

按主计划 R3:**8 个骨架管理视图工业级重写**

目标:
- ScoringManagement.vue (122→500+ 行)
- AnnotationManagement.vue (174→500+ 行)
- WorkflowManagement.vue (135→600+ 行)
- AssetManagement.vue (162→500+ 行)
- CleaningManagement.vue (147→600+ 行)
- NotificationManagement.vue (182→500+ 行)
- EvaluationManagement.vue (282→500+ 行)
- UserManagement.vue (208→500+ 行)

每个加:
- 多维筛选 (keyword / 状态 / 时间 / 标签 / 类型 / 评分)
- 批量操作
- 模板预设
- KPI 报表
- 与项目/需求/包多向联动
- 详情抽屉 + 历史版本

继续。
