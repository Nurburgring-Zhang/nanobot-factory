"""P19-B4 + V5 第25章 — OctoEngine 协作网络.

The Octopus-style multi-agent orchestration engine.  Two co-existing APIs:

* **Legacy 6-mode collab** (P19-B4) — ``execute_collab(SOLO/ROUNDTABLE/
  CRITIC/PIPELINE/SPLIT/SWARM, matter_id, bot_ids)`` returns a
  :class:`CollabResult`.  Uses dataclass storage for backwards
  compatibility with the existing test suite.
* **V5 ch.25 4-concept model** (this file, P19 v5.3) — ``create_bot`` /
  ``create_channel`` / ``create_matter`` / ``post_message`` + bus events
  + skill binding.  Storage is the in-memory :class:`OctoKB`, types
  are Pydantic v2 models in :mod:`octo_schemas`.

``OctoBot`` / ``OctoChannel`` / ``OctoMatter`` are kept as aliases for
``AgentBot`` / ``Channel`` / ``Matter`` so the existing 12 test cases
plus downstream code keep passing.
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .octo_schemas import (
    AgentBot,
    AgentCard,
    AgentType,
    Channel,
    Matter,
    MatterStatus,
    OctoBot,
    OctoChannel,
    OctoMatter,
    Thread,
    ThreadMessage,
    _flatten,
    _now_iso,
)
from .octo_kb import OctoKB

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Enums + dataclasses (kept for backward compat with P19-B4 test suite)
# --------------------------------------------------------------------------- #
class OctoCollabMode(str, Enum):
    SOLO = "solo"
    ROUNDTABLE = "roundtable"
    CRITIC = "critic"
    PIPELINE = "pipeline"
    SPLIT = "split"
    SWARM = "swarm"


class OctoEngineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class CollabResult:
    """Result envelope for one ``execute_collab`` call."""

    mode: OctoCollabMode
    matter_id: str
    participants: List[str]
    output: Dict[str, Any] = field(default_factory=dict)
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    finished_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "matter_id": self.matter_id,
            "participants": list(self.participants),
            "output": dict(self.output),
            "transcript": list(self.transcript),
            "finished_at": self.finished_at,
        }


# --------------------------------------------------------------------------- #
#  6 default-prompt templates — one per AgentType
# --------------------------------------------------------------------------- #
DEFAULT_PROMPTS: Dict[str, str] = {
    AgentType.CODER.value: (
        "You are a professional code generation assistant. "
        "Strong in Python, JavaScript, TypeScript; write clean, "
        "tested, maintainable code with clear documentation."
    ),
    AgentType.REVIEWER.value: (
        "You are a strict code reviewer. Focus on code quality, "
        "security, maintainability, and edge-case coverage. "
        "Always propose concrete patches for any issue you raise."
    ),
    AgentType.WRITER.value: (
        "You are a professional content creator. Skilled at "
        "technical docs, marketing copy, and tutorial articles. "
        "Write in clear, concise natural language."
    ),
    AgentType.ANALYST.value: (
        "You are a data-analysis expert. Good at data wrangling, "
        "statistical analysis, and visualization. Always explain "
        "your reasoning and surface assumptions."
    ),
    AgentType.RESEARCHER.value: (
        "You are a research assistant. Skilled at literature "
        "search, information synthesis, and producing research "
        "reports with citations."
    ),
    AgentType.GENERIC.value: (
        "You are a general-purpose AI assistant, happy to help "
        "users complete any task."
    ),
}


# --------------------------------------------------------------------------- #
#  Bus topic constants — V5 ch.25 § 25.2-25.5
# --------------------------------------------------------------------------- #
TOPIC_BOT_CREATED = "octo.bot_created"
TOPIC_CHANNEL_CREATED = "octo.channel_created"
TOPIC_MATTER_CREATED = "octo.matter_created"
TOPIC_MATTER_ASSIGNED = "octo.matter_assigned"
TOPIC_MATTER_COMPLETED = "octo.matter_completed"
TOPIC_MESSAGE_POSTED = "octo.message_posted"


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #
class OctoEngine:
    """Bot / Channel / Matter / Thread orchestration engine (V5 第25章).

    Parameters
    ----------
    skill_engine :
        Optional skill engine — anything that exposes a synchronous
        ``get_skill(skill_id)`` method.  When ``None`` a permissive
        stub accepts every skill id so unit tests / demos can run
        end-to-end without wiring the real SkillRegistry.
    bus :
        Optional cross-module :class:`orchestration.bus.EventBus`.  When
        ``None``, an in-memory bus recorder captures every event so
        tests can introspect it via :attr:`bus_events`.
    """

    def __init__(
        self,
        skill_engine: Optional[Any] = None,
        bus: Optional[Any] = None,
    ) -> None:
        # Storage: kb (new) + the original dicts (legacy) so execute_collab
        # can keep using whichever shape it likes without a migration.
        self.kb = OctoKB()
        self._bots: Dict[str, OctoBot] = self.kb._bots  # alias to keep old code paths working
        self._channels: Dict[str, OctoChannel] = self.kb._channels  # type: ignore[assignment]
        self._matters: Dict[str, OctoMatter] = self.kb._matters  # type: ignore[assignment]
        self._messages: List[ThreadMessage] = self.kb._messages  # for post_message()

        self._lock = threading.RLock()
        self._state = OctoEngineState.IDLE
        self.skill_engine = skill_engine
        self.bus = bus
        # Fallback recording bus — captures events when no real bus is wired.
        self.bus_events: List[Dict[str, Any]] = []

    # ────────────────────────────────────────────────────────────────────
    #  Lifecycle / status  (P19-B4 backward compat)
    # ────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._state = OctoEngineState.RUNNING

    def stop(self) -> None:
        with self._lock:
            self._state = OctoEngineState.STOPPED

    def pause(self) -> None:
        with self._lock:
            if self._state == OctoEngineState.RUNNING:
                self._state = OctoEngineState.PAUSED

    def resume(self) -> None:
        with self._lock:
            if self._state == OctoEngineState.PAUSED:
                self._state = OctoEngineState.RUNNING

    def status(self) -> Dict[str, Any]:
        with self._lock:
            kb_status = self.kb.status()
            return {
                "state": self._state.value,
                "bots": kb_status["bots"],
                "channels": kb_status["channels"],
                "matters": kb_status["matters"],
                "open_matters": kb_status["open_matters"],
                "messages": kb_status["messages"],
                "skill_bindings": kb_status["skill_bindings"],
                "events_recorded": len(self.bus_events),
            }

    # ────────────────────────────────────────────────────────────────────
    #  Bus event helper
    # ────────────────────────────────────────────────────────────────────
    def _emit(
        self,
        topic: str,
        entity_id: str,
        payload: Optional[Dict[str, Any]] = None,
        actor: str = "system",
    ) -> None:
        """Emit an event to the real bus (if wired) or capture locally."""
        payload = dict(payload or {})
        envelope = {
            "topic": topic,
            "entity_id": entity_id,
            "entity_type": topic.split(".", 1)[-1].split("_", 1)[0] if topic else "",
            "payload": payload,
            "actor": actor,
            "recorded_at": _now_iso(),
        }
        if self.bus is not None:
            try:
                self.bus.record(
                    topic=topic,
                    entity_type=envelope["entity_type"],
                    entity_id=entity_id,
                    payload=payload,
                    actor=actor,
                    source_module="octo",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("bus.record failed for %s: %s", topic, exc)
        with self._lock:
            self.bus_events.append(envelope)

    # ────────────────────────────────────────────────────────────────────
    #  Bot management  (V5 ch.25 §25.2)
    # ────────────────────────────────────────────────────────────────────
    def create_bot(
        self,
        name: str,
        *,
        persona: str = "",
        capabilities: Optional[List[str]] = None,
        agent_type: str = AgentType.GENERIC.value,
        system_prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a Bot — returns ``bot_id`` (string).

        The bot is stored both in the legacy ``_bots`` dict (so existing
        6-mode callers see it) and in the new :class:`OctoKB`.
        """
        capabilities = list(capabilities or [])
        agent_card = AgentCard(
            owner="system",
            ability_description=f"擅长: {', '.join(capabilities)}" if capabilities else "",
            work_history=[],
        )
        bot = AgentBot(
            name=name,
            agent_type=agent_type or AgentType.GENERIC.value,
            capabilities=capabilities,
            agent_card=agent_card,
            status="active",
            system_prompt=system_prompt or self._default_prompt(agent_type),
            persona=persona,
            metadata=dict(metadata or {}),
        )
        # Make sure id and bot_id are in sync.
        if not bot.id:
            from .octo_schemas import _new_id
            bot = bot.model_copy(update={"id": _new_id("bot")})
        with self._lock:
            self.kb.upsert_bot(bot)
            # Mirror into legacy dict for execute_collab paths.
            self._bots[bot.id] = bot
        self._emit(
            TOPIC_BOT_CREATED,
            bot.id,
            payload={
                "name": bot.name,
                "agent_type": bot.agent_type,
                "capabilities": bot.capabilities,
            },
            actor=bot.agent_card.owner,
        )
        return bot.id

    def get_bot(self, bot_id: str) -> Optional[AgentBot]:
        return self.kb.get_bot(bot_id)

    def assign_skill_to_bot(self, bot_id: str, skill_id: str) -> bool:
        """Assign (bind) a skill to a bot.

        Returns ``True`` if the bot exists and the skill id was either
        accepted by the skill engine (if one is wired) or accepted by
        the permissive fallback.  Returns ``False`` if the bot doesn't
        exist or the skill engine explicitly rejected the id.
        """
        bot = self.kb.get_bot(bot_id)
        if bot is None:
            return False
        # Verify the skill id exists in the skill engine, when one is wired.
        if self.skill_engine is not None:
            try:
                skill = self.skill_engine.get_skill(skill_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("skill_engine.get_skill failed: %s", exc)
                skill = None
            if skill is None:
                return False
        # Bind to KB (which also appends skill_id to bot.capabilities).
        ok = self.kb.bind_skill(bot_id, skill_id)
        if ok:
            card = bot.agent_card
            ability_suffix = f"\n- 技能: {skill_id}"
            if ability_suffix not in card.ability_description:
                card.ability_description += ability_suffix
            bot.add_work_history({
                "event": "skill_assigned",
                "skill_id": skill_id,
                "at": _now_iso(),
            })
        return ok

    def list_bots(self) -> List[AgentBot]:
        return self.kb.list_bots()

    def get_bot_by_capability(self, capability: str) -> List[AgentBot]:
        """Return all bots that have ``capability`` in their capability list.

        Convenience alias matching the V5 doc method name.
        """
        return self.kb.find_bots_by_capability(capability)

    def _default_prompt(self, agent_type: Optional[str]) -> str:
        """Default system prompt for the 6 canonical agent types."""
        key = (agent_type or "").lower().strip()
        return DEFAULT_PROMPTS.get(key, DEFAULT_PROMPTS[AgentType.GENERIC.value])

    # ────────────────────────────────────────────────────────────────────
    #  Channel management  (V5 ch.25 §25.3)
    # ────────────────────────────────────────────────────────────────────
    def create_channel(
        self,
        name_or_topic: str,
        *,
        bot_ids: Optional[List[str]] = None,
        members: Optional[List[str]] = None,
        description: str = "",
        project_id: Optional[str] = None,
    ) -> str:
        """Create a channel — returns ``channel_id``.

        The first positional argument can be the channel's legacy ``topic``
        or its V5 ``name`` — both fields are kept in sync so old callers
        like ``create_channel("design", bot_ids=[])`` continue to work.
        """
        members = list(members if members is not None else (bot_ids or []))
        channel = Channel(
            name=name_or_topic,
            topic=name_or_topic,
            description=description,
            members=members,
            bot_ids=list(bot_ids or []),
            project_id=project_id,
        )
        if not channel.id:
            from .octo_schemas import _new_id
            channel = channel.model_copy(update={"id": _new_id("chan")})
        with self._lock:
            self.kb.upsert_channel(channel)
            self._channels[channel.id] = channel
        self._emit(
            TOPIC_CHANNEL_CREATED,
            channel.id,
            payload={
                "name": channel.name,
                "members": channel.members,
                "project_id": channel.project_id,
            },
        )
        return channel.id

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        return self.kb.get_channel(channel_id)

    def add_member_to_channel(
        self,
        channel_id: str,
        member_id: str,
        role: str = "member",
    ) -> bool:
        ch = self.kb.get_channel(channel_id)
        if ch is None:
            return False
        before = set(ch.members)
        ch.add_member(member_id)
        if member_id.startswith("bot") and member_id not in ch.bot_ids:
            ch.bot_ids.append(member_id)
        if set(ch.members) != before:
            with self._lock:
                self.kb.upsert_channel(ch)
            return True
        return True  # idempotent

    def remove_member_from_channel(self, channel_id: str, member_id: str) -> bool:
        ch = self.kb.get_channel(channel_id)
        if ch is None:
            return False
        before = set(ch.members)
        ch.remove_member(member_id)
        with self._lock:
            self.kb.upsert_channel(ch)
        return set(ch.members) != before

    def list_channels(self) -> List[Channel]:
        return self.kb.list_channels()

    # ────────────────────────────────────────────────────────────────────
    #  Matter management  (V5 ch.25 §25.4)
    # ────────────────────────────────────────────────────────────────────
    def create_matter(
        self,
        title_or_channel_id: str,
        title_or_body: str = "",
        *,
        channel_id: Optional[str] = None,
        assignee_type: str = "user",
        assignee_id: Optional[str] = None,
        deliverable: Optional[Dict[str, Any]] = None,
        acceptance_criteria: Optional[List[str]] = None,
        body: str = "",
    ) -> str:
        """Create a Matter — returns ``matter_id``.

        Legacy signature: ``create_matter(title: str, body: str = "")``.
        V5 signature: ``create_matter(channel_id, title, assignee_type,
        assignee_id, deliverable, acceptance_criteria)``.

        Both signatures are accepted — the engine infers which one by
        looking at whether the V5-only kwargs (assignee_type, deliverable,
        acceptance_criteria) are supplied or whether the first positional
        arg is a known channel id.
        """
        v5_kwargs_supplied = (
            assignee_type != "user"
            or assignee_id is not None
            or deliverable is not None
            or acceptance_criteria is not None
        )
        first_arg_is_known_channel = (
            self.kb.get_channel(title_or_channel_id) is not None
        )
        if channel_id is not None or first_arg_is_known_channel or v5_kwargs_supplied:
            # V5 form: create_matter(channel_id, title, **kwargs)
            if channel_id is None:
                channel_id = title_or_channel_id
                title = title_or_body
                body_text = body
            else:
                title = title_or_channel_id
                body_text = body
        else:
            # Legacy form: create_matter(title, body)
            title = title_or_channel_id
            body_text = title_or_body
            channel_id = None

        if channel_id is not None and self.kb.get_channel(channel_id) is None:
            raise ValueError(f"Channel {channel_id!r} not found")

        matter = Matter(
            channel_id=channel_id,
            title=title,
            assignee_type=assignee_type,
            assignee_id=assignee_id,
            deliverable=dict(deliverable or {}),
            acceptance_criteria=list(acceptance_criteria or []),
            body=body_text,
            status=MatterStatus.DRAFT.value,
        )
        if not matter.id:
            from .octo_schemas import _new_id
            matter = matter.model_copy(update={"id": _new_id("mat")})

        with self._lock:
            self.kb.upsert_matter(matter)
            self._matters[matter.id] = matter

        # Also create a Thread inside the channel so the conversation has
        # somewhere to live (V5 doc §25.4).
        if channel_id:
            ch = self.kb.get_channel(channel_id)
            if ch is not None:
                thread = ch.new_thread(title=title, matter_id=matter.id)
                thread.post_message(
                    sender_id="system",
                    content=f"创建 Matter: {title}",
                    role="system",
                )
                self.kb.upsert_channel(ch)

        self._emit(
            TOPIC_MATTER_CREATED,
            matter.id,
            payload={
                "title": matter.title,
                "assignee_id": matter.assignee_id,
                "assignee_type": matter.assignee_type,
                "channel_id": matter.channel_id,
            },
        )
        return matter.id

    def get_matter(self, matter_id: str) -> Optional[Matter]:
        return self.kb.get_matter(matter_id)

    def assign_matter(self, matter_id: str, assignee_id: str) -> bool:
        matter = self.kb.get_matter(matter_id)
        if matter is None:
            return False
        if matter.assignee_id == assignee_id:
            return True  # idempotent
        matter.assignee_id = assignee_id
        # If assignee_id starts with bot_, treat as a bot.
        matter.assignee_type = "bot" if assignee_id.startswith("bot") else "user"
        matter.status = MatterStatus.ASSIGNED.value
        matter.updated_at = _now_iso()
        matter.claimed_by = assignee_id  # legacy
        with self._lock:
            self.kb.upsert_matter(matter)
            self._matters[matter.id] = matter
        self._emit(
            TOPIC_MATTER_ASSIGNED,
            matter.id,
            payload={"assignee_id": assignee_id, "assignee_type": matter.assignee_type},
        )
        return True

    def complete_matter(
        self,
        matter_id: str,
        result: Optional[Dict[str, Any]] = None,
        *,
        force: bool = False,
    ) -> bool:
        """Mark a Matter complete (status=done).

        If the matter has any ``acceptance_criteria`` the ``result`` dict
        must satisfy them; otherwise the matter is bumped to ``review``
        state instead of ``done``.  Pass ``force=True`` to override the
        criteria check (for emergency/manual completion).
        """
        matter = self.kb.get_matter(matter_id)
        if matter is None:
            return False

        merged = {**(matter.deliverable or {}), "result": result or {}}
        matter.deliverable = merged
        matter.answer = result or {}  # legacy
        matter.updated_at = _now_iso()

        if force or matter.meets_acceptance(result or {}):
            matter.status = MatterStatus.DONE.value
            matter.closed_at = _now_iso()
            completed = True
        else:
            matter.status = MatterStatus.REVIEW.value
            matter.feedback = {
                "decision": "needs_review",
                "criteria_unmet": matter.acceptance_criteria,
            }
            completed = False

        with self._lock:
            self.kb.upsert_matter(matter)
            self._matters[matter.id] = matter

        self._emit(
            TOPIC_MATTER_COMPLETED,
            matter.id,
            payload={
                "result": result or {},
                "criteria_met": completed,
                "forced": force,
                "final_status": matter.status,
            },
        )
        return completed

    def list_matters(self, channel_id: Optional[str] = None) -> List[Matter]:
        return self.kb.list_matters(channel_id=channel_id)

    # ────────────────────────────────────────────────────────────────────
    #  Thread / message management  (V5 ch.25 §25.3 + §25.4 thread concept)
    # ────────────────────────────────────────────────────────────────────
    def post_message(
        self,
        channel_id: str,
        sender_id: str,
        content: str,
        *,
        thread_id: Optional[str] = None,
        role: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ThreadMessage]:
        ch = self.kb.get_channel(channel_id)
        if ch is None:
            return None
        metadata = dict(metadata or {})
        metadata.setdefault("channel_id", channel_id)
        if thread_id:
            metadata.setdefault("thread_id", thread_id)
            thread = next((t for t in ch.threads if t.id == thread_id), None)
            if thread is None:
                thread = ch.new_thread(matter_id=metadata.get("matter_id"))
            msg = thread.post_message(
                sender_id=sender_id,
                content=content,
                role=role,
                metadata=metadata,
            )
            msg.metadata.setdefault("thread_id", thread.id)
        else:
            # Free-floating message into the channel's main thread.
            thread = ch.threads[0] if ch.threads else ch.new_thread()
            if not thread.channel_id:
                thread.channel_id = channel_id
            msg = thread.post_message(
                sender_id=sender_id,
                content=content,
                role=role,
                metadata=metadata,
            )
            msg.metadata.setdefault("thread_id", thread.id)

        with self._lock:
            self.kb.append_message(msg)
            self.kb.upsert_channel(ch)

        self._emit(
            TOPIC_MESSAGE_POSTED,
            msg.id,
            payload={
                "channel_id": channel_id,
                "thread_id": msg.metadata.get("thread_id"),
                "sender_id": sender_id,
                "role": role,
                "preview": content[:120],
            },
        )
        return msg

    def list_messages(
        self,
        channel_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        limit: int = 1000,
    ) -> List[ThreadMessage]:
        """Return ThreadMessages — filtered by channel / thread / sender."""
        with self._lock:
            ch_filtered: List[ThreadMessage] = []
            for ch in self.kb.list_channels():
                if channel_id and ch.id != channel_id:
                    continue
                for thread in ch.threads:
                    if thread_id and thread.id != thread_id:
                        continue
                    for msg in thread.messages:
                        if sender_id and msg.sender_id != sender_id:
                            continue
                        ch_filtered.append(msg)
            return ch_filtered[:limit]

    # ────────────────────────────────────────────────────────────────────
    #  execute_collab (legacy 6-mode orchestrator — P19-B4)
    # ────────────────────────────────────────────────────────────────────
    def execute_collab(
        self,
        mode: OctoCollabMode,
        matter_id: str,
        bot_ids: Optional[List[str]] = None,
        *,
        channel_id: Optional[str] = None,
        hooks: Optional[Dict[str, Callable[[AgentBot, Matter], Dict[str, Any]]]] = None,
    ) -> CollabResult:
        """Execute one of the 6 collaboration protocols.

        ``hooks`` maps ``bot_id -> callable(bot, matter) -> output_dict``.
        When a hook is missing, the engine emits a stub output
        ``{"echo": body, "by": bot.name}`` so callers can verify
        orchestration shape end-to-end.
        """
        hooks = hooks or {}
        with self._lock:
            matter = self._matters.get(matter_id)
            if matter is None:
                raise KeyError(f"matter {matter_id!r} not found")
            bots = [self._bots[bid] for bid in (bot_ids or []) if bid in self._bots]
            channel = self._channels.get(channel_id) if channel_id else None

        transcript: List[Dict[str, Any]] = []
        participants = [b.id for b in bots]

        # SOLO — one bot, no channel, no transcript.
        if mode == OctoCollabMode.SOLO:
            output = self._invoke_hook(hooks, bots, matter)
            matter.answer = output
            matter.state = "answered"
            if bots:
                matter.claimed_by = bots[0].id
            matter.closed_at = datetime.now().isoformat()
            with self._lock:
                self.kb.upsert_matter(matter)
            return CollabResult(
                mode=mode,
                matter_id=matter_id,
                participants=participants,
                output=output,
            )

        # ROUNDTABLE — every bot posts a message, no winner.
        if mode == OctoCollabMode.ROUNDTABLE:
            ch = channel or self._ensure_channel_for(bots, topic=matter.title)
            for b in bots:
                payload = self._invoke_hook(hooks, [b], matter)
                msg = ch.post(b.id, str(payload.get("echo", payload)), kind="roundtable")
                transcript.append({"channel_id": ch.id, "message": msg})
            with self._lock:
                self.kb.upsert_channel(ch)
            return CollabResult(
                mode=mode,
                matter_id=matter_id,
                participants=participants,
                output={"rounds": len(bots), "channel": ch.id},
                transcript=transcript,
            )

        # CRITIC — first bot proposes, second bot criticises, iterate up to 3 rounds.
        if mode == OctoCollabMode.CRITIC:
            if len(bots) < 2:
                bots = (bots + [self._create_default_critic(bots)])[:2]
            ch = channel or self._ensure_channel_for(
                bots, topic=f"critic:{matter.title}"
            )
            proposal = self._invoke_hook(hooks, [bots[0]], matter)
            for round_idx in range(3):
                critic_payload = self._invoke_hook(
                    hooks, [bots[1]], matter, base=proposal
                )
                msg_p = ch.post(bots[0].id, str(proposal), kind="proposal")
                msg_c = ch.post(bots[1].id, str(critic_payload), kind="critique")
                transcript.extend(
                    [
                        {"channel_id": ch.id, "message": msg_p},
                        {"channel_id": ch.id, "message": msg_c},
                    ]
                )
                if critic_payload.get("accept"):
                    proposal = {**proposal, "approved": True}
                    break
                proposal = {**proposal, "revision": round_idx + 1}
            matter.answer = proposal
            matter.state = "answered"
            matter.closed_at = datetime.now().isoformat()
            with self._lock:
                self.kb.upsert_matter(matter)
                self.kb.upsert_channel(ch)
            return CollabResult(
                mode=mode,
                matter_id=matter_id,
                participants=participants,
                output=proposal,
                transcript=transcript,
            )

        # PIPELINE — output of bot N is input to bot N+1.
        if mode == OctoCollabMode.PIPELINE:
            stage_output: Dict[str, Any] = {"input": matter.body}
            ch = channel or self._ensure_channel_for(
                bots, topic=f"pipeline:{matter.title}"
            )
            for idx, b in enumerate(bots):
                payload = self._invoke_hook(
                    hooks, [b], matter, base=stage_output, stage=idx
                )
                stage_output = {"stage": idx, "by": b.name, "payload": payload}
                msg = ch.post(b.id, str(payload), kind="stage")
                transcript.append({"channel_id": ch.id, "message": msg})
            matter.answer = stage_output
            matter.state = "answered"
            matter.closed_at = datetime.now().isoformat()
            with self._lock:
                self.kb.upsert_matter(matter)
                self.kb.upsert_channel(ch)
            return CollabResult(
                mode=mode,
                matter_id=matter_id,
                participants=participants,
                output=stage_output,
                transcript=transcript,
            )

        # SPLIT — sub-matters, each handled by one bot.
        if mode == OctoCollabMode.SPLIT:
            if not bots:
                raise ValueError("split mode requires at least one bot")
            shards = max(1, len(bots))
            sub_outputs: List[Dict[str, Any]] = []
            from .octo_schemas import _new_id
            for idx, b in enumerate(bots):
                shard_body = f"{matter.body}\n[shard {idx + 1}/{shards}]"
                shard = Matter(
                    id=_new_id("mat"),
                    title=f"{matter.title}#shard{idx}",
                    body=shard_body,
                )
                if not shard.id:
                    shard = shard.model_copy(update={"id": _new_id("mat")})
                with self._lock:
                    self.kb.upsert_matter(shard)
                    self._matters[shard.id] = shard
                payload = self._invoke_hook(hooks, [b], shard)
                shard.answer = payload
                shard.state = "answered"
                shard.claimed_by = b.id
                shard.closed_at = datetime.now().isoformat()
                with self._lock:
                    self.kb.upsert_matter(shard)
                    self._matters[shard.id] = shard
                sub_outputs.append({"shard_id": shard.id, "by": b.name, "output": payload})
            merged = {"shards": sub_outputs}
            matter.answer = merged
            matter.state = "answered"
            matter.closed_at = datetime.now().isoformat()
            with self._lock:
                self.kb.upsert_matter(matter)
            return CollabResult(
                mode=mode,
                matter_id=matter_id,
                participants=participants,
                output=merged,
                transcript=transcript,
            )

        # SWARM — every bot contributes a snippet, snippets merged.
        if mode == OctoCollabMode.SWARM:
            snippets: List[Dict[str, Any]] = []
            for b in bots:
                payload = self._invoke_hook(hooks, [b], matter)
                snippets.append({"bot_id": b.id, "name": b.name, "snippet": payload})
            merged = {"snippets": snippets, "count": len(snippets)}
            matter.answer = merged
            matter.state = "answered"
            matter.closed_at = datetime.now().isoformat()
            with self._lock:
                self.kb.upsert_matter(matter)
            return CollabResult(
                mode=mode,
                matter_id=matter_id,
                participants=participants,
                output=merged,
            )

        raise ValueError(f"unsupported collaboration mode: {mode!r}")

    # ── internal helpers (legacy) ─────────────────────────────────────
    def _invoke_hook(
        self,
        hooks: Dict[str, Callable[[AgentBot, Matter], Dict[str, Any]]],
        bots: List[AgentBot],
        matter: Matter,
        **extra: Any,
    ) -> Dict[str, Any]:
        if not bots:
            return {"echo": matter.body, "by": "nobody"}
        bot = bots[0]
        hook = hooks.get(bot.id)
        if hook is None:
            return {
                "echo": matter.body,
                "by": bot.name,
                "capabilities": list(bot.capabilities),
                **extra,
            }
        try:
            result = hook(bot, matter)
            if not isinstance(result, dict):
                result = {"value": result}
            return {**extra, **result}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "by": bot.name, **extra}

    def _ensure_channel_for(
        self, bots: List[AgentBot], *, topic: str
    ) -> Channel:
        for ch in self._channels.values():
            if ch.topic == topic and set(ch.bot_ids) == {b.id for b in bots}:
                return ch
        bot_ids = [b.id for b in bots]
        new_id = self.create_channel(topic, bot_ids=bot_ids)
        return self._channels[new_id]

    def _create_default_critic(self, bots: List[AgentBot]) -> AgentBot:
        new_id = self.create_bot(
            name="critic-default",
            persona="adversarial reviewer",
            capabilities=["critique"],
        )
        return self._bots[new_id]


__all__ = [
    "OctoEngine",
    "OctoEngineState",
    "OctoCollabMode",
    "OctoBot",
    "OctoChannel",
    "OctoMatter",
    "CollabResult",
    "DEFAULT_PROMPTS",
    # Bus topic constants
    "TOPIC_BOT_CREATED",
    "TOPIC_CHANNEL_CREATED",
    "TOPIC_MATTER_CREATED",
    "TOPIC_MATTER_ASSIGNED",
    "TOPIC_MATTER_COMPLETED",
    "TOPIC_MESSAGE_POSTED",
]
