"""Tests for :mod:`engines.meta_kim_engine` (P19 v5.3 — V5 Chapter 27).

Exercises the 7-step governance loop:

    Clarify → Search → Select → Split → Execute → Verify → Learn

The LLM provider, capability registry, octo engine, and event bus are all
mocked so the suite is hermetic and deterministic.  We assert:

* Each step produces the right typed model (Intent / Capability / Task / …)
* End-to-end ``govern_run`` returns a populated :class:`GovernedRun`
* The 4 verify criteria each behave correctly
* Successful runs create a Skill; failed runs append to FailureKnowledgeBase
* The bus records a ``meta_kim.run_completed`` event
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from engines.meta_kim_engine import (
    CapabilityRegistryLike,
    MetaKimEngine,
    OctoEngineLike,
    BusLike,
)
from engines.meta_kim_kb import FailureKnowledgeBase, RunHistoryStore
from engines.meta_kim_schemas import (
    Capability,
    GovernedReport,
    GovernedRun,
    Intent,
    IntentType,
    Lesson,
    LessonType,
    OwnerKind,
    Task,
    TaskExecution,
    VerifyCriterion,
    VerifyCriterionType,
    VerifiedResult,
)
from engines.meta_kim_skill_writer import MetaKimSkillWriter, StubSkillEngine


# --------------------------------------------------------------------------- #
# Mocks
# --------------------------------------------------------------------------- #
class MockLLM:
    """Deterministic LLM provider that returns a pre-canned response."""

    def __init__(self, response: str = "{}") -> None:
        self.response = response
        self.calls: List[str] = []

    async def complete(self, prompt: str, *, response_format: str = "json",
                        temperature: float = 0.2) -> str:
        self.calls.append(prompt)
        return self.response


def _make_clarify_response(intent_type: str = "data_acquisition",
                             description: str = "process 100k images",
                             criteria: Optional[List[Dict[str, Any]]] = None) -> str:
    return json.dumps({
        "intent_type": intent_type,
        "description": description,
        "success_standard": {"criteria": criteria or [
            {"type": "count_check", "min_count": 1, "description": "at least one task"},
        ]},
        "constraints": {"max_duration_min": 30},
        "clarifying_questions": [],
        "confidence": 0.85,
    })


def _make_split_response(n_tasks: int = 3) -> str:
    tasks = [
        {
            "name": f"step_{i}",
            "description": f"do step {i}",
            "capability_id": f"cap.step_{i}",
            "dependencies": [f"step_{i-1}"] if i > 0 else [],
            "estimated_duration_min": 5,
            "inputs": {"stage": i},
        }
        for i in range(n_tasks)
    ]
    return json.dumps({"tasks": tasks})


@dataclass
class MockCapability:
    id: str
    name: str = ""
    category: str = "general"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    owner: str = "platform"
    invoke: Optional[Any] = None


class MockCapabilityRegistry(CapabilityRegistryLike):
    def __init__(self, caps: Optional[List[MockCapability]] = None) -> None:
        self._caps: Dict[str, MockCapability] = {
            c.id: c for c in (caps or [])
        }

    def register(self, cap: MockCapability) -> None:
        self._caps[cap.id] = cap

    def list_all(self) -> List[MockCapability]:
        return list(self._caps.values())

    def search(self, q: str) -> List[MockCapability]:
        if not q:
            return list(self._caps.values())
        return [c for c in self._caps.values()
                if q.lower() in c.id.lower() or q.lower() in (c.description or "").lower()]

    def get(self, cap_id: str) -> Optional[MockCapability]:
        return self._caps.get(cap_id)


@dataclass
class MockOctoBot:
    bot_id: str
    name: str = "bot"
    capabilities: List[str] = field(default_factory=list)
    workload: int = 0


class MockOctoEngine(OctoEngineLike):
    def __init__(self, bots: Optional[List[MockOctoBot]] = None) -> None:
        self._bots = list(bots or [])
        self._matters: Dict[str, Dict[str, Any]] = {}

    def list_bots(self) -> List[MockOctoBot]:
        return list(self._bots)

    def get_bots_by_capability(self, capability_ids: List[str]) -> List[MockOctoBot]:
        ids = set(capability_ids)
        return [b for b in self._bots
                if any(c in ids for c in b.capabilities)]

    def create_matter(self, title: str, body: str = "") -> str:
        mid = f"m_{len(self._matters)+1}"
        self._matters[mid] = {"title": title, "body": body, "answer": {}}
        return mid

    def execute_collab(self, mode: Any, matter_id: str,
                       bot_ids: Optional[List[str]] = None, *,
                       channel_id: Optional[str] = None) -> Any:
        matter = self._matters.get(matter_id)
        if not matter:
            raise KeyError(matter_id)
        matter["answer"] = {"echo": matter["body"], "by": "octo"}
        return SimpleNamespace(output=matter["answer"])


class MockBus(BusLike):
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def record(self, topic: str, entity_type: str = "", entity_id: str = "",
               payload: Optional[Dict[str, Any]] = None, actor: str = "system",
               refs: Optional[Dict[str, str]] = None,
               source_module: str = "") -> int:
        self.events.append({
            "topic": topic, "entity_type": entity_type,
            "entity_id": entity_id, "payload": payload or {},
            "actor": actor, "source_module": source_module,
        })
        return len(self.events)


from types import SimpleNamespace


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _make_engine(
    *,
    caps: Optional[List[MockCapability]] = None,
    llm: Optional[MockLLM] = None,
    octo: Optional[MockOctoEngine] = None,
    bus: Optional[MockBus] = None,
    failure_kb: Optional[FailureKnowledgeBase] = None,
    run_history: Optional[RunHistoryStore] = None,
    skill_writer: Optional[MetaKimSkillWriter] = None,
) -> MetaKimEngine:
    return MetaKimEngine(
        capability_registry=MockCapabilityRegistry(caps or []),
        octo_engine=octo,
        llm=llm,
        bus=bus,
        failure_kb=failure_kb,
        run_history=run_history,
        skill_writer=skill_writer,
    )


# =========================================================================== #
# 1. Schema + KB + SkillWriter unit tests (3 tests)
# =========================================================================== #
class TestSchemas:
    def test_intent_defaults_and_validation(self):
        intent = Intent(intent_type=IntentType.DATA_CLEANING, description="clean")
        assert intent.intent_type == IntentType.DATA_CLEANING
        assert intent.confidence == 1.0  # clamped
        assert intent.clarifying_questions == []

    def test_intent_confidence_clamped(self):
        intent = Intent(intent_type=IntentType.ANNOTATION, confidence=5.0)
        assert intent.confidence == 1.0

    def test_task_defaults(self):
        t = Task(name="x", description="y")
        assert t.status == "pending"
        assert t.dependencies == []
        assert t.task_id.startswith("task_")


class TestKB:
    def test_failure_kb_append_and_list(self, tmp_path):
        path = str(tmp_path / "fk.json")
        kb = FailureKnowledgeBase(persist_path=path)
        rid = kb.append(run_id="r1", failure="OOM", suggestion="retry", tags=["oom"])
        assert rid.startswith("fail_")
        assert kb.count() == 1
        # reload
        kb2 = FailureKnowledgeBase(persist_path=path)
        assert kb2.count() == 1
        assert kb2.search(query="oom")[0]["suggestion"] == "retry"

    def test_failure_kb_rejects_empty(self):
        kb = FailureKnowledgeBase()
        with pytest.raises(ValueError):
            kb.append(run_id="x", failure="")

    def test_run_history_append_and_get(self, tmp_path):
        path = str(tmp_path / "rh.json")
        store = RunHistoryStore(persist_path=path)
        rid = store.append({"id": "gov_1", "succeeded": True, "intent": "test"})
        assert rid == "gov_1"
        assert store.get("gov_1")["succeeded"] is True
        assert store.count() == 1


class TestSkillWriter:
    def test_stub_skill_engine_creates_skill(self):
        eng = StubSkillEngine()
        writer = MetaKimSkillWriter(eng)
        lesson = {
            "type": "success",
            "name": "auto_pipe",
            "description": "auto pipeline",
            "steps": [{"name": "a"}],
            "trigger_phrases": ["pipe"],
        }
        rec = writer.write_skill_from_lesson(lesson, intent={"intent_type": "x"}, run_id="r1")
        assert rec is not None
        assert rec.name == "auto_pipe"
        assert rec.skill_id.startswith("skill_")
        # Failure lessons never create skills
        rec_fail = writer.write_skill_from_lesson({"type": "failure"})
        assert rec_fail is None


# =========================================================================== #
# 2. Each of the 7 governance steps (7 tests)
# =========================================================================== #
class TestClarifyStep:
    def test_clarify_with_mock_llm(self):
        llm = MockLLM(response=_make_clarify_response(
            intent_type="annotation", description="label 100 images",
        ))
        engine = _make_engine(llm=llm)
        intent = _run(engine._clarify_intent(request="label 100 images", context={}))
        assert intent.intent_type == IntentType.ANNOTATION
        assert intent.description == "label 100 images"
        assert intent.confidence == 0.85
        assert llm.calls, "LLM should have been called"


class TestSearchStep:
    def test_search_with_registry(self):
        caps = [
            MockCapability(id="cap.clean", name="clean", description="data cleaning",
                            tags=["cleaning"]),
            MockCapability(id="cap.crawl", name="crawl", description="data crawl",
                            tags=["acquisition"]),
        ]
        engine = _make_engine(caps=caps)
        intent = Intent(intent_type=IntentType.DATA_CLEANING, description="clean images")
        results = _run(engine._search_capabilities(intent=intent))
        assert results, "should return at least one capability"
        assert all(isinstance(c, Capability) for c in results)
        assert all(0.0 <= c.relevance_score <= 1.0 for c in results)


class TestSelectStep:
    def test_select_owner_auto_when_no_octo(self):
        engine = _make_engine(caps=[MockCapability(id="cap.x", name="x")])
        owner = _run(engine._select_owner(
            capabilities=[Capability(capability_id="cap.x", name="x", automatable=True)],
            intent=Intent(intent_type=IntentType.UNKNOWN, description="x"),
        ))
        assert owner == OwnerKind.AUTO

    def test_select_owner_human_required_when_no_capabilities(self):
        engine = _make_engine()
        owner = _run(engine._select_owner(
            capabilities=[],
            intent=Intent(intent_type=IntentType.UNKNOWN, description="ambiguous"),
        ))
        assert owner == OwnerKind.HUMAN_REQUIRED


class TestSplitStep:
    def test_split_with_mock_llm(self):
        llm = MockLLM(response=_make_split_response(n_tasks=4))
        engine = _make_engine(llm=llm)
        tasks = _run(engine._split_tasks(
            intent=Intent(intent_type=IntentType.DATA_CLEANING, description="clean"),
            capabilities=[],
        ))
        assert len(tasks) == 4
        assert all(isinstance(t, Task) for t in tasks)
        assert tasks[1].dependencies == ["step_0"]


class TestExecuteStep:
    def test_execute_stub_path(self):
        engine = _make_engine(caps=[])
        tasks = [Task(name="a", description="x", capability_id=None),
                 Task(name="b", description="y", capability_id=None)]
        results = _run(engine._execute_tasks(tasks=tasks, owner=OwnerKind.AUTO))
        assert len(results) == 2
        assert all(r.status == "success" for r in results)
        assert results[0].output["via"] == "stub"


class TestVerifyStep:
    @pytest.mark.parametrize("criterion_type,expected_ok", [
        (VerifyCriterionType.COUNT_CHECK, True),
        (VerifyCriterionType.AUTOMATED_TEST, True),
        (VerifyCriterionType.QUALITY_THRESHOLD, True),
        (VerifyCriterionType.HUMAN_REVIEW, False),
    ])
    def test_verify_each_criterion(self, criterion_type, expected_ok):
        engine = _make_engine()
        results = [TaskExecution(task_id="t1", task_name="t1", status="success")]
        verified = _run(engine._verify_results(
            results=results,
            criteria=[VerifyCriterion(type=criterion_type, description="t", min_count=1)],
            intent=Intent(intent_type=IntentType.UNKNOWN),
        ))
        if criterion_type == VerifyCriterionType.HUMAN_REVIEW:
            assert verified.requires_human_review is True
            assert verified.succeeded is False
        else:
            assert verified.succeeded is expected_ok


class TestLearnStep:
    def test_learn_success_creates_skill(self):
        eng = StubSkillEngine()
        writer = MetaKimSkillWriter(eng)
        engine = _make_engine(skill_writer=writer)
        verified = VerifiedResult(succeeded=True, message="ok", score=1.0)
        intent = Intent(intent_type=IntentType.DATA_CLEANING, description="clean")
        lessons = engine._extract_lessons(
            verified=verified, intent=intent,
            tasks=[Task(name="t1")], results=[], run_id="r1",
        )
        assert len(lessons) == 1
        assert lessons[0].type == LessonType.SUCCESS
        # Now write-back
        _run(engine._write_back_lessons(
            lessons=lessons, intent=intent, run_id="r1", verified=verified,
        ))
        assert len(writer.created_skills) == 1

    def test_learn_failure_records_to_kb(self, tmp_path):
        kb = FailureKnowledgeBase(persist_path=str(tmp_path / "fk.json"))
        engine = _make_engine(failure_kb=kb)
        verified = VerifiedResult(succeeded=False, message="bad",
                                   failures=["Quality below threshold: 0.5 < 0.9"])
        intent = Intent(intent_type=IntentType.ANNOTATION, description="label")
        lessons = engine._extract_lessons(
            verified=verified, intent=intent,
            tasks=[Task(name="t1")], results=[], run_id="r2",
        )
        assert lessons[0].type == LessonType.FAILURE
        _run(engine._write_back_lessons(
            lessons=lessons, intent=intent, run_id="r2", verified=verified,
        ))
        assert kb.count() == 1
        assert "Quality" in kb.list()[0]["failure"]


# =========================================================================== #
# 3. End-to-end govern_run (1 test)
# =========================================================================== #
class TestGovernRunE2E:
    def test_e2e_100k_images_pipeline(self):
        """The canonical example from the task brief."""
        llm = MockLLM(response=json.dumps({
            "intent_type": "data_acquisition",
            "description": "process this batch of 100k images",
            "success_standard": {"criteria": [
                {"type": "count_check", "min_count": 6, "description": "all 6 stages"},
            ]},
            "constraints": {"max_duration_min": 60},
            "clarifying_questions": [],
            "confidence": 0.95,
        }))
        bus = MockBus()
        engine = _make_engine(
            caps=[
                MockCapability(id="cap.crawl", name="crawl", description="crawl images"),
                MockCapability(id="cap.dedupe", name="dedupe", description="dedupe"),
                MockCapability(id="cap.clean", name="clean", description="clean"),
                MockCapability(id="cap.label", name="label", description="label"),
                MockCapability(id="cap.qc", name="qc", description="quality check"),
                MockCapability(id="cap.export", name="export", description="export"),
            ],
            llm=llm,
            bus=bus,
        )

        run = _run(engine.govern_run("process this batch of 100k images"))
        assert isinstance(run, GovernedRun)
        assert run.request == "process this batch of 100k images"
        # Intent classified
        assert run.intent is not None
        assert run.intent.intent_type == IntentType.DATA_ACQUISITION
        # Capabilities surfaced
        assert run.capabilities, "search step should return candidates"
        # Tasks split (stub) — 6 stages per the brief
        assert len(run.tasks) == 6
        task_names = [t.name for t in run.tasks]
        assert task_names == ["crawl", "dedupe", "clean", "label", "qc", "export"]
        # All tasks executed successfully (stub path)
        assert all(r.status == "success" for r in run.results)
        # Verify succeeded
        assert run.verified is not None
        assert run.verified.succeeded is True
        # Learn produced a skill
        assert len(run.lessons) == 1
        assert run.lessons[0].type == LessonType.SUCCESS
        # Skill was actually written
        assert len(engine.skill_writer.created_skills) == 1
        created = engine.skill_writer.created_skills[0]
        assert "pipeline" in created.name or "data_acquisition" in created.name
        # Report + run history + bus emit
        assert run.report is not None
        assert run.report.succeeded is True
        assert run.report.skill_created == run.lessons[0].content.get("name")
        assert engine.run_history.count() == 1
        # Bus event emitted
        topics = [e["topic"] for e in bus.events]
        assert "meta_kim.run_completed" in topics


# =========================================================================== #
# 4. Failure path e2e (1 test)
# =========================================================================== #
class TestGovernRunFailure:
    def test_e2e_failure_records_to_kb(self, tmp_path):
        # Make verify fail by including a HUMAN_REVIEW criterion
        llm = MockLLM(response=json.dumps({
            "intent_type": "export",
            "description": "export dataset",
            "success_standard": {"criteria": [
                {"type": "human_review", "description": "manual approval"},
            ]},
            "confidence": 0.6,
        }))
        bus = MockBus()
        kb = FailureKnowledgeBase(persist_path=str(tmp_path / "fk.json"))
        engine = _make_engine(
            caps=[MockCapability(id="cap.export", name="export")],
            llm=llm, bus=bus, failure_kb=kb,
        )

        run = _run(engine.govern_run("export dataset to cloud"))
        assert run.verified is not None
        assert run.verified.succeeded is False
        assert run.verified.requires_human_review is True
        # Failure lessons produced + written to KB
        assert all(l.type == LessonType.FAILURE for l in run.lessons)
        assert kb.count() == len(run.lessons)
        # Bus event still emitted (with success=False)
        last = bus.events[-1]
        assert last["payload"]["success"] is False


# =========================================================================== #
# 5. Misc (status, embedding fallback, owner probe, etc.) (4 tests)
# =========================================================================== #
class TestMisc:
    def test_status_reports_subsystems(self):
        engine = _make_engine(llm=MockLLM())
        s = engine.status()
        assert "runs" in s and "failures_recorded" in s
        assert s["has_llm"] is True
        assert s["has_octo_engine"] is False

    def test_hash_embedding_deterministic(self):
        from engines.meta_kim_engine import _hash_embedding, _cosine
        a = _hash_embedding("hello world")
        b = _hash_embedding("hello world")
        assert a == b
        assert 0.99 < _cosine(a, b) <= 1.0001

    def test_owner_probe_via_octo(self):
        # Bot present → owner = BOT (octo path)
        bot = MockOctoBot(bot_id="b1", name="b1", capabilities=["cap.x"])
        octo = MockOctoEngine(bots=[bot])
        engine = _make_engine(
            caps=[MockCapability(id="cap.x", name="x")],
            octo=octo,
        )
        owner = _run(engine._select_owner(
            capabilities=[Capability(capability_id="cap.x", name="x", automatable=True)],
            intent=Intent(intent_type=IntentType.UNKNOWN, description="x"),
        ))
        assert owner == OwnerKind.BOT

    def test_skill_writer_receives_real_engine(self):
        # When the engine is wired with a stub skill_writer + no engine,
        # skills still get created via the stub.
        eng = MetaKimEngine(skill_engine=StubSkillEngine())
        lesson = {
            "type": "success", "name": "x", "description": "x",
            "steps": [], "trigger_phrases": [],
        }
        rec = eng._skill_writer.write_skill_from_lesson(lesson)
        assert rec is not None
        assert rec.skill_id.startswith("skill_")


# =========================================================================== #
# 6. Edge cases
# =========================================================================== #
class TestEdgeCases:
    def test_empty_request_returns_unknown_intent(self):
        engine = _make_engine()
        run = _run(engine.govern_run(""))
        assert run.intent.intent_type == IntentType.UNKNOWN

    def test_llm_failure_falls_back_to_stub(self):
        class BoomLLM:
            async def complete(self, *args, **kwargs):
                raise RuntimeError("LLM unavailable")
        engine = _make_engine(llm=BoomLLM())
        # Should NOT raise — falls back to stub
        run = _run(engine.govern_run("clean this dataset"))
        assert run.intent.intent_type == IntentType.DATA_CLEANING  # heuristic

    def test_intent_classifier_chinese(self):
        engine = _make_engine()
        assert engine._classify_intent_heuristic("请帮我清洗数据") == IntentType.DATA_CLEANING
        assert engine._classify_intent_heuristic("采集图像") == IntentType.DATA_ACQUISITION
        assert engine._classify_intent_heuristic("导出数据") == IntentType.EXPORT
        assert engine._classify_intent_heuristic("wat") == IntentType.UNKNOWN

    def test_verify_empty_results(self):
        engine = _make_engine()
        verified = _run(engine._verify_results(
            results=[], criteria=[],
            intent=Intent(intent_type=IntentType.UNKNOWN),
        ))
        assert verified.succeeded is False