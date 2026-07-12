# P19 v5.3 — Vida 屏幕感知主控 Agent 实现报告

> V5 第 26 章 — "屏幕感知型主控 Agent (Vida 完整实现)"

---

## 1. 任务目标

实现 V5 文档第 26 章描述的 **Vida 屏幕感知型主控 Agent** — 一个"不等待命令、
主动协助"的桌面 Agent 系统。核心理念: **持续感知屏幕 → 理解上下文 → 预测用户意图 →
当置信度足够时主动执行行动 → 形成闭环**。

参考: V5 doc chapter 26 (line 6080-6330 in `reports/V5_doc_decoded.txt`)

---

## 2. 实现总览

### 2.1 文件清单

| # | 文件 | 路径 | LOC | 角色 |
|---|---|---|---|---|
| 1 | `schemas.py` | `backend/imdf/intelligence/vida/` | 172 | Pydantic v2 数据模型 |
| 2 | `screen_capture.py` | `backend/imdf/intelligence/vida/` | 197 | 多平台屏幕抓拍 (win/mac/linux/mock) |
| 3 | `context_analyzer.py` | `backend/imdf/intelligence/vida/` | 168 | 6 场景识别 + key_info 提取 |
| 4 | `intent_predictor.py` | `backend/imdf/intelligence/vida/` | 162 | LLM-based 意图预测 + heuristic fallback |
| 5 | `action_executor.py` | `backend/imdf/intelligence/vida/` | 170 | 7 种主动行动执行 |
| 6 | `memory_store.py` | `backend/imdf/intelligence/vida/` | 159 | 用户级 JSON memory (atomic write) |
| 7 | `__init__.py` | `backend/imdf/intelligence/vida/` | 56 | 包入口 |
| 8 | `tests/test_vida.py` | `backend/imdf/intelligence/vida/tests/` | 436 | **41 个 pytest 用例** |
| 9 | `vida_engine.py` | `backend/imdf/engines/` | 336 | VidaEngine 编排器 (DI) — 重写 |
| 10 | `registry.py` | `backend/imdf/skills/` | 343 | 注册 `vida_proactive_assist` Skill |
| **TOTAL** | | | **2199** | |

### 2.2 架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                           VidaEngine                                 │
│                                                                      │
│   ┌─────────────────┐                                                │
│   │ ScreenCapture   │  win32gui / pyautogui+AppKit / scrot / mock    │
│   └────────┬────────┘                                                │
│            │ ScreenData                                              │
│            ▼                                                         │
│   ┌─────────────────┐                                                │
│   │ ContextAnalyzer │  6 场景 (code/chat/document/research/email/    │
│   │                 │  terminal) + URL/email/file 提取                │
│   └────────┬────────┘                                                │
│            │ Context                                                 │
│            ▼                                                         │
│   ┌─────────────────┐    ┌─────────────────┐                         │
│   │ MemoryStore     │◀──▶│ IntentPredictor │  LLM + SCENARIO_HEURISTIC│
│   └────────┬────────┘    └────────┬────────┘                         │
│            │                      │ Intent                            │
│            │                      ▼                                   │
│            │           ┌─────────────────┐                           │
│            │           │ _decide_action  │  intent → Action 映射     │
│            │           └────────┬────────┘                           │
│            │                    │ Action                             │
│            │                    ▼                                   │
│            │           ┌─────────────────┐                           │
│            └──────────▶│ ActionExecutor  │  7 types (summarize/      │
│                        └────────┬────────┘  reply/organize/search/  │
│                                 │             remind/draft/analyze)  │
│                                 ▼                                   │
│                         ActionResult                                 │
│                                                                      │
│   perceive_and_act(user_id) ─── capture → analyze → load memory →    │
│                                  predict → decide → execute → save →│
│                                  generate_daily_report               │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 关键决策点

| 决策 | 选择 | 理由 |
|---|---|---|
| 异步 vs 同步 | **async/await** | ScreenCapture 涉及阻塞 IO (win32gui); 编排多组件适合 asyncio |
| 持久化 | **JSON 文件** | 任务约束: 无 SQLite/Postgres 要求; atomic write via tmp + os.replace |
| LLM 集成 | **DI 注入 + heuristic fallback** | 测试可绕过 LLM (MockLLM); 生产可注入真实 LLM |
| EventBus | **imdf.orchestration.bus.EventBus** | 与项目内其他引擎 (octo/meta_kim 等) 一致 |
| Skill 注册 | **VidaSkillSpec dataclass** | 与 RedFoxSkillSpec 同构, 统一查询接口 |

---

## 3. E2E 示例: "user opens vscode with Python file"

### 3.1 输入场景

```python
# 用户打开 vscode 编辑 main.py
screen = ScreenCapture(mode="mock", mock_app="vscode", mock_window="main.py - nanobot-factory")
context_analyzer = ContextAnalyzer()  # 用 default keyword table
intent_predictor = IntentPredictor(heuristic_only=True)  # 不依赖 LLM
action_executor = ActionExecutor()
memory_store = AgentMemoryStore(root_dir=".vida_memory")
bus = EventBus()

engine = VidaEngine(screen, context_analyzer, intent_predictor, action_executor, memory_store, bus)

result = await engine.perceive_and_act(user_id="alice")
```

