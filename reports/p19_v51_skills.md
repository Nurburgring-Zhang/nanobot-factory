# P19 v5.1-B 报告 — 50 内置 Skill 集成

**作者**: coder (MiniMax Agent)
**日期**: 2026-07-02
**任务**: P19 v5.1-B
**状态**: ✅ DONE

---

## 1. 目标

把 V5 附录 D 中规划的 **50 个内置 Skill** (11 类基础 + 11 扩展) 集成到
`backend/skills.py + backend/skills_manager.py + backend/external_skills.py`,
并新增 `SkillRegistry` / `SkillExecutor` 提供:
- 异步执行
- 超时控制 (默认 30s)
- 错误处理 + 重试 (最多 3 次)
- 审计日志
- 注册表查询 / 搜索 / trigger matching

测试 5 大验证点全部通过。

---

## 2. 整体改动概览

| 文件 | 状态 | 说明 |
|---|---|---|
| `backend/skills.py` | 重建 | 物理文件 + `SkillSpec` dataclass (V5.1 附录 D 字段) |
| `backend/skills/legacy.py` | 新建 | 原 skills.py 5 个 BaseSkill 移植,使 `from backend.skills import SkillManager` 重新可用 |
| `backend/skills/__init__.py` | 修改 | re-export SkillSpec / Skill / SkillManager / get_skill_manager |
| `backend/skills_builtin.py` | 新建 | **50 个 builtin Skill** (11 类) |
| `backend/skills_manager.py` | 修改 | 末尾追加 `SkillRegistryV51` (V5.1 模式) |
| `backend/external_skills.py` | 修改 | 末尾追加 `SkillExecutorV51` (async / timeout / retry / audit) |
| `backend/tests/test_skills_builtin_50.py` | 新建 | 11 tests |
| `backend/tests/test_skills_registry.py` | 新建 | 19 tests |
| `backend/tests/test_skills_executor.py` | 新建 | 10 tests |

**重要修复**:`backend/skills.py` 此前被同名 package `backend/skills/` shadow,
导致既有 `from backend.skills import SkillManager` (production_agents.py) 也
已经 broken。这次修复同步恢复了对既有代码的兼容性。

---

## 3. Skill dataclass (V5.1 附录 D)

```python
@dataclass
class SkillSpec:  # alias: Skill
    id: str                              # 唯一 id,如 "skill_crawl_web"
    name: str                            # 中英双语名称
    category: str                        # 11 类之一
    trigger_phrases: List[str]           # 触发短语
    inputs: Dict[str, Any]               # 输入字段 schema
    outputs: Dict[str, Any]              # 输出字段 schema
    description: str = ""                # 中英双语描述
    enabled: bool = True
    version: str = "1.0.0"               # semver
    dependencies: List[str]              # 依赖其它 skill.id
```

提供 `to_dict()` / `from_dict()` 序列化方法。

---

## 4. 50 内置 Skill 分类

| # | 类别 | 数量 | 示例 ID |
|---|---|---|---|
| 1 | crawl    | 10 | `skill_crawl_web`, `skill_crawl_deep`, `skill_seed_extract`, `skill_sitemap_parse` |
| 2 | process  |  5 | `skill_dedupe`, `skill_auto_label`, `skill_score_quality`, `skill_translate` |
| 3 | agent    |  8 | `skill_agent_chat`, `skill_agent_memory`, `skill_agent_plan`, `skill_agent_multi` |
| 4 | octo     |  4 | `skill_octo_bot_create`, `skill_octo_channel_create`, `skill_octo_matter_create` |
| 5 | vida     |  2 | `skill_vida_screen`, `skill_vida_action` |
| 6 | meta_kim |  3 | `skill_meta_intent`, `skill_meta_review`, `skill_meta_lesson` |
| 7 | drama    |  5 | `skill_drama_script`, `skill_drama_character`, `skill_drama_shot`, `skill_drama_assemble` |
| 8 | comfy    |  3 | `skill_comfy_run`, `skill_comfy_workflow`, `skill_comfy_model` |
| 9 | redfox   |  3 | `skill_redfox_search`, `skill_redfox_hot`, `skill_redfox_publish` |
| 10 | reach   |  4 | `skill_reach_web`, `skill_reach_twitter`, `skill_reach_github`, `skill_reach_arxiv` |
| 11 | agency  |  3 | `skill_agency_expert`, `skill_agency_department`, `skill_agency_capability` |
| | **TOTAL** | **50** | |

