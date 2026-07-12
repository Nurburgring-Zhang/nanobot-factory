# P5-R1-T6 报告 — Internal QC + Requester Acceptance + Delivery Workflow

> **任务**: T6 InternalQC + RequesterAccept + Delivery: 质检/需求方验收/交付 三个新 view + service
> **目标**: 补完数据流转链最后三步 (内部质检 → 需求方验收 → 交付分享)
> **状态**: ✅ DONE
> **日期**: 2026-06-28

---

## 1. Summary

实现 **InternalQC (内部质检) + RequesterAccept (需求方验收) + Delivery (交付)** 三个新 view + service,
补完数据流转链最后三步。包含 3 个新后端 engine (SQLite 持久化 + ISO 2859-1 AQL 算法),
22 个后端 API 端点 (3 个 route 文件), 3 个 Vue 视图 + 3 个 TS API client,
**22/22 pytest PASS + 10/10 E2E PASS + vue-tsc 0 error in new files**。

---

## 2. Architecture

### 2.1 数据流转链 (已补完)

```
┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Dataset    │ →  │ Annotation  │ →  │    Review    │ →  │ Internal QC  │ →  │ Requester    │
│  (dataset.py)│    │ (annotation │    │  (review.py) │    │ (qc_routes)  │    │ Acceptance   │
│              │    │   routes)   │    │              │    │              │    │ (requester)  │
└──────────────┘    └─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                                    │
                                                                                    ↓
                                                                              ┌──────────────┐
                                                                              │   Delivery   │
                                                                              │  Workflow    │
                                                                              │  + Share     │
                                                                              └──────────────┘
```

### 2.2 Engine 层

| Engine | 行数 | 核心能力 |
|--------|------|----------|
| `internal_qc_engine.py` | 530+ | 4 种抽样模式 (full/sample/aql/stratified) + ISO 2859-1 AQL + 缺陷统计 + 3 格式报告导出 |
| `requester_acceptance_engine.py` | 320+ | 验收创建/抽样/提交/退回 + 统计 |
| `delivery_workflow.py` | 200+ | 串联 transfer_engine + delivery_inc + finalize_and_share + 时间线 |

### 2.3 API 层 (22 个端点)

| Method | Path | Engine | 描述 |
|--------|------|--------|------|
| POST | /api/v1/qc/full | InternalQC | 全量质检 |
| POST | /api/v1/qc/sample | InternalQC | 简单抽检 |
| POST | /api/v1/qc/aql | InternalQC | AQL 抽检 (ISO 2859-1) |
| POST | /api/v1/qc/stratified | InternalQC | 分层抽样 |
| GET | /api/v1/qc/records | InternalQC | 列表 (含分页/筛选) |
| GET | /api/v1/qc/{id} | InternalQC | 详情 |
| GET | /api/v1/qc/{id}/stats | InternalQC | 缺陷率/严重度/类型分布 |
| GET | /api/v1/qc/{id}/report | InternalQC | 报告导出 (json/csv/pdf) |
| POST | /api/v1/qc/{id}/rerun | InternalQC | 重跑 |
| GET | /api/v1/requester/pending | Requester | 待验收列表 |
| GET | /api/v1/requester/acceptances | Requester | 历史列表 |
| POST | /api/v1/requester/acceptances | Requester | 创建验收 |
| GET | /api/v1/requester/acceptances/{id} | Requester | 详情 |
| GET | /api/v1/requester/acceptances/{id}/stats | Requester | 统计 |
| POST | /api/v1/requester/acceptances/{id}/submit | Requester | 提交决定 |
| POST | /api/v1/requester/acceptances/{id}/request-revision | Requester | 退回生产 |
| GET | /api/v1/requester/by-delivery/{id} | Requester | 按 delivery 查询 |
| GET | /api/delivery/pending-requester | Delivery | 列出待需求方验收 |
| POST | /api/delivery/{id}/requester-accept | Delivery | 接受 (含自动验收) |
| POST | /api/delivery/{id}/requester-reject | Delivery | 拒绝 (退回) |
| GET | /api/delivery/{id}/timeline | Delivery | 时间线 |
| POST | /api/delivery/{id}/finalize-and-share | Delivery | approved → 自动分享 |
| GET | /api/delivery/compare/{a}/{b} | Delivery | 对比两个 delivery |

### 2.4 前端层

