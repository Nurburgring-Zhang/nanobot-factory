"""V5 第25章 — OctoEngine 的内存知识库 (OctoKB).

Threading-safe in-memory store that holds:

* bots        — Dict[bot_id, AgentBot]
* channels    — Dict[channel_id, Channel]
* matters     — Dict[matter_id, Matter]
* messages    — List[ThreadMessage]   (chronological, cross-channel)
* skill_bindings — Dict[bot_id, List[skill_id]]

A future swap-in SQLite or Redis backend only needs to subclass
:class:`OctoKB` and override ``upsert_bot`` / ``upsert_channel`` /
``upsert_matter`` / ``append_message``.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, Iterable, List, Optional

from .octo_schemas import AgentBot, Channel, Matter, ThreadMessage

logger = logging.getLogger(__name__)


class OctoKB:
    """In-memory storage for the Octo 4-concept model.

    Methods that return collections return *copies* — callers may mutate
    them freely without disturbing the engine's authoritative state.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bots: Dict[str, AgentBot] = {}
        self._channels: Dict[str, Channel] = {}
        self._matters: Dict[str, Matter] = {}
        self._messages: List[ThreadMessage] = []
        # bot_id -> [skill_id,...]
        self._skill_bindings: Dict[str, List[str]] = {}

    # ── bots ──────────────────────────────────────────────────────────
    def upsert_bot(self, bot: AgentBot) -> None:
        with self._lock:
            self._bots[bot.id] = bot

    def get_bot(self, bot_id: str) -> Optional[AgentBot]:
        with self._lock:
            return self._bots.get(bot_id)

    def list_bots(self) -> List[AgentBot]:
        with self._lock:
            return list(self._bots.values())

    def find_bots_by_capability(self, capability: str) -> List[AgentBot]:
        with self._lock:
            return [b for b in self._bots.values() if capability in b.capabilities]

    def delete_bot(self, bot_id: str) -> bool:
        with self._lock:
            return self._bots.pop(bot_id, None) is not None

    # ── skill bindings ───────────────────────────────────────────────
    def bind_skill(self, bot_id: str, skill_id: str) -> bool:
        with self._lock:
            if bot_id not in self._bots:
                return False
            skills = self._skill_bindings.setdefault(bot_id, [])
            if skill_id not in skills:
                skills.append(skill_id)
            # Also expose skill_id as a capability
            bot = self._bots[bot_id]
            if skill_id not in bot.capabilities:
                bot.capabilities.append(skill_id)
            return True

    def list_skills_for_bot(self, bot_id: str) -> List[str]:
        with self._lock:
            return list(self._skill_bindings.get(bot_id, []))

    # ── channels ──────────────────────────────────────────────────────
    def upsert_channel(self, channel: Channel) -> None:
        with self._lock:
            self._channels[channel.id] = channel

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        with self._lock:
            return self._channels.get(channel_id)

    def list_channels(self) -> List[Channel]:
        with self._lock:
            return list(self._channels.values())

    def delete_channel(self, channel_id: str) -> bool:
        with self._lock:
            return self._channels.pop(channel_id, None) is not None

    # ── matters ───────────────────────────────────────────────────────
    def upsert_matter(self, matter: Matter) -> None:
        with self._lock:
            self._matters[matter.id] = matter

    def get_matter(self, matter_id: str) -> Optional[Matter]:
        with self._lock:
            return self._matters.get(matter_id)

    def list_matters(self, channel_id: Optional[str] = None) -> List[Matter]:
        with self._lock:
            if channel_id is None:
                return list(self._matters.values())
            return [m for m in self._matters.values() if m.channel_id == channel_id]

    def delete_matter(self, matter_id: str) -> bool:
        with self._lock:
            return self._matters.pop(matter_id, None) is not None

    # ── messages (cross-channel chronological log) ────────────────────
    def append_message(self, message: ThreadMessage) -> None:
        with self._lock:
            self._messages.append(message)

    def list_messages(
        self,
        channel_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        limit: int = 1000,
    ) -> List[ThreadMessage]:
        with self._lock:
            out: List[ThreadMessage] = []
            for msg in self._messages:
                if channel_id is not None and msg.metadata.get("channel_id") != channel_id:
                    continue
                if thread_id is not None and msg.metadata.get("thread_id") != thread_id:
                    continue
                if sender_id is not None and msg.sender_id != sender_id:
                    continue
                out.append(msg)
                if len(out) >= limit:
                    break
            return out

    # ── engine-level health snapshot ──────────────────────────────────
    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "bots": len(self._bots),
                "channels": len(self._channels),
                "matters": len(self._matters),
                "open_matters": sum(
                    1 for m in self._matters.values()
                    if m.status not in {"done", "cancelled", "failed"}
                ),
                "messages": len(self._messages),
                "skill_bindings": sum(len(v) for v in self._skill_bindings.values()),
            }

    def reset(self) -> None:
        """Wipe everything — useful in tests."""
        with self._lock:
            self._bots.clear()
            self._channels.clear()
            self._matters.clear()
            self._messages.clear()
            self._skill_bindings.clear()


__all__ = ["OctoKB"]