### 3.2 执行过程

```
[1] screen_capture.capture()
    → ScreenData(active_app="vscode", active_window_title="vscode — main.py - nanobot-factory",
                 platform="mock-win32", width=1920, height=1080)
    → bus: vida.screen_captured

[2] context_analyzer.analyze(screen, user_id="alice")
    → Context(app="vscode", scenario=Scenario.CODE,
              text="", key_info={"urls":[], "emails":[], "files":[]},
              language="en", user_id="alice")
    → bus: vida.context_analyzed

[3] memory_store.load("alice")
    → {"user_id": "alice", "preferences": {}, "history": []}

[4] intent_predictor.predict(context, memory)
    → Intent(intent_type=IntentType.WRITE_CODE,
             confidence=0.85,            # heuristic for CODE scenario
             suggested_action=ActionType.SUMMARIZE,
             rationale="heuristic: scenario=code → intent=write_code action=summarize")
    → bus: vida.intent_predicted (confidence=0.85 > threshold 0.7 ✓)

[5] intent.confidence (0.85) > threshold (0.7) → 执行
    → _decide_action(intent, context)
       Action(action_type=ActionType.SUMMARIZE,
              parameters={"intent_id":"int_xxx", "scenario":"code",
                          "app":"vscode", "content":"", "length":"short"})

[6] action_executor.execute(action)
    → ActionResult(success=True, status=COMPLETED,
                   result={"summary": "[mock-summary | short] ", "length":"short",
                           "src_chars": 0},
                   duration_ms=2)

[7] memory_store.save("alice", action, result)
    → append to .vida_memory/alice/memory.json (atomic write)

[8] generate_daily_report("alice")
    → Report(date="2026-07-02", completed_count=1, in_progress_count=0, failed_count=0,
             completed_items=[{"title":"summarize", "result":{...}}],
             key_words=["summarize"], tomorrow_plan=["Continue current workflow patterns"],
             time_distribution={"20": 1})
    → bus: vida.daily_report_generated
```

### 3.3 最终返回

```python
{
    "context": Context(scenario=CODE, app="vscode", ...),
    "intent":  Intent(intent_type=WRITE_CODE, confidence=0.85, ...),
    "screen":  ScreenData(active_app="vscode", ...),
    "action":  Action(action_type=SUMMARIZE, ...),
    "result":  ActionResult(success=True, status=COMPLETED, ...),
}
```

### 3.4 验证 confidence ≤ 0.7 不执行

```python
# 注入一个返回低 confidence 的 MockLLM
llm = MockLLM(confidence=0.5, intent_type=IntentType.OTHER, action_type=ActionType.SUMMARIZE)
predictor = IntentPredictor(llm=llm)
engine = VidaEngine(..., intent_predictor=predictor, ...)

result = await engine.perceive_and_act(user_id="bob")
assert result["action"] is None   # ✓ 不执行
assert result["result"] is None   # ✓
assert engine.status()["stats"]["actions_skipped_low_confidence"] >= 1
```

---

## 4. 测试结果

```
$ D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/intelligence/vida/tests/test_vida.py -v --tb=short

collected 41 items

TestScreenCapture::test_capture_mock_mode                    PASSED
TestScreenCapture::test_set_mock_target                      PASSED
TestScreenCapture::test_capture_increments_count             PASSED
TestContextAnalyzer::test_scenario_code                      PASSED
TestContextAnalyzer::test_scenario_chat                      PASSED
TestContextAnalyzer::test_scenario_document                  PASSED
TestContextAnalyzer::test_scenario_research                  PASSED
TestContextAnalyzer::test_scenario_email                     PASSED
TestContextAnalyzer::test_scenario_terminal                  PASSED
TestContextAnalyzer::test_text_truncate                      PASSED
TestContextAnalyzer::test_email_extraction                   PASSED
TestContextAnalyzer::test_url_extraction                     PASSED
TestContextAnalyzer::test_scenario_override                  PASSED
TestIntentPredictor::test_heuristic_only_code                PASSED
TestIntentPredictor::test_heuristic_only_email               PASSED
TestIntentPredictor::test_mock_llm                           PASSED
TestIntentPredictor::test_heuristic_all_scenarios            PASSED
TestActionExecutor::test_summarize                           PASSED
TestActionExecutor::test_reply                               PASSED
TestActionExecutor::test_organize                            PASSED
TestActionExecutor::test_search                              PASSED
TestActionExecutor::test_remind                              PASSED
TestActionExecutor::test_draft                               PASSED
TestActionExecutor::test_analyze_with_numbers                PASSED
TestActionExecutor::test_unknown_action_type_fails_gracefully PASSED
TestMemoryStore::test_save_load_roundtrip                    PASSED
TestMemoryStore::test_load_missing_user_returns_empty        PASSED
TestMemoryStore::test_get_today_actions                      PASSED
TestMemoryStore::test_set_preferences                        PASSED
TestVidaEngine::test_perceive_and_act_high_confidence_executes_action  PASSED
TestVidaEngine::test_perceive_and_act_low_confidence_no_action         PASSED
TestVidaEngine::test_perceive_and_act_saves_to_memory        PASSED
TestVidaEngine::test_generate_daily_report                   PASSED
TestVidaEngine::test_status_includes_components              PASSED
TestVidaSkillRegistry::test_vida_proactive_assist_registered PASSED
TestVidaSkillRegistry::test_get_vida_skill_returns_spec      PASSED
TestVidaSkillRegistry::test_get_unknown_vida_skill_raises    PASSED
TestSchemas::test_screen_data_defaults                       PASSED
TestSchemas::test_intent_confidence_validation               PASSED
TestSchemas::test_action_result_serializable                 PASSED
TestScenarioHeuristic::test_all_scenarios_have_heuristic     PASSED

======================== 41 passed, 1 warning in 0.56s ========================
```

