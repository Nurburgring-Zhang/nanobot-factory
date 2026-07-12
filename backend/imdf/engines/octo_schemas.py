"""V5 第25章 — Octo Agent 协作网络 Pydantic v2 schemas.

The four collaboration concepts:

* **Bot**      — Agent identity (AgentBot + AgentCard).
                 Connects to OpenClaw, Hermes, Codex, Claude Code, WorkBuddy.
* **Channel**  — A project team / workspace where humans and bots
                 discuss intent and plan together.
* **Thread**   — One specific event / topic — its context, discussion,
                 and conclusion live in one place.
* **Matter**   — A deliverable — has owner, deliverable spec,
                 acceptance criteria, and a full history of record.

The schemas also re-export the legacy dataclass names (``OctoBot`` /
``OctoChannel`` / ``OctoMatter``) used by the existing 6-mode
``execute_collab`` API.  Both ``OctoBot`` and ``AgentBot`` resolve to
the same Pydantic model so that older code keeps an ``isinstance``
green check.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- #
#  Enums
# --------------------------------------------------------------------------- #
class MatterStatus(str, Enum):
    """Matter lifecycle states (V5 ch.25 §25.4)."""

    DRAFT = "draft"             # matter created but not yet assigned
    ASSIGNED = "assigned"       # owner (user or bot) is chosen
    IN_PROGRESS = "in_progress" # owner is actively working
    REVIEW = "review"           # deliverables submitted, awaiting review
    DONE = "done"               # accepted — finished
    CANCELLED = "cancelled"     # abandoned (terminal)
    FAILED = "failed"           # review rejected (terminal)


class ChannelRole(str, Enum):
    """Channel member roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    OBSERVER = "observer"


class AgentType(str, Enum):
    """Bot agent_type — powers ``_default_prompt`` dispatch."""

    CODER = "coder"
    REVIEWER = "reviewer"
    WRITER = "writer"
    ANALYST = "analyst"
    RESEARCHER = "researcher"
    GENERIC = "generic"


# --------------------------------------------------------------------------- #
#  Bot
# --------------------------------------------------------------------------- #
class AgentCard(BaseModel):
    """Bot 公开名片 — 身份、能力描述、工作历史.

    Mirrors the `AgentCard` shape from the V5 chapter §25.2.
    """

    model_config = ConfigDict(extra="allow")

    owner: str = "system"
    ability_description: str = ""
    work_history: List[Dict[str, Any]] = Field(default_factory=list)


class AgentBot(BaseModel):
    """Bot (Agent 身份) — V5 ch.25.

    Fields are organized in two groups:

    * **V5 doc-shape** — fields shown in the chapter 25 source:
      ``id``, ``name``, ``agent_type``, ``capabilities``,
      ``agent_card``, ``status``, ``system_prompt``, ``created_at``.
    * **Legacy compat** — kept so the old ``OctoBot`` API still
      works: ``bot_id`` (=id), ``persona``, ``metadata``.
    """

    model_config = ConfigDict(extra="allow")

    # V5 doc-shape
    id: str = Field(default_factory=lambda: _new_id("bot"))
    name: str
    agent_type: str = "generic"
    capabilities: List[str] = Field(default_factory=list)
    agent_card: AgentCard = Field(default_factory=AgentCard)
    status: str = "active"
    system_prompt: str = ""
    created_at: str = Field(default_factory=_now_iso)

    # Legacy compat (P19-B4 dataclass)
    bot_id: Optional[str] = None
    persona: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # Sync legacy ``bot_id`` with ``id`` so old callers that touch
        # ``bot.bot_id`` see the same value.
        if not self.bot_id:
            object.__setattr__(self, "bot_id", self.id)

    def add_work_history(self, item: Dict[str, Any]) -> None:
        self.agent_card.work_history.append(item)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# --------------------------------------------------------------------------- #
