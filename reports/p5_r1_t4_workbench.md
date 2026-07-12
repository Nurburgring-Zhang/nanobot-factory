# P5-R1-T4 AnnotationWorkbench — 报告

**任务**: 把 Annotation.vue 重写为真画布 + 后端 workbench_engine
**Worker**: coder (mvs_a6f1965c42494af292d620dc62e1ae59)
**完成时间**: 2026-06-28

---

## 1. 目标达成情况

| Spec 项 | 状态 | 证据 |
|---|---|---|
| backend workbench_engine.py | ✅ DONE | 395 行,SQLite + 锁 + 心跳 + 几何校验 + 历史版本链 |
| backend workbench_routes.py | ✅ DONE | 200 行,10 端点,/api/v1/workbench 前缀 |
| frontend Annotation.vue 真画布 | ✅ DONE | 1002 行,SVG 画布 + 6 工具 + 快捷键 + autosave + 心跳 + 提交 modal |
| frontend workbench.ts API client | ✅ DONE | 230 行,完整 TS 接口 + 10 函数 |
| router 注册兼容 /annotation | ✅ DONE | router/index.ts 已有 `/annotation` 路由到 Annotation.vue,自动生效 |
| test_p5_r1_t4_workbench.py ≥15 测 | ✅ DONE | 26 测试 (超出 73%),全部 PASS |
| e2e_workbench.py 8 步 | ✅ DONE | 全部 PASS |
| pytest 15/15 PASS | ✅ DONE | 26/26 PASS |
| vue-tsc 0 error | ⚠️ 仅我的文件 | Annotation.vue 0 error;7 个预存在错误不在本任务 |
| npm run build 0 error | ⚠️ 同上 | 预存在错误 + ProjectCenter.vue 缺失阻断 |
| 后端 9 个端点全可调 | ✅ DONE | 10 端点 (含 enqueue),TestClient 全 200/4xx 正确 |
| E2E 8 步全过 | ✅ DONE | 实测通过 |
| 集成: 标注保存 → 提交 → review queue | ✅ DONE | submit 后 review_stage 自动 draft → self_check,锁释放,任务状态 → submitted |

## 2. 文件清单

### 新建 (5)
```
backend/imdf/engines/workbench_engine.py      # 395 行
backend/imdf/api/workbench_routes.py          # 200 行
frontend-v2/src/api/workbench.ts              # 230 行
tests/test_p5_r1_t4_workbench.py              # 26 测试
tests/test_p5_r1_t4_e2e_workbench.py          # 8 步 E2E
```

### 修改 (2)
```
backend/imdf/api/canvas_web.py                # +1 块注册 workbench_router
frontend-v2/src/views/Annotation.vue          # 307 → 1002 行,完整重写
```

## 3. 验证证据

### 3.1 pytest 26/26 PASS (2.40s)
```
test_01_enqueue_and_pull              PASSED
test_02_pull_empty_returns_none       PASSED
test_03_release_task                  PASSED
test_04_heartbeat_extends_lock        PASSED
test_05_lock_status                   PASSED
test_06a_save_rect                    PASSED
test_06b_save_polygon                 PASSED
test_06c_save_point                   PASSED
test_06d_save_obb                     PASSED
test_06e_save_keypoint                PASSED
test_07_geometry_validation           PASSED
test_08_bulk_save                     PASSED
test_09_submit_flow                   PASSED
test_10_submit_requires_lock_owner    PASSED
test_11_get_task_annotations          PASSED
test_12_get_annotation_history        PASSED
test_13_stats                         PASSED
test_14_pull_http_200                 PASSED
test_15_pull_http_404_when_empty      PASSED
test_16_annotation_http_422           PASSED
test_17_annotation_http_200           PASSED
test_18_submit_http_403               PASSED
test_19_submit_http_200               PASSED
test_20_lock_status_http              PASSED
test_21_stats_http                    PASSED
test_22_bulk_save_http                PASSED
```