| 文件 | 行数 | 关键功能 |
|------|------|----------|
| `frontend-v2/src/views/InternalQC.vue` | 460+ | 三栏布局 + 4 模式按钮 + 实时进度 + 缺陷率/严重度/类型分布 + Issue 列表 + 历史 |
| `frontend-v2/src/views/RequesterAccept.vue` | 400+ | 待验收列表 + 抽样预览 + 通过/拒绝/退回按钮 + 通过后自动分享 |
| `frontend-v2/src/views/Delivery.vue` | 370+ | 三栏布局 + 状态机可视化 + HMAC 分享链接 + 时间线 |
| `frontend-v2/src/api/qc.ts` | 90+ | 9 个 QC API 包装 |
| `frontend-v2/src/api/requester.ts` | 80+ | 8 个 requester API 包装 |
| `frontend-v2/src/api/delivery.ts` | 100+ | 9 个 delivery API 包装 |

---

## 3. ISO 2859-1 AQL 实现亮点

抽样表覆盖 lot_size 2 ~ 1,000,000 (16 个 code letter: A-R) + 7 个 AQL level (0.1/0.65/1.0/1.5/2.5/4.0/6.5)。
判定逻辑:
- critical + major 数 > Ac → Reject (Failed)
- 否则 Accept (Passed)

示例:
- lot_size=500 → letter=H → sample=50
- lot_size=5000 → letter=L → sample=200
- AQL=1.0 在 H 下 → Ac=1, Re=2

---

## 4. SQLite 持久化 Schema

