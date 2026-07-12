"""P19-V53: Vida tests — ≥12 tests covering all 6 modules + end-to-end.

Test plan:
  * ScreenCapture     — 2 tests (mock mode, set_mock_target)
  * ContextAnalyzer   — 6 tests (one per scenario) + key_info extraction
  * IntentPredictor   — 3 tests (heuristic, mock LLM, JSON parse fallback)
  * ActionExecutor    — 7 tests (one per action_type)
  * MemoryStore       — 2 tests (save/load round-trip, get_today_actions)
  * VidaEngine (E2E)  — 2 tests (high confidence → action; low confidence → no action)
  * DailyReport       — 1 test (full aggregation)
  * Skills registry   — 1 test (vida_proactive_assist registered)

Total ≥ 12 (actually ~24).
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest


# ── Imports under test ─────────────────────────────────────────────────
from imdf.intelligence.vida import (  # noqa: E402
    Action,
    ActionExecutor,
    ActionResult,
    ActionStatus,
    ActionType,
    AgentMemoryStore,
    Context,
    ContextAnalyzer,
    Intent,
    IntentPredictor,
    IntentType,
    MockLLM,
    Report,
    Scenario,
    ScreenCapture,
    ScreenData,
)
from imdf.intelligence.vida.intent_predictor import SCENARIO_HEURISTIC
from imdf.engines.vida_engine import VidaEngine, CONFIDENCE_THRESHOLD


# ── Shared fixtures ────────────────────────────────────────────────────
@pytest.fixture
def tmp_memory_dir():
    """临时目录 — 每个 test 独立的 memory root."""
    with tempfile.TemporaryDirectory(prefix="vida_test_") as d:
        yield d


def _run(coro):
    """同步运行 async coro — 简化测试."""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  1. ScreenCapture (mocked)                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestScreenCapture:
    def test_capture_mock_mode(self):
        cap = ScreenCapture(mode="mock", mock_app="vscode", mock_window="main.py")
        data = _run(cap.capture())
        assert isinstance(data, ScreenData)
        assert data.active_app == "vscode"
        assert "main.py" in data.active_window_title
        assert data.platform.startswith("mock")
        assert data.width > 0 and data.height > 0

    def test_set_mock_target(self):
        cap = ScreenCapture(mode="mock")
        cap.set_mock_target("chrome", "GitHub - repo")
        data = _run(cap.capture())
        assert data.active_app == "chrome"
        assert "GitHub" in data.active_window_title

    def test_capture_increments_count(self):
        cap = ScreenCapture(mode="mock")
        d1 = _run(cap.capture())
        d2 = _run(cap.capture())
        # screen_id 应该不同
        assert d1.screen_id != d2.screen_id


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  2. ContextAnalyzer — 6 scenarios                                   ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestContextAnalyzer:
    def _analyze(self, app: str, text: str = "") -> Context:
        analyzer = ContextAnalyzer()
        screen = ScreenData(active_app=app, active_window_title=app, extra={"text": text})
        return _run(analyzer.analyze(screen, user_id="u1"))

    def test_scenario_code(self):
        ctx = self._analyze("vscode", "def foo(): pass")
        assert ctx.scenario == Scenario.CODE
        # code 场景的 key_info 应包含 code_symbols
        assert "code_symbols" in ctx.key_info
        assert "foo" in ctx.key_info["code_symbols"]

    def test_scenario_chat(self):
        ctx = self._analyze("wechat")
        assert ctx.scenario == Scenario.CHAT

    def test_scenario_document(self):
        ctx = self._analyze("notion")
        assert ctx.scenario == Scenario.DOCUMENT

    def test_scenario_research(self):
        ctx = self._analyze("chrome", "https://example.com/article")
        assert ctx.scenario == Scenario.RESEARCH
        assert ctx.key_info.get("page_url") == "https://example.com/article"

    def test_scenario_email(self):
        ctx = self._analyze("outlook", "Subject: Q4 planning")
        assert ctx.scenario == Scenario.EMAIL
        assert ctx.key_info.get("subject") == "Q4 planning"

    def test_scenario_terminal(self):
        ctx = self._analyze("powershell", "$ ls -la")
        assert ctx.scenario == Scenario.TERMINAL
        assert ctx.key_info.get("last_command") == "ls -la"

    def test_text_truncate(self):
        long_text = "x" * 1000
        ctx = self._analyze("vscode", long_text)
        assert len(ctx.text) == 500

    def test_email_extraction(self):
        ctx = self._analyze("vscode", "Contact me at hello@example.com or support@foo.org")
        assert "hello@example.com" in ctx.key_info["emails"]

    def test_url_extraction(self):
        ctx = self._analyze("vscode", "See https://github.com/test/repo and https://docs.example.com")
        urls = ctx.key_info["urls"]
        assert len(urls) == 2
        assert "https://github.com/test/repo" in urls

    def test_scenario_override(self):
        """scenario_overrides 必须传给 ContextAnalyzer 实例 — 不能在 _analyze 里新建."""
        analyzer = ContextAnalyzer(scenario_overrides={"my-app": Scenario.CHAT})
        screen = ScreenData(active_app="my-app", active_window_title="my-app")
        ctx = _run(analyzer.analyze(screen, user_id="u1"))
        assert ctx.scenario == Scenario.CHAT


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  3. IntentPredictor                                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestIntentPredictor:
    def test_heuristic_only_code(self):
        predictor = IntentPredictor(heuristic_only=True)
        ctx = Context(scenario=Scenario.CODE, app="vscode")
        intent = _run(predictor.predict(ctx, memory={}))
        assert intent.intent_type == IntentType.WRITE_CODE
        assert intent.confidence == SCENARIO_HEURISTIC[Scenario.CODE][2]
        assert intent.suggested_action == ActionType.SUMMARIZE

    def test_heuristic_only_email(self):
        predictor = IntentPredictor(heuristic_only=True)
        ctx = Context(scenario=Scenario.EMAIL, app="outlook")
        intent = _run(predictor.predict(ctx, memory={}))
        assert intent.intent_type == IntentType.EMAIL
        assert intent.suggested_action == ActionType.DRAFT
        assert intent.confidence > 0.7

    def test_mock_llm(self):
        llm = MockLLM(confidence=0.92, intent_type=IntentType.REPLY_MESSAGE,
                      action_type=ActionType.REPLY)
        predictor = IntentPredictor(llm=llm)
        ctx = Context(scenario=Scenario.CHAT, app="wechat")
        intent = _run(predictor.predict(ctx, memory={"history": "chat-heavy"}))
        assert llm.call_count == 1
        assert intent.intent_type == IntentType.REPLY_MESSAGE
        assert intent.confidence == 0.92
        assert intent.suggested_action == ActionType.REPLY
        # MockLLM 返回 "mock-LLM after N calls" — rationale 应非空
        assert intent.rationale
        assert "mock" in intent.rationale.lower()

    def test_heuristic_all_scenarios(self):
        """所有 6 个 scenario 都应能用 heuristic 预测."""
        predictor = IntentPredictor(heuristic_only=True)
        for scenario in Scenario:
            ctx = Context(scenario=scenario, app=scenario.value)
            intent = _run(predictor.predict(ctx, memory={}))
            assert intent.intent_type is not None
            assert 0 < intent.confidence <= 1.0


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  4. ActionExecutor — 7 action types                                 ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestActionExecutor:
    def _exec(self, action_type: ActionType, params: dict) -> ActionResult:
        executor = ActionExecutor()
        action = Action(action_type=action_type, parameters=params)
        return _run(executor.execute(action))

    def test_summarize(self):
        r = self._exec(ActionType.SUMMARIZE, {"content": "a long text", "length": "short"})
        assert r.success
        assert "summary" in r.result

    def test_reply(self):
        r = self._exec(ActionType.REPLY, {"message": "hello there", "n": 3})
        assert r.success
        assert r.result["count"] == 3
        assert len(r.result["replies"]) == 3

    def test_organize(self):
        r = self._exec(ActionType.ORGANIZE, {"files": ["a.py", "b.js", "c.py", "d.md"]})
        assert r.success
        assert r.result["total"] == 4
        assert "py" in r.result["groups"]
        assert len(r.result["groups"]["py"]) == 2

    def test_search(self):
        r = self._exec(ActionType.SEARCH, {"query": "python async"})
        assert r.success
        assert r.result["query"] == "python async"
        assert len(r.result["results"]) == 5

    def test_remind(self):
        r = self._exec(ActionType.REMIND, {"when": "in 30 min", "message": "standup"})
        assert r.success
        assert r.result["when"] == "in 30 min"
        assert r.result["message"] == "standup"
        assert "reminder_id" in r.result

    def test_draft(self):
        r = self._exec(ActionType.DRAFT, {"subject": "Hello", "template": "formal"})
        assert r.success
        assert r.result["subject"] == "Hello"
        assert "Hello" in r.result["body"]

    def test_analyze_with_numbers(self):
        r = self._exec(ActionType.ANALYZE, {"data": [1, 2, 3, 4, 5]})
        assert r.success
        assert r.result["count"] == 5
        assert r.result["avg"] == 3.0
        assert r.result["min"] == 1
        assert r.result["max"] == 5

    def test_unknown_action_type_fails_gracefully(self):
        """传不在 ActionType enum 里的字符串应当抛 ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Action(action_type="invalid_type", parameters={})


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  5. MemoryStore — save/load round-trip                              ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestMemoryStore:
    def test_save_load_roundtrip(self, tmp_memory_dir):
        store = AgentMemoryStore(root_dir=tmp_memory_dir)
        action = Action(action_type=ActionType.SUMMARIZE, parameters={"x": 1})
        result = ActionResult(success=True, status=ActionStatus.COMPLETED)
        _run(store.save("u1", action, result))

        loaded = _run(store.load("u1"))
        assert loaded["user_id"] == "u1"
        assert len(loaded["history"]) == 1
        entry = loaded["history"][0]
        assert entry["action"]["action_type"] == "summarize"
        assert entry["result"]["success"] is True

    def test_load_missing_user_returns_empty(self, tmp_memory_dir):
        store = AgentMemoryStore(root_dir=tmp_memory_dir)
        loaded = _run(store.load("ghost-user"))
        assert loaded["history"] == []
        assert loaded["preferences"] == {}

    def test_get_today_actions(self, tmp_memory_dir):
        store = AgentMemoryStore(root_dir=tmp_memory_dir)
        action = Action(action_type=ActionType.SEARCH)
        result = ActionResult(success=True, status=ActionStatus.COMPLETED)
        _run(store.save("u2", action, result))
        _run(store.save("u2", action, result))
        today = _run(store.get_today_actions("u2"))
        assert len(today) == 2

    def test_set_preferences(self, tmp_memory_dir):
        store = AgentMemoryStore(root_dir=tmp_memory_dir)
        _run(store.set_preferences("u3", {"language": "zh", "theme": "dark"}))
        loaded = _run(store.load("u3"))
        assert loaded["preferences"]["language"] == "zh"
        assert loaded["preferences"]["theme"] == "dark"


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  6. VidaEngine — end-to-end                                         ║
# ╚══════════════════════════════════════════════════════════════════════╝
def _make_engine(tmp_dir: str, mock_llm: MockLLM | None = None) -> VidaEngine:
    """构造一个完整的 mock VidaEngine."""
    from imdf.orchestration.bus import EventBus

    return VidaEngine(
        screen_capture=ScreenCapture(mode="mock", mock_app="vscode", mock_window="main.py"),
        context_analyzer=ContextAnalyzer(),
        intent_predictor=IntentPredictor(llm=mock_llm, heuristic_only=(mock_llm is None)),
        action_executor=ActionExecutor(),
        memory_store=AgentMemoryStore(root_dir=tmp_dir),
        bus=EventBus(),
    )