每个 Skill 含 1+ `trigger_phrases` (中英双语) + `inputs`/`outputs` schema +
dependencies 链。

---

## 5. SkillRegistry (V5.1)

`backend/skills_manager.py` 末尾追加 `SkillRegistryV51`,API 完整:

```python
reg = SkillRegistryV51.from_builtin(BUILTIN_SKILLS)
# register(skill), register_all(list)
# get(skill_id), list_by_category(cat), list_categories()
# search(query, limit=10)        — 模糊
# trigger_match(phrase)          — 精确 + 子串回退
# to_json() / from_json()        — 完整序列化
# __contains__(id), __len__()
```

**Alias** `SkillRegistry = SkillRegistryV51` 让任务 API 名可工作。

---

## 6. SkillExecutor (V5.1)

`backend/external_skills.py` 末尾追加 `SkillExecutorV51`:

```python
exec_ = SkillExecutorV51(
    registry=reg,
    default_timeout_sec=30.0,
    max_retries=3,
    retry_backoff_sec=0.1,
)
result = await exec_.execute(
    "skill_crawl_web",
    {"url": "https://x.com", "depth": 2},
    timeout_sec=5.0,  # 可覆盖 default
)
# -> {"ok": bool, "skill_id": str, "result": Any,
#     "error": str|None, "attempts": int, "duration_ms": float}
```

- **异步**: `asyncio.wait_for(handler, timeout)`
- **超时**: 默认 30s,可 per-call override
- **重试**: 默认 3 次,指数退避 (`backoff * 2^(n-1)`)
- **审计日志**: 每次执行写一条 `SkillExecutionRecord(skill_id, started_at, ended_at, duration_ms, success, error, attempts, inputs, output_preview)`,可按 skill_id 过滤 / 清空

Handler 解析策略:
1. `skill.metadata["handler_coro"]` (coroutine function) → 首选
2. `skill.metadata["handler_callable"]` (sync) → 第二
3. `skill.metadata["handler_factory"]` (callable that returns handler) → 第三
4. 默认 echo handler(把 inputs 镜像成 output)— 让 50 个 builtin 在未注入真实 handler 情况下仍可 round-trip 测试

---

## 7. 测试结果

### 7.1 `test_skills_builtin_50.py` — 11/11 PASS

```
TestBuiltinCount:
  test_total_is_50             PASS
  test_categories_count        PASS  (10+5+8+4+2+3+5+3+3+4+3=50)
TestBuiltinUniqueness:
  test_unique_ids              PASS  (50 unique)
  test_unique_categories       PASS  (11 类合法)
TestBuiltinShape:
  test_each_has_required_fields PASS
  test_trigger_phrases_not_empty PASS
  test_inputs_outputs_not_empty  PASS
TestBuiltinRegistration:
  test_register_all             PASS  (全部 register 成功)
  test_specific_id_present      PASS  (11 个代表 ID 全在)
  test_trigger_match_cn         PASS  (抓取网页 → skill_crawl_web)
  test_search_by_query          PASS
```

### 7.2 `test_skills_registry.py` — 19/19 PASS