---

## 5. Skill Registry 集成

新增 `vida_proactive_assist` Skill:

```python
from backend.imdf.skills import list_vida_skills, get_vida_skill

skills = list_vida_skills()  # 1 个
# [VidaSkillSpec(skill_id='vida_proactive_assist', name='Vida Proactive Assist', ...)]

spec = get_vida_skill('vida_proactive_assist')
spec.trigger_phrases
# ['proactive assist', 'screen aware', 'what should i do next', '主动助手', '下一步', 'vida']
spec.dependencies
# ['imdf.intelligence.vida.ScreenCapture',
#  'imdf.intelligence.vida.ContextAnalyzer',
#  'imdf.intelligence.vida.IntentPredictor',
#  'imdf.intelligence.vida.ActionExecutor',
#  'imdf.intelligence.vida.AgentMemoryStore',
#  'imdf.engines.vida_engine.VidaEngine',
#  'imdf.orchestration.bus.EventBus']

# 直接调用
from backend.imdf.skills import _run_vida_skill
result = _run_vida_skill(user_id="alice")
# {'scenario': 'code', 'app': 'vscode', 'intent_type': 'write_code',
#  'confidence': 0.85, 'action_type': 'summarize', 'action_executed': True}
```

---

## 6. 完成度对照

| 任务要求 | 状态 | 说明 |
|---|---|---|
| 1. `vida_engine.py` (DI + perceive_and_act + generate_daily_report) | ✅ | 336 LOC, async, 完整主循环 |
| 2. `screen_capture.py` (multi-platform + mock) | ✅ | 197 LOC, win/mac/linux + mock + auto fallback |
| 3. `context_analyzer.py` (6 scenarios) | ✅ | 168 LOC, code/chat/document/research/email/terminal |
| 4. `intent_predictor.py` (LLM + heuristic) | ✅ | 162 LOC, LLM 注入 + MockLLM + heuristic fallback |
| 5. `action_executor.py` (7 action types) | ✅ | 170 LOC, summarize/reply/organize/search/remind/draft/analyze |
| 6. `memory_store.py` (load/save) | ✅ | 159 LOC, JSON + atomic write + today filter |
| 7. `schemas.py` (Pydantic v2) | ✅ | 172 LOC, 6 models + 3 enums |
| 8. `tests/test_vida.py` (≥12 tests) | ✅ | 41 tests, 全部通过 |
| 9. `skills/registry.py` 注册 `vida_proactive_assist` | ✅ | VidaSkillSpec + VIDA_SKILLS |
| 10. `reports/p19_v53_vida.md` + E2E example | ✅ | 本文件 |

**100% 完成**,所有 hard rule 满足:
- ✅ 25min 预算 (实际 ~17min)
- ✅ 所有 platform-specific 代码 mock 化
- ✅ 用 `D:\ComfyUI\.ext\python.exe -m pytest` 测试
- ✅ Pydantic v2 (`model_config = ConfigDict`)

---

## 7. 已知限制与后续工作

1. **真实屏幕抓拍**: 当前依赖可选库 (pywin32, pyautogui, AppKit)。生产部署需要确保
   平台依赖正确安装。
2. **OCR**: ContextAnalyzer 默认从 `ScreenData.extra["text"]` 取文本 — 真实部署需要
   OCR pipeline (Tesseract / PaddleOCR)。当前保留 `text_extractor` 注入点。
3. **real LLM**: 当前测试用 `MockLLM`。生产应该注入真实的 LLM provider (例如
   `imdf.engines.model_gateway.LLMProvider`)。
4. **多用户隔离**: memory_store 已经按 user_id 分目录存储; 生产需要确保 user_id
   来自身份验证而非用户输入。
5. **P19-B4 dataclass 版**: 之前的 `vida_engine.py` (dataclass + MCP cu 集成) 已被
   替换。如果需要回退,git 历史可恢复。