### 3.2 E2E 8/8 STEPS PASSED
- Step 1: 拉任务 → 200,locked_by=alice ✅
- Step 2: 锁状态 + 空 annotations ✅
- Step 3: 画矩形 → 200,label=car ✅
- Step 4: 输入 label=truck ✅
- Step 5: 保存 → count=2 ✅
- Step 6: 释放 + 拉下一个 ✅
- Step 7: 提交 → submitted ✅
- Step 8: 锁释放 + review_stage=self_check + 历史 + stats ✅

### 3.3 vue-tsc (我的文件)
- `src/views/Annotation.vue`: 0 error (用 `(ann.geometry as any)` 绕过 union 模板缩窄)
- `src/api/workbench.ts`: 0 error
- `parser 验证`: @vue/compiler-sfc 解析干净

## 4. 设计要点

### 4.1 后端引擎
- **WorkbenchEngine** 线程安全 (threading.RLock + WAL mode SQLite)
- **3 张表**: workbench_tasks, annotations, annotation_history
- **6 种几何类型**: rect / polygon / point / keypoint / obb / mask
- **完整校验链**: Pydantic v2 + 引擎层 + 422 错误码 (无 500 泄漏)
- **锁机制**: 5min TTL + 心跳延长 + 懒回收
- **版本链**: parent_annotation_id 形成版本树,get_annotation_history 拉整链时间线

### 4.2 前端工作台
- **三栏布局**: 左 320px (队列 + 工具) + 中 1fr (SVG 画布 800x600) + 右 360px (标注列表 + 属性面板)
- **SVG 叠加层** (不用 Konva 等重库): 自己实现坐标变换、拖拽、绘制
- **6 工具**: select / rect / polygon / point / keypoint / obb
- **快捷键**: V/R/P/K/O (工具) + Ctrl+Z/Y (撤销/重做) + Delete + [/] (切资产)
- **autosave**: debounce 1s, local id 替换为 server id
- **心跳**: 60s 间隔, 失败静默
- **提交**: modal 确认 → 状态切 submitted → 提示"已推送审核"

### 4.3 API 风格
- TypeScript strict 接口 + 10 个 typed wrapper 函数
- 复用已有 http.ts (axios instance + bearer token)
- 错误码语义化: 422 (校验) / 404 (无任务) / 403 (非锁拥有者) / 409 (心跳/释放冲突)

## 5. 已知约束 / Notes

1. **构建/类型检查非完全通过**: 项目里有 7 个预存在 vue-tsc 错误在 `Scoring.vue / ScoringManagement.vue / PackManager.vue / InternalQC.vue / EvaluationManagement.vue / api/project.ts` 中,**与本任务无关**。这些是之前 P 任务遗留/未追踪文件。`ProjectCenter.vue` 在 router 引用但文件不存在,导致 vite build 加载失败。本任务**新增代码本身 0 错误**,Annotation.vue 通过 `@vue/compiler-sfc` parse 干净。

2. **路由兼容**: 现有 `router/index.ts` 已将 `/annotation` 路由指向 `Annotation.vue`,内部逻辑彻底替换为 Workbench 实现,URL 兼容。

3. **占位图**: 没有真实 asset URL 时生成 SVG data URI,离线可演示。

4. **后端引擎 register**: 与 canvas_web.py 中其他路由风格一致 (try/except + logger.info/warning),失败不阻断其他路由加载。

## 6. memory 学习点 (本次任务)

无新增跨项目复用 pattern。本任务用的 pattern 已存在于 memory:
- `python-footguns.md`: Pydantic v2 model_validator → 500 (本任务用 HTTPException 4xx 避免)
- `typescript-vite-react-traps.md`: vue-tsc 真实状态判定 (用 `--noEmit` 而非 vite build 蒙混)
- `fastapi-validation-patterns.md`: 7-mode 参数分类 + body_schemas import 模板 (本任务简化, 直接 inline)
- `multi-worker-orchestration.md`: retry 降级策略 (本任务无 retry, 一次成功)