```
TestRegister (3):
  test_register_one
  test_register_duplicate_raises
  test_register_all
TestQueries (4):
  test_get, test_get_missing_returns_none
  test_list_by_category, test_list_categories
TestSearch (4):
  test_search_finds_by_name, test_search_finds_by_description_keyword
  test_search_empty_returns_empty, test_search_no_match_returns_empty
TestTriggerMatch (5):
  test_match_chinese_phrase, test_match_english_phrase
  test_match_dedupe, test_match_substring
  test_match_unknown_returns_none
TestSerialize (2):
  test_to_json, test_to_json_is_ascii_safe
TestAlias (1):
  test_alias_works
```

### 7.3 `test_skills_executor.py` — 10/10 PASS

```
TestAsyncExecute (3):
  test_execute_skill_success     PASS  (async ok)
  test_execute_unknown_skill     PASS
  test_execute_disabled_skill    PASS

TestTimeout (1):
  test_timeout_triggers_retries  PASS  (3 retries,全部 timeout)

TestRetry (2):
  test_retry_until_success       PASS  (2nd try 成功)
  test_retry_exhausted_returns_failure  PASS

TestAuditLog (3):
  test_audit_record_per_call     PASS  (每次写 1 条)
  test_audit_filter_by_skill_id  PASS
  test_clear_audit_log           PASS

TestAlias (1):
  test_executor_alias            PASS
```

**总计 40/40 PASS**,耗时 < 1s。

---

## 8. 关键决策与问题排查

### 8.1 `backend/skills.py` 与同名 package 冲突

`backend/skills.py` (file) 与 `backend/skills/` (package) 共存,Python 优先
解析 package,导致:
- `from backend.skills import SkillManager` (production_agents.py line 23) 失败
- `scripts/quick_audit.py` 也预期此 import 工作

**修复方案**:
1. 把 `backend/skills.py` 内容迁到 `backend/skills/legacy.py`
2. 在 `backend/skills/__init__.py` re-export 所有 legacy 符号 (`SkillManager`, `SkillInput`, `get_skill_manager`, 5 个 Skill 类等)
3. 同时在 package `__init__` 末尾追加 V5.1 `SkillSpec` dataclass + `Skill` alias

修复后 `from backend.skills import SkillManager, SkillInput, get_skill_manager, SkillSpec, Skill` 全部可用,production_agents.py 重新可工作。

`backend/skills.py` 物理文件保留为 source reference,含 V5.1 SkillSpec 字段定义。

### 8.2 Skill handler 默认 echo

50 个 builtin 默认无 handler,executor 注入默认 echo handler 来 round-trip —
这保证 registry 集成测试时 50 个 skill 都能 `execute()` 而不抛错。真实执行
时各 Skill 通过 `Skill.metadata["handler_coro"]` 注入真实实现。

---

## 9. 后续可扩展点

1. **真实 handler 注入**:每个 builtin skill 注册时同时注入真实 handler。
2. **触发路由器**:把 trigger_match 与 LLM routing 整合,接收用户口语化指令自动调起 skill。
3. **SkillMarketplace 融合**:与已有 `backend/skills/marketplace.py` 整合,让 builtin 与社区 skill 共享 UI。
4. **持久化 audit log**:目前 audit_log 只在内存,可加 SQLite 后端做 ops dashboard。
5. **依赖拓扑执行**:支持按 dependencies 自动 pre-run 前置 skill。

---

## 10. 文件清单(交付)

```
backend/skills.py                                       (~3.4 KB)
backend/skills/legacy.py                                (~9.5 KB)
backend/skills/__init__.py                              (+re-export)
backend/skills_builtin.py                               (~18 KB)
backend/skills_manager.py                               (+SkillRegistryV51)
backend/external_skills.py                              (+SkillExecutorV51)
backend/tests/test_skills_builtin_50.py                 (11 tests)
backend/tests/test_skills_registry.py                   (19 tests)
backend/tests/test_skills_executor.py                    (10 tests)
```

**测试**: 40/40 PASS in < 1s
**耗时**: ~17 min (25min 预算内)
**改动文件数**: 9 (其中 5 新建 + 4 修改)

---
*Generated by coder (MiniMax Agent) — P19 v5.1-B*
