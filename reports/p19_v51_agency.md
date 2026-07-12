# P19 v5.1-A — The Agency (232 专家) — Delivery Report

> V5 Chapter 28 — "The Agency" 静态人才市场 → 静态数据 driver + 16 部门
> `backend.imdf.agency` 包：JSON roster + frozen dataclass + agency loader。

---

## 1. 交付目标

把 V5 第 28 章的 **232 个虚拟专家 / 16 部门 + 1 spare 池** 落成
工程级模块（不是 inline list、不是 dead docstring），让 V5 routing
层可以真正去 import:

```python
from backend.imdf.agency import (
    AgencyLoader,
    AgentRole,
    Bilingual,
    DEPARTMENT_ORDER,        # 16
    DEPARTMENT_SEAT_QUOTAS,  # sums to 232
    EXPECTED_TOTAL_ROLES,    # 232
)
loader = AgencyLoader()                       # 校验 + load
loader.load_all()                             # 232 roles
loader.load_by_department("Data Acquisition") # 15
loader.load_by_id("data_acquisition_expert_001")
loader.search("crawler")
loader.get_capability_matrix()                # {skill: [role_ids]}
```

VDP 报告里写的 "差 217" 已经覆盖：

```
| **Agent 角色** | 0 | **232** | 15 | **差 217** | **P0** |
```

P19 v5.1-A 任务把 `15 → 232`，P0 缺口从 217 → 0。

---

## 2. 16 部门 + spare 池分布

| # | Department              | 配额 | 备注                                  |
|---|-------------------------|------|---------------------------------------|
| 1 | Data Acquisition        | 15   | 12 类爬虫工程师 + crawler 编排         |
| 2 | Annotation              | 15   | bbox/3D/LiDAR/OCR/panoptic 全套        |
| 3 | Quality Assurance       | 15   | 视觉/音频/视频/文本 + NSFW/偏见/美学   |
| 4 | Workflow                | 14   | DAG / cron / 退避 / 模板 + A/B + prompt flow |
| 5 | Project Management      | 12   | 10 PM + 2 TPM                         |
| 6 | Domain Expert           | 20   | 医学/法律/财报/农业/工业/...           |
| 7 | Creative Writing        | 15   | 故事/角色/类型 + 漫画/童书/翻译       |
| 8 | Visual Arts             | 15   | 摄影/UI/服装/CG/Mograph               |
| 9 | Audio & Music           | 12   | 作曲/拟音/混音/TTS/水印              |
| 10 | Video & Film            | 15   | 摄影/剪辑/调色/动画/分镜/短剧         |
| 11 | AI/ML Research          | 15   | LLM/Diffusion/RL/安全/可解释          |
| 12 | Security & Compliance   | 10   | Pentest/应用安全/PII/GDPR/SOC2        |
| 13 | DevOps & Infrastructure| 10   | SRE/Observability/DB/网络/存储        |
| 14 | Customer Service        | 12   | 一/二线/CSM/培训/升级 + 知识库         |
| 15 | Sales & Marketing       | 12   | AE/SC/Pricing/SEO + 线下/渠道          |
| 16 | Executive & Strategy    | 10   | CEO/CTO/CPO/CDO/CFO/COO + 研究/法务/HR/战略 |
| — | `_spare_`               | 15   | 跨职能 bench（分诊/插画/QA 替补/礼宾） |
|   | **Total**               | **232** |                                    |

> **数学修正**：任务书给的部门原始数目加起来是 209（不是 217）。
> 为了兼容 "凑 232 加 15 spare" 的意图，把 4 个 10 配额的小部门
> （Workflow / PM / Customer Service / Sales & Marketing）扩充到
> 14/12/12/12，加 8 个专家，部门合计 217 + spare 15 = 232。

---

## 3. 文件清单

```
backend/imdf/agency/
├── __init__.py            (≈ 1.9 KB) — 公开 API
├── loader.py              (≈ 19 KB)  — AgentRole/Bilingual/AgencyLoader
├── departments.json       (≈ 169 KB) — 232 角色整表
├── scripts/
│   └── build_roster.py    (≈ 78 KB)  — roster 数据生成器
└── tests/
    ├── __init__.py
    ├── test_loader.py     — 23 tests
    └── test_departments.py — 123 parametrised tests

reports/p19_v51_agency.md  ← (this file)
```

### `loader.py` 关键点

* `AgentRole(frozen=True, slots=True)` — 不可变实例，线程安全
* `Bilingual(zh, en)` — 双语字段辅助类，禁空白
* `AgencyLoader` 公开方法:
  * `load_all() -> List[AgentRole]`
  * `load_by_department(department: str) -> List[AgentRole]` — case-insensitive
  * `load_by_id(role_id: str) -> Optional[AgentRole]`
  * `search(query: str) -> List[AgentRole]` — 全字段 case-insensitive
  * `get_capability_matrix() -> Dict[str, List[str]]` — skill → sorted role ids
  * `departments_present() -> List[str]` — 现役部门列表