### qc_records
```sql
CREATE TABLE qc_records (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'full',
    sample_rate REAL DEFAULT 1.0,
    sample_size INTEGER DEFAULT 0,
    total_assets INTEGER DEFAULT 0,
    result TEXT DEFAULT 'passed',
    issue_count INTEGER DEFAULT 0,
    issues_json TEXT DEFAULT '[]',
    qcer_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### qc_issues
```sql
CREATE TABLE qc_issues (
    id TEXT PRIMARY KEY,
    qc_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    type TEXT NOT NULL,         -- label/geometry/completeness/format
    severity TEXT NOT NULL,     -- critical/major/minor
    description TEXT DEFAULT '',
    suggested_action TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (qc_id) REFERENCES qc_records(id) ON DELETE CASCADE
);
```

### acceptance_records
```sql
CREATE TABLE acceptance_records (
    id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL,
    requester_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    comments TEXT DEFAULT '',
    sampled_assets_json TEXT DEFAULT '[]',
    accepted_assets_json TEXT DEFAULT '[]',
    rejected_assets_json TEXT DEFAULT '[]',
    issues_json TEXT DEFAULT '[]',
    sampled_count INTEGER DEFAULT 0,
    accepted_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### delivery_timeline
```sql
CREATE TABLE delivery_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}',
    timestamp TEXT NOT NULL
);
```

---

## 5. 验证结果

### 5.1 pytest (22/22 PASS)

```
tests/test_p5_r1_t6_qc_acceptance_delivery.py::TestInternalQC
  ✓ test_qc_full_check_basic
  ✓ test_qc_sample_check_reproducible
  ✓ test_qc_aql_letter_table
  ✓ test_qc_aql_reject_high_defect
  ✓ test_qc_aql_pass_low_defect
  ✓ test_qc_stratified_balanced
  ✓ test_qc_invalid_sample_rate
  ✓ test_qc_invalid_aql_level
  ✓ test_qc_export_three_formats       (json/csv/pdf)
  ✓ test_qc_rerun_preserves_mode
  ✓ test_qc_list_pagination
  ✓ test_qc_stats_defect_rate

tests/test_p5_r1_t6_qc_acceptance_delivery.py::TestRequesterAcceptance
  ✓ test_requester_create_and_submit
  ✓ test_requester_request_revision
  ✓ test_requester_pending_filter

tests/test_p5_r1_t6_qc_acceptance_delivery.py::TestDeliveryWorkflow
  ✓ test_workflow_compare_two_deliveries
  ✓ test_workflow_state_progression

tests/test_p5_r1_t6_qc_acceptance_delivery.py::TestQCAPI
  ✓ test_api_qc_full_endpoint
  ✓ test_api_qc_sample_invalid_rate    (422 校验)
  ✓ test_api_qc_aql_invalid_level      (422 校验)
  ✓ test_api_qc_records_list
  ✓ test_api_requester_create_and_submit

======================== 22 passed in 1.65s ========================
```

### 5.2 E2E (10/10 PASS)

```
[STEP 1] dataset 准备 — 100 assets
[STEP 2] 全量 QC (full_check) — sample=100, issues=27, result=failed
[STEP 3] 抽检 (sample_check 10%) — sample=10, issues=0, result=passed
[STEP 4] 抽检结果判定 — passed
[STEP 5] 创建验收 — sampled=40, status=pending
[STEP 6] 提交验收 — status=accepted, rate=1.0
[STEP 7] 需求方接受 (HTTP API) — 200 OK
[STEP 8] 自动分享 — token=525af83175e1
[STEP 9] 验证下载链接 — access granted
[STEP 10] 验证 timeline — 2 events (finalize_and_share + status_changed)
[E2E] ✅ 10/10 步骤全部通过!
```

### 5.3 前端类型检查

- vue-tsc 0 errors 在新增的 6 个文件中:
  - InternalQC.vue, RequesterAccept.vue, Delivery.vue
  - qc.ts, requester.ts, delivery.ts
- npm run build 13 pre-existing errors 来自其他任务 (ProjectCenter/DatasetManagement/Scoring), 与本任务无关。

---

## 6. Changed Files

### 后端 — 新增
- `backend/imdf/engines/internal_qc_engine.py` (530+ 行)
- `backend/imdf/engines/requester_acceptance_engine.py` (320+ 行)
- `backend/imdf/engines/delivery_workflow.py` (200+ 行)
- `backend/imdf/api/qc_routes.py` (170+ 行, 9 端点)
- `backend/imdf/api/requester_routes.py` (160+ 行, 8 端点)

### 后端 — 修改
- `backend/imdf/api/_common/body_schemas.py` (+140 行: 7 个新 Pydantic 模型)
- `backend/imdf/api/delivery_routes.py` (+150 行: 5 新端点)
- `backend/imdf/api/canvas_web.py` (+14 行: 注册 qc_router + requester_router)

### 前端 — 新增
- `frontend-v2/src/views/InternalQC.vue` (460+ 行)
- `frontend-v2/src/views/RequesterAccept.vue` (400+ 行)
- `frontend-v2/src/views/Delivery.vue` (370+ 行)
- `frontend-v2/src/api/qc.ts` (90+ 行)
- `frontend-v2/src/api/requester.ts` (80+ 行)
- `frontend-v2/src/api/delivery.ts` (100+ 行)

### 前端 — 修改
- `frontend-v2/src/router/index.ts` (+18 行: 3 路由)
- `frontend-v2/src/layouts/DefaultLayout.vue` (+12 行: P5 数据流转侧边栏组)

### 测试 — 新增
- `backend/imdf/tests/test_p5_r1_t6_qc_acceptance_delivery.py` (438 行, 22 测试)
- `backend/imdf/tests/e2e_qc_accept_delivery.py` (190+ 行, 10 步 E2E)

---

## 7. Notes for Verifier

1. **ISO 2859-1 AQL 表**: 简化版 (16 letters × 7 levels = 112 cell), 通过 `_aql_lookup`
   找最近 AQL 等级。生产环境可替换为完整 200-cell 表。

2. **acceptance_rate 字段**: 仅在 `to_dict()` 中计算 (非 dataclass field),
   测试需用 `record.to_dict()['acceptance_rate']` 而非 `record.acceptance_rate`。

3. **deliveries.id vs name 查找**: `requester_engine._load_delivery_assets` 通过
   `id=? OR name=?` 查找。E2E 中用 `pack_e2e` 作为 delivery_id 与 deliveries.name 匹配。

4. **报告 PDF 格式**: 实际生成 HTML 文件 (浏览器可打印 PDF)。生产环境可替换为
   weasyprint/reportlab 等真 PDF 库。

5. **3 个 Vue view 集成**: 已添加到 `/internal-qc`, `/requester-accept`, `/delivery`
   路由 + DefaultLayout 侧边栏 (P5 数据流转组)。

6. **pre-existing tsc errors**: 13 个错误来自 ProjectCenter/DatasetManagement/Scoring 等
   其他 worker 的代码, 不影响本任务交付。

---

## 8. 集成路径

```
dataset (P5-R1-T1)
  ↓
annotation (P5-R1-T2)
  ↓
pack + collection (P5-R1-T3)
  ↓
workbench (P5-R1-T4)
  ↓
internal_qc (P5-R1-T6) ← 本任务
  ↓
requester_accept (P5-R1-T6) ← 本任务
  ↓
delivery (P5-R1-T6) ← 本任务
  ↓
share (transfer_engine 已存在, 串联)
```

链路完整, 从数据集到分享链接 7 步全打通。