#  Channel
# --------------------------------------------------------------------------- #
class ThreadMessage(BaseModel):
    """A single message inside a Thread / Channel."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: _new_id("msg"))
    sender_id: str = ""
    role: str = "user"          # user / bot / system
    content: str = ""
    timestamp: str = Field(default_factory=_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Thread(BaseModel):
    """Thread — specific event (one thing's context + discussion + conclusion)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: _new_id("thr"))
    channel_id: Optional[str] = None
    matter_id: Optional[str] = None
    title: str = ""
    messages: List[ThreadMessage] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    closed_at: Optional[str] = None

    def post_message(
        self,
        sender_id: str,
        content: str,
        *,
        role: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ThreadMessage:
        msg = ThreadMessage(
            sender_id=sender_id,
            role=role,
            content=content,
            metadata=dict(metadata or {}),
        )
        self.messages.append(msg)
        return msg


class Channel(BaseModel):
    """Channel — project team / workspace.

    V5 doc fields: ``id``, ``name``, ``description``, ``members``,
    ``threads``, ``project_id``, ``created_at``.

    Legacy compat: ``channel_id``, ``topic``, ``bot_ids``.
    """

    model_config = ConfigDict(extra="allow")

    # V5 doc
    id: str = Field(default_factory=lambda: _new_id("chan"))
    name: str
    description: str = ""
    members: List[str] = Field(default_factory=list)
    threads: List[Thread] = Field(default_factory=list)
    project_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)

    # Legacy compat (P19-B4 dataclass)
    channel_id: Optional[str] = None
    topic: str = ""
    bot_ids: List[str] = Field(default_factory=list)
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.channel_id:
            object.__setattr__(self, "channel_id", self.id)
        if not self.topic:
            object.__setattr__(self, "topic", self.name)

    def add_member(self, member_id: str) -> bool:
        if member_id not in self.members:
            self.members.append(member_id)
        if member_id not in self.bot_ids and member_id.startswith("bot"):
            self.bot_ids.append(member_id)
        return True

    def remove_member(self, member_id: str) -> bool:
        changed = False
        if member_id in self.members:
            self.members.remove(member_id)
            changed = True
        if member_id in self.bot_ids:
            self.bot_ids.remove(member_id)
            changed = True
        return changed

    def new_thread(self, title: str = "", matter_id: Optional[str] = None) -> Thread:
        thread = Thread(
            channel_id=self.id,
            matter_id=matter_id,
            title=title or self.name,
        )
        self.threads.append(thread)
        return thread

    def post(
        self, bot_id: str, content: str, kind: str = "message"
    ) -> Dict[str, Any]:
        """Legacy `OctoChannel.post` API — raw dict message."""
        msg = {
            "message_id": uuid.uuid4().hex[:8],
            "bot_id": bot_id,
            "kind": kind,
            "content": content,
            "timestamp": _now_iso(),
        }
        self.messages.append(msg)
        return msg

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# --------------------------------------------------------------------------- #
#  Matter
# --------------------------------------------------------------------------- #
class Matter(BaseModel):
    """Matter — deliverable (V5 ch.25 §25.4).

    V5 doc fields: ``id``, ``channel_id``, ``title``, ``assignee_type``,
    ``assignee_id``, ``deliverable``, ``acceptance_criteria``,
    ``status``, ``created_at``, ``updated_at``.

    Legacy compat: ``matter_id``, ``body``, ``state``, ``claimed_by``,
    ``answer``, ``closed_at``.
    """

    model_config = ConfigDict(extra="allow")

    # V5 doc
    id: str = Field(default_factory=lambda: _new_id("mat"))
    channel_id: Optional[str] = None
    title: str
    assignee_type: str = "user"        # user or bot
    assignee_id: Optional[str] = None
    deliverable: Dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: List[str] = Field(default_factory=list)
    status: str = MatterStatus.DRAFT.value
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    # Legacy compat
    matter_id: Optional[str] = None
    body: str = ""
    state: str = "open"
    claimed_by: Optional[str] = None
    answer: Dict[str, Any] = Field(default_factory=dict)
    closed_at: Optional[str] = None
    feedback: Optional[Dict[str, Any]] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.matter_id:
            object.__setattr__(self, "matter_id", self.id)

    # ── Helpers ──────────────────────────────────────────────────────
    def meets_acceptance(self, result: Optional[Dict[str, Any]] = None) -> bool:
        """Check whether ``result`` satisfies every acceptance criterion.

        A criterion is a string that must appear as a key or substring in
        ``result``.  This is intentionally lenient — it gives a deterministic
        "yes/no" signal for the ``complete_matter`` gate.
        """
        result = result or {}
        flat = _flatten(result)
        for criterion in self.acceptance_criteria or []:
            if not criterion:
                continue
            if criterion in flat:
                continue
            if any(criterion in str(v) for v in flat.values()):
                continue
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dicts/lists using dotted keys."""
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                out.update(_flatten(v, key))
            else:
                out[key] = v
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}.{i}" if prefix else str(i)))
    else:
        out[prefix or "value"] = obj
    return out


# --------------------------------------------------------------------------- #
#  Backwards-compat aliases — keep ``OctoBot`` / ``OctoChannel`` / ``OctoMatter``
#  working for the existing 6-mode ``execute_collab`` callers.
# --------------------------------------------------------------------------- #
OctoBot = AgentBot
OctoChannel = Channel
OctoMatter = Matter

__all__ = [
    "AgentBot",
    "AgentCard",
    "AgentType",
    "Channel",
    "ChannelRole",
    "Matter",
    "MatterStatus",
    "OctoBot",
    "OctoChannel",
    "OctoMatter",
    "Thread",
    "ThreadMessage",
    "_flatten",
    "_now_iso",
    "_new_id",
]