* module-level `DEPARTMENT_ORDER` (16-tuple) + `DEPARTMENT_SEAT_QUOTAS` (17-dict)
  + `EXPECTED_TOTAL_ROLES = 232`
* 构造时（`__init__`）就 eager-load + validate，fail-fast
* `reload(source)` 可强制 reload（测试友好）

### `departments.json` schema

每条记录：

```json
{
  "id": "data_acquisition_expert_001",
  "name": {"zh": "...", "en": "..."},
  "department": "Data Acquisition",
  "title": "Senior Crawler Specialist",
  "skills": ["crawler", "scraping", ...],
  "description": {"zh": "...", "en": "..."},
  "avatar_url": null,
  "system_prompt": {"zh": "...", "en": "..."}
}
```

* 顶层是 list（也接受 `{"departments": [...]}` 包装）
* 232 条记录、slug 命名 `<dept_slug>_expert_NNN`
* `avatar_url` 当前一律 `null`（V5.1 后续阶段接 CDN 头像）

---

## 4. 测试覆盖

```
$ python -m pytest backend/imdf/agency/tests/ -v
... 146 passed in 0.18s
```

| 文件 | tests | 覆盖 |
|---|---|---|
| `test_loader.py`        | 23 | load_all / by_department / by_id / search / capability_matrix + 5 invariants |
| `test_departments.py`   | 123 | 17 buckets × 6 invariants (quota / id-prefix / bilingual / skills / title / matrix-membership) + 5 globals |

### test_loader.py (23)

1. `test_load_all_returns_expected_total` (Task #1: 232 角色)
2. `test_load_all_ids_are_unique`
3. `test_load_all_ids_follow_slug_pattern`
4. `test_load_all_departments_are_canonical`
5. `test_load_by_department_data_acquisition_has_15` (Task #2: 15 角色)
6. `test_load_by_department_is_case_insensitive`
7. `test_load_by_department_empty_returns_empty`
8. `test_load_by_id_returns_role_for_valid_slug` (Task #3 有效)
9. `test_load_by_id_returns_none_for_unknown` (Task #3 无效)
10. `test_load_by_id_roundtrips_all_roles`
11. `test_search_crawler_returns_relevant_hits` (Task #4: "crawler")
12. `test_search_is_case_insensitive`
13. `test_search_empty_query_returns_all`
14. `test_search_zero_hits_for_unknown`
15. `test_search_results_ordered_by_department_then_id`
16. `test_capability_matrix_covers_all_232_roles` (Task #5: 232)
17. `test_capability_matrix_values_are_sorted_lists`
18. `test_capability_matrix_at_least_one_skill_per_role`
19. `test_agent_role_is_frozen`
20. `test_bilingual_rejects_empty_strings`
21. `test_bilingual_from_value_dict_and_string`
22. `test_agency_dir_path_exists`
23. `test_department_order_has_16_entries`

### test_departments.py (123 parametrised)

* `test_department_has_expected_seat_count[<dept>-<quota>]` × 17 = **17**
* `test_department_quota_dict_matches_module_constant` = 1
* 5 invariant suites (`ids_use_correct_slug` / `roles_have_bilingual_fields`
  / `roles_have_skills` / `roles_have_title` / `ids_are_unique_within_department`
  / `contributes_to_capability_matrix`) × 17 = 6 × 17 = 102
* `test_spare_pool_distinct_from_canonical_departments` = 1
* `test_department_order_has_16_entries` = 1
* `test_department_seat_quotas_sum_to_232` = 1

Total = 17 + 1 + 102 + 1 + 1 + 1 = 123 ✓

---

## 5. 集成点 / 后续

* **V5.1 routing 层**：在 `agent_router.py` 里调用
  `loader.search(query)` + `loader.get_capability_matrix()` 完成意图路由。
* **V5.2 P19-B (6 级去重)**：可借 `_spare_` 池的 "Float Annotator" 角色
  顶峰 spike。
* **V5.2 P19-Y (RBAC)**：权限矩阵可联合 `AgentRole.department` 与
  `Skill` 字段做 attribute-based check。
* **avatar_url**：现阶段 all-NULL；V5.2 后端接 CDN pipeline 时再 backfill。

---

## 6. 总结

* **任务**：补 V5 P0 第 8-11 项 Agent 系统的 "232 个虚拟专家 / 16 部门" 数据底座。
* **完成度**：
  * loader: ✅ 5 个公开方法 + 3 个公开 dataclass + 4 个 module-level 常量
  * data: ✅ 232 专家 / 16 canonical + 1 spare 池
  * tests: ✅ 146/146 PASS（23 + 123 parametrised）
* **下一步**：把 `loader.search()` 与 `loader.get_capability_matrix()` 接入
  `P19-H` 意图分类器、`P19-I` 命令解析器、`P19-J` 命令路由器。
