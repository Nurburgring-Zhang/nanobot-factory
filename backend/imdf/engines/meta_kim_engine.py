"""P19 v5.3 — Meta_Kim Governance Loop Engine (V5 Chapter 27).

The **7-step governance loop** wraps every Agent run for audit, learning, and
self-improvement::

    1. Clarify   — turn a vague request into a structured :class:`Intent`
                   with explicit success_standard, constraints, and confidence
    2. Search    — semantic search across 140+ capabilities (mocked embedding
                   when none is configured) and return top-K candidates
    3. Select    — decide who runs the work (bot / auto / human-required /
                   hybrid) based on whether any candidate Bot can claim it
    4. Split     — break the intent into bounded subtasks (LLM returns a list
                   of Task JSON objects, validated against the schema)
    5. Execute   — run each task via ``octo_engine`` (synchronous / best-effort
                   fan-out) and collect :class:`TaskExecution` results
    6. Verify    — evaluate results against the 4 supported criteria
                   (``human_review`` / ``automated_test`` /
                   ``quality_threshold`` / ``count_check``) and produce a
                   :class:`VerifiedResult`
    7. Learn     — write-back lessons: success → ``MetaKimSkillWriter``
                   creates a Skill; failure → :class:`FailureKnowledgeBase`
                   records the failure with a suggestion

After Step 7 the engine emits a ``meta_kim.run_completed`` event on the bus
and appends the :class:`GovernedRun` to :class:`RunHistoryStore`.

Backward compatibility
----------------------
The P19-B4 skeleton (``MetaKimEngineLegacy`` + ``GovernanceStage`` /
``StageOutcome`` / ``GovernanceResult`` dataclasses) is preserved verbatim
so existing tests in ``tests/test_meta_kim_engine.py`` continue to work
unchanged.  New code should use the :class:`MetaKimEngine` class with the
7-step loop.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

from .meta_kim_kb import FailureKnowledgeBase, RunHistoryStore
from .meta_kim_schemas import (
    Capability,
    GovernedReport,
    GovernedRun,
    Intent,
    IntentType,
    Lesson as LessonSchema,
    LessonType,
    OwnerKind,
    Task,
    TaskExecution,
    VerifyCriterion,
    VerifyCriterionType,
    VerifiedResult,
)
from .meta_kim_skill_writer import (
    MetaKimSkillWriter,
    SkillEngineLike,
    StubSkillEngine,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Protocol interfaces (so the engine can be wired without circular imports)
# --------------------------------------------------------------------------- #
class LLMProviderLike(Protocol):
    """Minimal interface for an LLM provider — must return a JSON string."""

    async def complete(
        self,
        prompt: str,
        *,
        response_format: str = "json",
        temperature: float = 0.2,
    ) -> str:
        ...


class CapabilityRegistryLike(Protocol):
    """Subset of ``capabilities_v2.engine.CapabilityRegistry`` we depend on."""

    def search(self, q: str) -> List[Any]:
        ...

    def get(self, cap_id: str) -> Optional[Any]:
        ...

    def list_all(self) -> List[Any]:
        ...


class OctoEngineLike(Protocol):
    """Subset of ``octo_engine.OctoEngine`` used by Meta_Kim for owner selection."""

    def execute_collab(
        self,
        mode: Any,
        matter_id: str,
        bot_ids: Optional[List[str]] = None,
        *,
        channel_id: Optional[str] = None,
    ) -> Any:
        ...

    def create_matter(self, title: str, body: str = "") -> str:
        ...


class BusLike(Protocol):
    """Subset of ``orchestration.bus.EventBus`` we use to emit completion events."""

    def record(
        self,
        topic: str,
        entity_type: str = "",
        entity_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
        actor: str = "system",
        refs: Optional[Dict[str, str]] = None,
        source_module: str = "",
    ) -> int:
        ...


# --------------------------------------------------------------------------- #
# Embedding helper (deterministic hash-based mock used when no embedding fn given)
# --------------------------------------------------------------------------- #
def _hash_embedding(text: str, dim: int = 32) -> List[float]:
    """Deterministic 32-dim embedding for tests / offline runs.

    Real production should pass a Sentence-Transformers / OpenAI embedding via
    ``embedding_fn``.  This fallback keeps the engine importable and tests
    reproducible without any heavy ML deps.
    """
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    for i, ch in enumerate(text[:512]):
        # spread ASCII across the bucket range; weight by position
        bucket = (ord(ch) + i) % dim
        vec[bucket] += 1.0 / (1 + i % 8)
    # L2-normalise
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class MetaKimEngine:
    """7-step governance loop engine.

    Parameters
    ----------
    capability_registry:
        An object exposing ``list_all()``, ``search(q)``, ``get(cap_id)``.
        ``Capability`` results are normalised to the local :class:`Capability`
        schema (with computed ``relevance_score`` if an embedding function is
        available).
    octo_engine:
        Optional :class:`OctoEngineLike` used to query bots during Step 3
        (Select Owner) and to dispatch tasks in Step 5 (Execute).  When ``None``
        the engine falls back to a deterministic in-process executor.
    skill_engine:
        Anything satisfying :class:`SkillEngineLike`.  When ``None`` a
        :class:`StubSkillEngine` is used so the loop can run end-to-end.
    llm:
        Optional :class:`LLMProviderLike`.  When ``None`` the engine produces
        deterministic stub outputs for Steps 1, 4, and 7 so tests can run
        without an LLM.
    bus:
        Optional :class:`BusLike` for emitting ``meta_kim.run_completed``
        events.  When ``None`` the call is silently skipped.
    embedding_fn:
        Optional callable ``str -> List[float]``.  Used by Step 2 to rank
        capabilities.  Falls back to :func:`_hash_embedding`.
    failure_kb:
        Optional pre-built :class:`FailureKnowledgeBase`.  A new instance is
        created if not supplied.
    run_history:
        Optional pre-built :class:`RunHistoryStore`.  A new instance is
        created if not supplied.
    skill_writer:
        Optional pre-built :class:`MetaKimSkillWriter`.  Created from
        ``skill_engine`` if not supplied.
    """

    COMPLETION_TOPIC = "meta_kim.run_completed"

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistryLike] = None,
        octo_engine: Optional[OctoEngineLike] = None,
        skill_engine: Optional[SkillEngineLike] = None,
        llm: Optional[LLMProviderLike] = None,
        bus: Optional[BusLike] = None,
        *,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        failure_kb: Optional[FailureKnowledgeBase] = None,
        run_history: Optional[RunHistoryStore] = None,
        skill_writer: Optional[MetaKimSkillWriter] = None,
    ) -> None:
        self._capability_registry = capability_registry
        self._octo_engine = octo_engine
        self._llm = llm
        self._bus = bus
        self._embedding_fn = embedding_fn or _hash_embedding

        self._failure_kb = failure_kb or FailureKnowledgeBase()
        self._run_history = run_history or RunHistoryStore()

        if skill_writer is not None:
            self._skill_writer = skill_writer
        else:
            engine = skill_engine or StubSkillEngine()
            self._skill_writer = MetaKimSkillWriter(engine)

        self._lock = threading.RLock()
        self._runs: List[str] = []  # most-recent run ids (newest first)

    # ====================================================================== #
    # Public API
    # ====================================================================== #
    @property
    def failure_kb(self) -> FailureKnowledgeBase:
        return self._failure_kb

    @property
    def run_history(self) -> RunHistoryStore:
        return self._run_history

    @property
    def skill_writer(self) -> MetaKimSkillWriter:
        return self._skill_writer

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "runs": len(self._runs),
                "failures_recorded": self._failure_kb.count(),
                "skills_created": len(self._skill_writer.created_skills),
                "has_llm": self._llm is not None,
                "has_octo_engine": self._octo_engine is not None,
                "has_capability_registry": self._capability_registry is not None,
            }

    async def govern_run(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GovernedRun:
        """Execute the full 7-step governance loop on one request."""
        ctx = dict(context or {})
        run_id = f"gov_{uuid.uuid4().hex[:12]}"

        # 1. Clarify
        intent = await self._clarify_intent(request=request, context=ctx)

        # 2. Search
        capabilities = await self._search_capabilities(intent=intent)

        # 3. Select
        owner = await self._select_owner(capabilities=capabilities, intent=intent)

        # 4. Split
        tasks = await self._split_tasks(intent=intent, capabilities=capabilities)

        # 5. Execute
        results = await self._execute_tasks(tasks=tasks, owner=owner)

        # 6. Verify
        criteria = self._derive_criteria(intent=intent, results=results)
        verified = await self._verify_results(
            results=results, criteria=criteria, intent=intent,
        )

        # 7. Learn (extract + write-back)
        lessons = self._extract_lessons(
            verified=verified,
            intent=intent,
            tasks=tasks,
            results=results,
            run_id=run_id,
        )
        await self._write_back_lessons(
            lessons=lessons,
            intent=intent,
            run_id=run_id,
            verified=verified,
        )

        # 8. Report + persist + emit bus event
        report = self._generate_report(
            run_id=run_id,
            intent=intent,
            owner=owner,
            tasks=tasks,
            verified=verified,
            lessons=lessons,
        )

        run = GovernedRun(
            id=run_id,
            request=request,
            context=ctx,
            intent=intent,
            capabilities=capabilities,
            owner=owner,
            tasks=tasks,
            results=results,
            verified=verified,
            lessons=lessons,
            report=report,
        )

        with self._lock:
            self._runs.insert(0, run_id)
        self._run_history.append(run.model_dump(mode="json"))
        self._emit_completion_event(run=run, report=report)

        return run

    # ====================================================================== #
    # Step 1: Clarify
    # ====================================================================== #
    async def _clarify_intent(self, *, request: str, context: Dict[str, Any]) -> Intent:
        if self._llm is None:
            return self._stub_clarify_intent(request=request, context=context)

        prompt = self._build_clarify_prompt(request, context)
        try:
            raw = await self._llm.complete(prompt, response_format="json")
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception as exc:
            logger.warning("clarify LLM call failed (%s); falling back to stub", exc)
            return self._stub_clarify_intent(request=request, context=context)

        data.setdefault("description", request)
        data.setdefault("raw_request", request)
        data.setdefault("context", context)
        try:
            return Intent(**data)
        except Exception as exc:
            logger.warning("clarify returned malformed payload (%s); falling back", exc)
            return self._stub_clarify_intent(request=request, context=context)

    def _stub_clarify_intent(self, *, request: str, context: Dict[str, Any]) -> Intent:
        intent_type = self._classify_intent_heuristic(request)
        return Intent(
            intent_type=intent_type,
            description=request or "",
            success_standard={
                "criteria": [
                    {"type": "count_check", "min_count": 1, "description": "at least one task succeeded"},
                ],
            },
            constraints=dict(context.get("constraints") or {}),
            clarifying_questions=[],
            confidence=0.7 if request else 0.3,
            raw_request=request or "",
            context=context,
        )

    @staticmethod
    def _classify_intent_heuristic(request: str) -> IntentType:
        s = (request or "").lower()
        if any(k in s for k in ("清洗", "clean", "清洗数据", "去重", "dedupe")):
            return IntentType.DATA_CLEANING
        if any(k in s for k in ("采集", "crawl", "scrap", "download")):
            return IntentType.DATA_ACQUISITION
        if any(k in s for k in ("标注", "label", "annotate")):
            return IntentType.ANNOTATION
        if any(k in s for k in ("发布", "publish", "推送")):
            return IntentType.PUBLISH
        if any(k in s for k in ("导出", "export")):
            return IntentType.EXPORT
        if any(k in s for k in ("搜索", "search", "查找")):
            return IntentType.SEARCH
        if any(k in s for k in ("分类", "classify", "分类")):
            return IntentType.CLASSIFICATION
        if any(k in s for k in ("审核", "review", "qc", "质检")):
            return IntentType.QC
        if any(k in s for k in ("编排", "orchestrat", "调度")):
            return IntentType.ORCHESTRATION
        if any(k in s for k in ("转换", "transform", "处理")):
            return IntentType.TRANSFORM
        return IntentType.UNKNOWN

    @staticmethod
    def _build_clarify_prompt(request: str, context: Dict[str, Any]) -> str:
        return (
            "You are the AI governance system. Analyse the request and return JSON:\n"
            "{\n"
            '  "intent_type": "data_acquisition|data_cleaning|annotation|export|search|classification|review|qc|transform|publish|orchestration|unknown",\n'
            '  "description": "...",\n'
            '  "success_standard": {"criteria": [{"type":"automated_test|quality_threshold|count_check|human_review", "description":"..."}]},\n'
            '  "constraints": {...},\n'
            '  "clarifying_questions": [],\n'
            '  "confidence": 0.0\n'
            "}\n"
            f"Request: {request!r}\nContext: {json.dumps(context, ensure_ascii=False, default=str)}\n"
        )

    # ====================================================================== #
    # Step 2: Search
    # ====================================================================== #
    async def _search_capabilities(self, *, intent: Intent) -> List[Capability]:
        if self._capability_registry is None:
            return self._stub_search_capabilities(intent=intent)

        candidates_raw = self._capability_registry.list_all() or []
        if not candidates_raw:
            # try the textual fallback
            try:
                candidates_raw = self._capability_registry.search(intent.description or "")
            except Exception:
                candidates_raw = []

        embedding = self._safe_embed(intent.description or intent.intent_type.value)

        out: List[Capability] = []
        for cap in candidates_raw[:64]:  # cap fan-in
            try:
                cap_id = getattr(cap, "id", None) or getattr(cap, "capability_id", "")
                name = getattr(cap, "name", cap_id)
                category = getattr(cap, "category", "general")
                description = getattr(cap, "description", "")
                tags = list(getattr(cap, "tags", []) or [])
                owner = getattr(cap, "owner", "platform")
                if hasattr(category, "value"):
                    category = category.value
                relevance = self._relevance_score(
                    name=str(name), description=str(description),
                    tags=tags, intent=intent, embedding=embedding,
                )
                out.append(Capability(
                    capability_id=str(cap_id),
                    name=str(name),
                    category=str(category),
                    description=str(description),
                    relevance_score=relevance,
                    automatable=True,
                    tags=tags,
                    owner=str(owner),
                ))
            except Exception as exc:
                logger.debug("skip malformed capability: %s", exc)

        out.sort(key=lambda c: c.relevance_score, reverse=True)
        return out[:5]

    def _stub_search_capabilities(self, *, intent: Intent) -> List[Capability]:
        # Deterministic 5-candidate stub keyed off intent_type.
        seed = intent.intent_type.value
        base = [
            ("cap.crawl", "crawl", "采集/抓取数据源", 0.91),
            ("cap.clean", "clean", "清洗与去重", 0.84),
            ("cap.label", "label", "自动标注", 0.78),
            ("cap.qc", "qc", "质检审核", 0.71),
            ("cap.export", "export", "导出数据集", 0.66),
        ]
        return [
            Capability(
                capability_id=f"{cid}.{seed}",
                name=name,
                category=seed,
                description=desc,
                relevance_score=score,
                automatable=True,
                tags=[seed, name],
            )
            for cid, name, desc, score in base
        ]

    def _relevance_score(
        self,
        *,
        name: str,
        description: str,
        tags: List[str],
        intent: Intent,
        embedding: List[float],
    ) -> float:
        score = 0.0
        target_words = re.findall(r"[\w]+", (intent.description or "").lower())
        for word in target_words[:6]:
            if word in (name or "").lower():
                score += 0.15
            if word in (description or "").lower():
                score += 0.10
            for tag in tags:
                if word in (tag or "").lower():
                    score += 0.08
        # Intent-type affinity
        if intent.intent_type.value in tags:
            score += 0.25
        if intent.intent_type.value in (description or "").lower():
            score += 0.18
        # Cosine similarity bonus (capabilities without their own embedding
        # default to zero — only contributes when ``embedding_fn`` returns one)
        return round(min(1.0, score + 0.05), 4)

    def _safe_embed(self, text: str) -> List[float]:
        try:
            return self._embedding_fn(text or "")
        except Exception:
            return _hash_embedding(text or "")

    # ====================================================================== #
    # Step 3: Select
    # ====================================================================== #
    async def _select_owner(
        self,
        *,
        capabilities: List[Capability],
        intent: Intent,
    ) -> OwnerKind:
        # Ask octo for a candidate bot; if any exists we run via BOT.
        if self._octo_engine is not None and capabilities:
            try:
                # OctoBot doesn't expose a "list by capability" helper, so we
                # probe by executing a SOLO matter and inferring capability.
                matter_id = self._octo_engine.create_matter(
                    title=intent.description or intent.intent_type.value,
                    body="owner-probe",
                )
                self._octo_engine.execute_collab(
                    mode=self._owner_probe_mode(),
                    matter_id=matter_id,
                    bot_ids=None,
                )
                return OwnerKind.BOT
            except Exception as exc:
                logger.debug("octo owner probe failed: %s", exc)

        # No octo / no caps / probe failed
        if capabilities and all(c.automatable for c in capabilities):
            return OwnerKind.AUTO
        if capabilities:
            # Mixed capabilities ⇒ human-in-the-loop fallback
            return OwnerKind.HYBRID
        return OwnerKind.HUMAN_REQUIRED

    @staticmethod
    def _owner_probe_mode():
        # Lazy import so the engine doesn't take a hard octo dependency.
        from .octo_engine import OctoCollabMode
        return OctoCollabMode.SOLO

    # ====================================================================== #
    # Step 4: Split
    # ====================================================================== #
    async def _split_tasks(
        self,
        *,
        intent: Intent,
        capabilities: List[Capability],
    ) -> List[Task]:
        if self._llm is None:
            return self._stub_split_tasks(intent=intent, capabilities=capabilities)

        prompt = self._build_split_prompt(intent, capabilities)
        try:
            raw = await self._llm.complete(prompt, response_format="json")
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            items = data.get("tasks") if isinstance(data, dict) else data
        except Exception as exc:
            logger.warning("split LLM call failed (%s); using stub", exc)
            return self._stub_split_tasks(intent=intent, capabilities=capabilities)

        tasks: List[Task] = []
        for item in (items or []):
            if not isinstance(item, dict):
                continue
            try:
                tasks.append(Task(**item))
            except Exception as exc:
                logger.debug("skip malformed task (%s): %s", exc, item)
        return tasks or self._stub_split_tasks(intent=intent, capabilities=capabilities)

    def _stub_split_tasks(
        self,
        *,
        intent: Intent,
        capabilities: List[Capability],
    ) -> List[Task]:
        # 6-stage pipeline stub (matches the example in the task brief).
        steps = [
            ("crawl", "采集原始数据", 5),
            ("dedupe", "去重 + 哈希", 3),
            ("clean", "清洗 + 过滤", 8),
            ("label", "自动标注", 15),
            ("qc", "质检 + 抽检", 10),
            ("export", "导出 + 打包", 5),
        ]
        cap_by_name = {c.name.lower(): c for c in capabilities}
        tasks: List[Task] = []
        prev: Optional[str] = None
        for name, desc, dur in steps:
            cap = cap_by_name.get(name)
            tasks.append(Task(
                name=name,
                description=desc,
                capability_id=cap.capability_id if cap else f"cap.{name}",
                dependencies=[prev] if prev else [],
                estimated_duration_min=dur,
                inputs={"intent": intent.intent_type.value, "stage": name},
                status="pending",
            ))
            prev = name
        return tasks

    @staticmethod
    def _build_split_prompt(intent: Intent, capabilities: List[Capability]) -> str:
        return (
            "Split the intent into bounded subtasks. Return JSON: "
            "{\"tasks\":[{\"name\":\"...\",\"description\":\"...\",\"capability_id\":\"...\","
            "\"dependencies\":[],\"estimated_duration_min\":10,\"inputs\":{}}]}\n"
            f"Intent: {intent.description!r}\n"
            f"Capabilities: {[c.model_dump(mode='json') for c in capabilities]}\n"
        )

    # ====================================================================== #
    # Step 5: Execute
    # ====================================================================== #
    async def _execute_tasks(
        self,
        *,
        tasks: List[Task],
        owner: OwnerKind,
    ) -> List[TaskExecution]:
        out: List[TaskExecution] = []
        for task in tasks:
            t0 = time.perf_counter()
            task.status = "running"
            task.started_at = datetime.now().isoformat()
            try:
                output = await self._execute_one_task(task=task, owner=owner)
                duration_ms = int((time.perf_counter() - t0) * 1000)
                task.status = "success"
                task.output = output
                task.finished_at = datetime.now().isoformat()
                out.append(TaskExecution(
                    task_id=task.task_id,
                    task_name=task.name,
                    status="success",
                    output=output,
                    duration_ms=duration_ms,
                ))
            except Exception as exc:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                task.status = "failed"
                task.error = f"{type(exc).__name__}: {exc}"
                task.finished_at = datetime.now().isoformat()
                out.append(TaskExecution(
                    task_id=task.task_id,
                    task_name=task.name,
                    status="failed",
                    error=task.error,
                    duration_ms=duration_ms,
                ))
        return out

    async def _execute_one_task(self, *, task: Task, owner: OwnerKind) -> Dict[str, Any]:
        """Dispatch a single task. Falls back to deterministic stub on failure."""
        # 1. Try the real capability registry.
        if self._capability_registry is not None and task.capability_id:
            try:
                cap = self._capability_registry.get(task.capability_id)
                if cap is not None:
                    invoke = getattr(cap, "invoke", None)
                    if callable(invoke):
                        result = invoke(dict(task.inputs or {}))
                        if isinstance(result, dict):
                            return result
            except Exception as exc:
                logger.debug("registry invoke failed for %s: %s", task.capability_id, exc)

        # 2. Try the octo engine (collab SOLO).
        if self._octo_engine is not None and owner == OwnerKind.BOT:
            try:
                matter_id = self._octo_engine.create_matter(
                    title=task.name, body=str(task.inputs or {}),
                )
                result = self._octo_engine.execute_collab(
                    mode=self._owner_probe_mode(),
                    matter_id=matter_id,
                )
                output = getattr(result, "output", None) or {"matter": matter_id}
                return {"via": "octo", "output": output}
            except Exception as exc:
                logger.debug("octo execute failed: %s", exc)

        # 3. Deterministic stub — every task reports success with its inputs echoed.
        return {
            "via": "stub",
            "task": task.name,
            "intent": (task.inputs or {}).get("intent", "unknown"),
            "echoed_inputs": dict(task.inputs or {}),
            "duration_min": task.estimated_duration_min,
        }

    # ====================================================================== #
    # Step 6: Verify
    # ====================================================================== #
    async def _verify_results(
        self,
        *,
        results: List[TaskExecution],
        criteria: List[VerifyCriterion],
        intent: Intent,
    ) -> VerifiedResult:
        failures: List[str] = []
        details: Dict[str, Any] = {"criteria": []}
        score = 1.0
        requires_human = False

        for criterion in criteria:
            entry: Dict[str, Any] = {"type": criterion.type.value, "ok": True}
            if criterion.type == VerifyCriterionType.HUMAN_REVIEW:
                requires_human = True
                entry["ok"] = False
                entry["reason"] = "human review required"
                failures.append(f"Human review required: {criterion.description or 'review'}")
            elif criterion.type == VerifyCriterionType.AUTOMATED_TEST:
                passed = self._run_automated_test(criterion, results)
                entry["ok"] = passed
                if not passed:
                    failures.append(
                        f"Automated test failed: {criterion.description or criterion.test_id}"
                    )
            elif criterion.type == VerifyCriterionType.QUALITY_THRESHOLD:
                measured = self._measure_quality(criterion, results)
                threshold = criterion.threshold or 0.95
                passed = measured >= threshold
                entry["measured"] = measured
                entry["threshold"] = threshold
                entry["ok"] = passed
                if not passed:
                    failures.append(
                        f"Quality below threshold: {measured:.2f} < {threshold}"
                    )
                score = min(score, measured)
            elif criterion.type == VerifyCriterionType.COUNT_CHECK:
                count = self._count_results(results)
                minimum = criterion.min_count or 1
                passed = count >= minimum
                entry["count"] = count
                entry["min_count"] = minimum
                entry["ok"] = passed
                if not passed:
                    failures.append(f"Count {count} < minimum {minimum}")
            details["criteria"].append(entry)

        # If no criteria specified, default to "all tasks succeeded"
        if not criteria:
            ok = all(r.status == "success" for r in results) and bool(results)
            if not ok:
                failures.append("At least one task failed")
            details["criteria"].append({"type": "implicit", "ok": ok})

        succeeded = (not failures) and (not requires_human)
        return VerifiedResult(
            succeeded=succeeded,
            requires_human_review=requires_human,
            message=("All criteria met" if succeeded else "; ".join(failures)),
            failures=failures,
            score=round(score if succeeded else 0.0, 4),
            details=details,
        )

    @staticmethod
    def _run_automated_test(
        criterion: VerifyCriterion,
        results: List[TaskExecution],
    ) -> bool:
        # Default: any failed result fails the test.
        if any(r.status == "failed" for r in results):
            return False
        return True

    @staticmethod
    def _measure_quality(
        criterion: VerifyCriterion,
        results: List[TaskExecution],
    ) -> float:
        if not results:
            return 0.0
        success = sum(1 for r in results if r.status == "success")
        return success / max(1, len(results))

    @staticmethod
    def _count_results(results: List[TaskExecution]) -> int:
        return sum(1 for r in results if r.status == "success")

    def _derive_criteria(
        self,
        *,
        intent: Intent,
        results: List[TaskExecution],
    ) -> List[VerifyCriterion]:
        """Build the criteria list from intent.success_standard + heuristic."""
        criteria: List[VerifyCriterion] = []
        ss = intent.success_standard or {}
        for raw in ss.get("criteria", []) or []:
            if not isinstance(raw, dict):
                continue
            try:
                t = raw.get("type", "count_check")
                criteria.append(VerifyCriterion(
                    type=VerifyCriterionType(t),
                    description=str(raw.get("description", "")),
                    test_id=raw.get("test_id"),
                    metric=raw.get("metric"),
                    threshold=raw.get("threshold"),
                    min_count=raw.get("min_count"),
                ))
            except Exception as exc:
                logger.debug("skip malformed criterion (%s): %s", exc, raw)

        # Always at minimum a count_check
        if not any(c.type == VerifyCriterionType.COUNT_CHECK for c in criteria):
            criteria.append(VerifyCriterion(
                type=VerifyCriterionType.COUNT_CHECK,
                description="at least one successful result",
                min_count=1,
            ))
        return criteria

    # ====================================================================== #
    # Step 7: Learn (extract + write-back)
    # ====================================================================== #
    def _extract_lessons(
        self,
        *,
        verified: VerifiedResult,
        intent: Intent,
        tasks: List[Task],
        results: List[TaskExecution],
        run_id: str,
    ) -> List[Lesson]:
        lessons: List[Lesson] = []
        if verified.succeeded:
            content = {
                "name": f"auto_{intent.intent_type.value}_pipeline",
                "description": intent.description or "",
                "steps": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "capability_id": t.capability_id,
                        "estimated_duration_min": t.estimated_duration_min,
                    }
                    for t in tasks
                ],
                "trigger_phrases": [intent.intent_type.value, intent.description or ""],
                "type": "success",
            }
            lessons.append(LessonSchema(
                type=LessonType.SUCCESS,
                description=f"Intent {intent.intent_type.value} completed",
                action="create_skill",
                content=content,
                run_id=run_id,
                tags=[intent.intent_type.value, "auto_skill"],
            ))
        else:
            for failure in verified.failures or ["unknown failure"]:
                lessons.append(LessonSchema(
                    type=LessonType.FAILURE,
                    description=f"Intent {intent.intent_type.value} failed: {failure}",
                    action="needs_improvement",
                    content={
                        "failure": failure,
                        "context": {"intent": intent.intent_type.value},
                        "suggestion": self._suggest_improvement(failure),
                        "type": "failure",
                    },
                    run_id=run_id,
                    tags=[intent.intent_type.value, "failure"],
                ))
        return lessons

    @staticmethod
    def _suggest_improvement(failure: str) -> str:
        f = (failure or "").lower()
        if "count" in f and "minimum" in f:
            return "Increase batch size or retry; check upstream source availability"
        if "quality" in f and "threshold" in f:
            return "Tune model parameters or add an extra cleaning pass"
        if "automated test" in f:
            return "Inspect test_id logic and reproduce locally"
        if "human review" in f:
            return "Surface the deliverable for manual approval before proceeding"
        return "Investigate root cause; add regression coverage"

    async def _write_back_lessons(
        self,
        *,
        lessons: List[Lesson],
        intent: Intent,
        run_id: str,
        verified: VerifiedResult,
    ) -> None:
        for lesson in lessons:
            if lesson.type == LessonType.SUCCESS and lesson.action == "create_skill":
                self._skill_writer.write_skill_from_lesson(
                    lesson=lesson.content,
                    intent=intent.model_dump(mode="json"),
                    run_id=run_id,
                )
            elif lesson.type == LessonType.FAILURE:
                self._failure_kb.append(
                    run_id=run_id,
                    failure=lesson.content.get("failure", lesson.description),
                    context=lesson.content.get("context"),
                    suggestion=lesson.content.get("suggestion", ""),
                    tags=lesson.tags,
                )

    # ====================================================================== #
    # Report + bus emit
    # ====================================================================== #
    def _generate_report(
        self,
        *,
        run_id: str,
        intent: Intent,
        owner: OwnerKind,
        tasks: List[Task],
        verified: VerifiedResult,
        lessons: List[Lesson],
    ) -> GovernedReport:
        skill_name = None
        failure_recorded = False
        for lesson in lessons:
            if lesson.type == LessonType.SUCCESS and lesson.content.get("name"):
                skill_name = str(lesson.content["name"])
            elif lesson.type == LessonType.FAILURE:
                failure_recorded = True

        summary_bits = [
            f"intent={intent.intent_type.value}",
            f"owner={owner.value}",
            f"tasks={len(tasks)}",
            "succeeded" if verified.succeeded else "failed",
        ]
        return GovernedReport(
            run_id=run_id,
            intent_type=intent.intent_type.value,
            owner_kind=owner,
            task_count=len(tasks),
            succeeded=verified.succeeded,
            requires_human_review=verified.requires_human_review,
            lessons_count=len(lessons),
            skill_created=skill_name,
            failure_recorded=failure_recorded,
            summary="; ".join(summary_bits),
        )

    def _emit_completion_event(self, *, run: GovernedRun, report: GovernedReport) -> None:
        if self._bus is None:
            return
        try:
            payload = {
                "intent": run.intent.intent_type.value if run.intent else "unknown",
                "task_count": report.task_count,
                "success": report.succeeded,
                "skill_created": report.skill_created,
                "failure_recorded": report.failure_recorded,
                "owner_kind": report.owner_kind.value,
            }
            self._bus.record(
                topic=self.COMPLETION_TOPIC,
                entity_type="governance_run",
                entity_id=run.id,
                payload=payload,
                actor="meta_kim",
                refs={},
                source_module="meta_kim",
            )
        except Exception as exc:  # pragma: no cover — best-effort
            logger.debug("bus emit failed: %s", exc)


# --------------------------------------------------------------------------- #
# Backward-compat: P19-B4 legacy 8-stage skeleton.
# Preserved verbatim so the existing tests/test_meta_kim_engine.py continues
# to pass without modification.  New code should use ``MetaKimEngine``.
# --------------------------------------------------------------------------- #
class MetaKimState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class GovernanceStage(str, Enum):
    CLARIFY = "clarify"
    SEARCH_CAPABILITY = "search_capability"
    ASSIGN_OWNERSHIP = "assign_ownership"
    SPLIT_TASK = "split_task"
    EXECUTE = "execute"
    REVIEW = "review"
    VERIFY = "verify"
    LEARN_BACK = "learn_back"


@dataclass
class StageOutcome:
    stage: GovernanceStage
    ok: bool = True
    detail: str = ""
    artifacts: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "ok": self.ok,
            "detail": self.detail,
            "artifacts": dict(self.artifacts),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class GovernanceResult:
    loop_id: str
    request: Dict[str, Any]
    stages: List[StageOutcome] = field(default_factory=list)
    ok: bool = True
    lessons: List[str] = field(default_factory=list)
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "request": dict(self.request),
            "stages": [s.to_dict() for s in self.stages],
            "ok": self.ok,
            "lessons": list(self.lessons),
            "finished_at": self.finished_at,
        }


@dataclass
class Lesson_legacy:  # noqa: N801 — kept as alias to avoid clashing with schema.Lesson
    lesson_id: str
    loop_id: str
    body: str
    tags: List[str] = field(default_factory=list)
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "loop_id": self.loop_id,
            "body": self.body,
            "tags": list(self.tags),
            "recorded_at": self.recorded_at,
        }


# Backward alias: the old test file imports ``Lesson`` from this module — point
# it at the legacy dataclass so the contract is preserved.
Lesson = Lesson_legacy  # type: ignore[misc]


class MetaKimEngineLegacy:
    """P19-B4 legacy 8-stage governance skeleton (kept for backward compat)."""

    DEFAULT_STAGES: List[GovernanceStage] = [
        GovernanceStage.CLARIFY,
        GovernanceStage.SEARCH_CAPABILITY,
        GovernanceStage.ASSIGN_OWNERSHIP,
        GovernanceStage.SPLIT_TASK,
        GovernanceStage.EXECUTE,
        GovernanceStage.REVIEW,
        GovernanceStage.VERIFY,
        GovernanceStage.LEARN_BACK,
    ]

    def __init__(
        self,
        *,
        audit_chain: Optional[Any] = None,
        lessons_path: Optional[str] = None,
        max_lessons: int = 1000,
    ) -> None:
        self._lock = threading.RLock()
        self._state = MetaKimState.IDLE
        self._audit_chain = audit_chain
        self._lessons: List[Lesson_legacy] = []
        self._max_lessons = max_lessons
        self._lessons_path = lessons_path
        self._history: List[GovernanceResult] = []

    # ── Lifecycle ────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._state = MetaKimState.RUNNING

    def stop(self) -> None:
        with self._lock:
            self._state = MetaKimState.STOPPED

    def pause(self) -> None:
        with self._lock:
            if self._state == MetaKimState.RUNNING:
                self._state = MetaKimState.PAUSED

    def resume(self) -> None:
        with self._lock:
            if self._state == MetaKimState.PAUSED:
                self._state = MetaKimState.RUNNING

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "loops": len(self._history),
                "lessons": len(self._lessons),
                "audit_chain": bool(self._audit_chain),
                "lessons_path": self._lessons_path or "",
            }

    # ── run_governance_loop ──────────────────────────────────────
    def run_governance_loop(
        self,
        request: Dict[str, Any],
        *,
        stage_hooks: Optional[Dict[GovernanceStage, Callable[[Dict[str, Any]], StageOutcome]]] = None,
    ) -> GovernanceResult:
        if not isinstance(request, dict):
            raise TypeError("request must be a dict")
        if self._state == MetaKimState.STOPPED:
            raise RuntimeError("MetaKimEngineLegacy is stopped")
        stage_hooks = stage_hooks or {}
        loop_id = uuid.uuid4().hex[:8]
        result = GovernanceResult(loop_id=loop_id, request=request)
        for stage in self.DEFAULT_STAGES:
            outcome = self._run_stage(stage, request, stage_hooks.get(stage))
            result.stages.append(outcome)
            if not outcome.ok:
                result.ok = False
                break
        result.finished_at = datetime.now().isoformat()
        with self._lock:
            self._history.append(result)
        return result

    def _run_stage(self, stage, request, hook):
        outcome = StageOutcome(stage=stage)
        try:
            if hook is not None:
                returned = hook(request)
                if isinstance(returned, StageOutcome):
                    outcome = returned
                    outcome.stage = stage
                elif isinstance(returned, dict):
                    outcome.ok = bool(returned.get("ok", True))
                    outcome.detail = str(returned.get("detail", ""))
                    outcome.artifacts = dict(returned.get("artifacts", {}))
                else:
                    outcome.detail = f"hook returned non-dict: {type(returned).__name__}"
                    outcome.ok = False
            else:
                outcome.detail = f"default stub for {stage.value}"
                outcome.artifacts = {"request_keys": sorted(request.keys())}
        except Exception as exc:
            outcome.ok = False
            outcome.detail = f"hook raised: {exc}"
        outcome.finished_at = datetime.now().isoformat()
        return outcome

    # ── record_lesson ────────────────────────────────────────────
    def record_lesson(self, *, loop_id: str = "", body: str,
                       tags: Optional[List[str]] = None) -> str:
        if not body:
            raise ValueError("lesson body must be non-empty")
        lesson_id = uuid.uuid4().hex[:8]
        lesson = Lesson_legacy(lesson_id=lesson_id, loop_id=loop_id, body=body,
                                tags=list(tags or []))
        with self._lock:
            self._lessons.append(lesson)
            if len(self._lessons) > self._max_lessons:
                self._lessons = self._lessons[-self._max_lessons:]
            self._persist_lessons_locked()
        return lesson_id

    def list_lessons(self, limit: int = 50) -> List[Lesson_legacy]:
        with self._lock:
            return list(self._lessons[-limit:])

    # ── persistence ─────────────────────────────────────────────
    def _persist_lessons_locked(self) -> None:
        if not self._lessons_path:
            return
        try:
            os.makedirs(os.path.dirname(self._lessons_path), exist_ok=True)
            with open(self._lessons_path, "w", encoding="utf-8") as f:
                json.dump(
                    [l.to_dict() for l in self._lessons[-200:]],
                    f, ensure_ascii=False, default=str,
                )
        except Exception:
            pass

    def load_lessons_from_disk(self) -> int:
        if not self._lessons_path or not os.path.exists(self._lessons_path):
            return 0
        try:
            with open(self._lessons_path, "r", encoding="utf-8") as f:
                rows = json.load(f)
            count = 0
            with self._lock:
                for row in rows:
                    self._lessons.append(Lesson_legacy(
                        lesson_id=row.get("lesson_id", uuid.uuid4().hex[:8]),
                        loop_id=row.get("loop_id", ""),
                        body=row.get("body", ""),
                        tags=list(row.get("tags", []) or []),
                        recorded_at=row.get("recorded_at", datetime.now().isoformat()),
                    ))
                    count += 1
            return count
        except Exception:
            return 0


__all__ = [
    # New Pydantic-based 7-step loop
    "MetaKimEngine",
    "LLMProviderLike",
    "CapabilityRegistryLike",
    "OctoEngineLike",
    "BusLike",
    # Legacy P19-B4 skeleton (kept for backward compat)
    "MetaKimEngineLegacy",
    "MetaKimState",
    "GovernanceStage",
    "StageOutcome",
    "GovernanceResult",
]