class TestVidaEngine:
    def test_perceive_and_act_high_confidence_executes_action(self, tmp_memory_dir):
        """code scenario + heuristic → confidence 0.85 > 0.7 → 应该执行 action."""
        engine = _make_engine(tmp_memory_dir)
        result = _run(engine.perceive_and_act(user_id="u1"))
        assert result["context"].scenario == Scenario.CODE
        assert result["intent"].intent_type == IntentType.WRITE_CODE
        assert result["intent"].confidence > 0.7
        assert result["action"] is not None
        assert result["action"].action_type == ActionType.SUMMARIZE
        assert result["result"] is not None
        assert result["result"].success is True

    def test_perceive_and_act_low_confidence_no_action(self, tmp_memory_dir):
        """confidence ≤ 0.7 → 不应执行 action."""
        llm = MockLLM(confidence=0.5, intent_type=IntentType.OTHER,
                      action_type=ActionType.SUMMARIZE)
        engine = _make_engine(tmp_memory_dir, mock_llm=llm)
        result = _run(engine.perceive_and_act(user_id="u2"))
        assert result["action"] is None
        assert result["result"] is None
        assert result["intent"].confidence == 0.5
        # stats should reflect skip
        st = engine.status()
        assert st["stats"]["actions_skipped_low_confidence"] >= 1

    def test_perceive_and_act_saves_to_memory(self, tmp_memory_dir):
        engine = _make_engine(tmp_memory_dir)
        _run(engine.perceive_and_act(user_id="u3"))
        # Memory file should now have an entry
        memory_path = Path(tmp_memory_dir) / "u3" / "memory.json"
        assert memory_path.exists()
        data = json.loads(memory_path.read_text(encoding="utf-8"))
        assert len(data["history"]) >= 1

    def test_generate_daily_report(self, tmp_memory_dir):
        engine = _make_engine(tmp_memory_dir)
        # 先跑几次 perceive_and_act 来填充 memory
        for _ in range(3):
            _run(engine.perceive_and_act(user_id="u4"))
        report = _run(engine.generate_daily_report(user_id="u4"))
        assert isinstance(report, Report)
        assert report.user_id == "u4"
        assert report.date  # YYYY-MM-DD
        assert report.completed_count >= 1
        assert len(report.completed_items) >= 1

    def test_status_includes_components(self, tmp_memory_dir):
        engine = _make_engine(tmp_memory_dir)
        st = engine.status()
        assert "components" in st
        assert st["components"]["screen_capture"] == "ScreenCapture"
        assert st["components"]["context_analyzer"] == "ContextAnalyzer"
        assert st["components"]["intent_predictor"] == "IntentPredictor"
        assert st["components"]["action_executor"] == "ActionExecutor"
        assert st["components"]["memory_store"] == "AgentMemoryStore"
        assert st["confidence_threshold"] == CONFIDENCE_THRESHOLD


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  7. Skills registry — vida_proactive_assist                         ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestVidaSkillRegistry:
    def test_vida_proactive_assist_registered(self):
        from imdf.skills import list_vida_skills, get_vida_skill

        skills = list_vida_skills()
        assert len(skills) >= 1
        ids = [s.skill_id for s in skills]
        assert "vida_proactive_assist" in ids

    def test_get_vida_skill_returns_spec(self):
        from imdf.skills import get_vida_skill

        spec = get_vida_skill("vida_proactive_assist")
        assert spec.skill_id == "vida_proactive_assist"
        assert spec.author == "vida"
        assert "屏幕感知" in spec.description or "屏幕" in spec.description
        assert len(spec.trigger_phrases) >= 3
        assert callable(spec.function_ref)

    def test_get_unknown_vida_skill_raises(self):
        from imdf.skills import get_vida_skill

        with pytest.raises(KeyError):
            get_vida_skill("nonexistent_skill_xyz")


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  8. Schemas validation                                               ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestSchemas:
    def test_screen_data_defaults(self):
        data = ScreenData()
        assert data.width == 1920
        assert data.height == 1080
        assert data.platform == "mock"

    def test_intent_confidence_validation(self):
        # Pydantic v2 — confidence should accept floats
        intent = Intent(confidence=0.85)
        assert intent.confidence == 0.85

    def test_action_result_serializable(self):
        r = ActionResult(success=True, status=ActionStatus.COMPLETED, result={"k": "v"})
        d = r.model_dump(mode="json")
        assert d["success"] is True
        assert d["status"] == "completed"
        assert d["result"] == {"k": "v"}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  9. Heuristic mapping completeness                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝
class TestScenarioHeuristic:
    def test_all_scenarios_have_heuristic(self):
        """SCENARIO_HEURISTIC 必须覆盖全部 6 个 Scenario."""
        for scenario in Scenario:
            assert scenario in SCENARIO_HEURISTIC, f"missing heuristic for {scenario}"
            intent_type, action_type, conf = SCENARIO_HEURISTIC[scenario]
            assert isinstance(intent_type, IntentType)
            assert isinstance(action_type, ActionType)
            assert 0 < conf <= 1.0