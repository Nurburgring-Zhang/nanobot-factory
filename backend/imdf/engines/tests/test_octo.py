"""V5 第25章 — Octo 协作网络 tests (P19 v5.3).

Covers the 4-concept model:

* **Bot**  — create / assign_skill / list / get_by_capability / 6 prompts
* **Channel** — create / add / remove member / list
* **Matter** — create / assign / complete (with acceptance criteria) / list
* **Thread** — post_message / list_messages
* **Bus events** — all 6 octo.* topics emitted
* **End-to-end** — full happy path: create coder bot → channel → matter
  → post messages → complete
"""
from __future__ import annotations

import pytest

from engines.octo_engine import (
    CollabResult,
    OctoCollabMode,
    OctoEngine,
    OctoEngineState,
    TOPIC_BOT_CREATED,
    TOPIC_CHANNEL_CREATED,
    TOPIC_MATTER_ASSIGNED,
    TOPIC_MATTER_COMPLETED,
    TOPIC_MATTER_CREATED,
    TOPIC_MESSAGE_POSTED,
)
from engines.octo_schemas import (
    AgentBot,
    AgentType,
    Channel,
    Matter,
    MatterStatus,
    OctoBot,
    OctoChannel,
    OctoMatter,
    ThreadMessage,
)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
class _StubSkillEngine:
    """Permissive stub skill engine for tests — accepts every skill id."""

    def __init__(self, allowed: list[str] | None = None) -> None:
        self._allowed = set(allowed) if allowed is not None else None
        self.calls: list[str] = []

    def get_skill(self, skill_id: str):
        self.calls.append(skill_id)
        if self._allowed is not None and skill_id not in self._allowed:
            return None
        return {"skill_id": skill_id, "name": skill_id}


class _StubBus:
    """Records every ``record()`` call for inspection."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, *, topic, entity_type, entity_id, payload, actor, source_module, **kw):
        self.events.append({
            "topic": topic,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "actor": actor,
            "source_module": source_module,
        })
        return len(self.events)


@pytest.fixture
def bus() -> _StubBus:
    return _StubBus()


@pytest.fixture
def skill_engine() -> _StubSkillEngine:
    return _StubSkillEngine()


@pytest.fixture
def engine(bus, skill_engine) -> OctoEngine:
    return OctoEngine(skill_engine=skill_engine, bus=bus)


# --------------------------------------------------------------------------- #
#  Bot lifecycle (5 tests)
# --------------------------------------------------------------------------- #
class TestBotLifecycle:
    def test_create_bot_returns_id_and_persists(self, engine: OctoEngine) -> None:
        bot_id = engine.create_bot("Alice", agent_type=AgentType.CODER.value, capabilities=["python", "testing"])
        assert isinstance(bot_id, str) and bot_id.startswith("bot_")
        bot = engine.get_bot(bot_id)
        assert isinstance(bot, OctoBot)
        assert bot is not None
        assert bot.name == "Alice"
        assert bot.id == bot.bot_id
        assert "python" in bot.capabilities
        assert bot.agent_type == AgentType.CODER.value
        assert bot.status == "active"
        # Default prompt was set.
        assert bot.system_prompt
        assert "code" in bot.system_prompt.lower()

    def test_create_bot_with_custom_system_prompt(self, engine: OctoEngine) -> None:
        bot_id = engine.create_bot("BotX", system_prompt="CUSTOM PROMPT")
        assert engine.get_bot(bot_id).system_prompt == "CUSTOM PROMPT"

    def test_list_bots(self, engine: OctoEngine) -> None:
        engine.create_bot("a")
        engine.create_bot("b")
        engine.create_bot("c")
        bots = engine.list_bots()
        assert len(bots) == 3
        names = {b.name for b in bots}
        assert names == {"a", "b", "c"}

    def test_assign_skill_to_bot_uses_skill_engine(self, engine: OctoEngine, skill_engine: _StubSkillEngine) -> None:
        bot_id = engine.create_bot("Bob")
        assert engine.assign_skill_to_bot(bot_id, "write_poem") is True
        # The skill engine was queried.
        assert "write_poem" in skill_engine.calls
        # The skill id ended up in bot.capabilities.
        assert "write_poem" in engine.get_bot(bot_id).capabilities
        # And in the work_history + ability_description.
        bot = engine.get_bot(bot_id)
        assert "write_poem" in bot.agent_card.ability_description
        assert any(
            h.get("event") == "skill_assigned" and h.get("skill_id") == "write_poem"
            for h in bot.agent_card.work_history
        )

    def test_assign_skill_to_unknown_bot_returns_false(self, engine: OctoEngine) -> None:
        assert engine.assign_skill_to_bot("bot_does_not_exist", "x") is False

    def test_assign_skill_engine_rejects_unknown_skill(self, engine: OctoEngine) -> None:
        # Swap to a strict skill engine that rejects "evil".
        engine.skill_engine = _StubSkillEngine(allowed=["good"])
        bot_id = engine.create_bot("Strict")
        assert engine.assign_skill_to_bot(bot_id, "good") is True
        assert engine.assign_skill_to_bot(bot_id, "evil") is False


# --------------------------------------------------------------------------- #
#  Bot capability lookup + default prompts (4 tests)
# --------------------------------------------------------------------------- #
class TestBotCapabilityAndPrompts:
    def test_get_bot_by_capability(self, engine: OctoEngine) -> None:
        engine.create_bot("py_dev", capabilities=["python", "fastapi"])
        engine.create_bot("writer", capabilities=["copywriting", "blog"])
        engine.create_bot("full_stack", capabilities=["python", "react"])
        found = engine.get_bot_by_capability("python")
        names = {b.name for b in found}
        assert names == {"py_dev", "full_stack"}
        assert engine.get_bot_by_capability("nonexistent") == []

    @pytest.mark.parametrize(
        "agent_type",
        [AgentType.CODER.value, AgentType.REVIEWER.value, AgentType.WRITER.value,
         AgentType.ANALYST.value, AgentType.RESEARCHER.value, AgentType.GENERIC.value],
    )
    def test_default_prompt_for_all_6_agent_types(self, engine: OctoEngine, agent_type: str) -> None:
        prompt = engine._default_prompt(agent_type)
        assert isinstance(prompt, str) and len(prompt) > 20
        bot_id = engine.create_bot(f"bot_{agent_type}", agent_type=agent_type)
        assert prompt == engine.get_bot(bot_id).system_prompt

    def test_default_prompt_unknown_falls_back_to_generic(self, engine: OctoEngine) -> None:
        prompt = engine._default_prompt("doesnt_exist")
        generic = engine._default_prompt(AgentType.GENERIC.value)
        assert prompt == generic

    def test_bot_card_populated_on_create(self, engine: OctoEngine) -> None:
        bot_id = engine.create_bot("Carla", capabilities=["python", "rust"])
        bot = engine.get_bot(bot_id)
        assert bot.agent_card is not None
        assert "python" in bot.agent_card.ability_description
        assert "rust" in bot.agent_card.ability_description
        assert bot.agent_card.owner == "system"
        assert bot.agent_card.work_history == []


# --------------------------------------------------------------------------- #
#  Channel lifecycle (4 tests)
# --------------------------------------------------------------------------- #
class TestChannelLifecycle:
    def test_create_channel_basic(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("DataPipeline", description="ETL discussions", project_id="proj_1")
        ch = engine.get_channel(ch_id)
        assert isinstance(ch, OctoChannel)
        assert ch.name == "DataPipeline"
        assert ch.topic == "DataPipeline"  # legacy alias
        assert ch.description == "ETL discussions"
        assert ch.project_id == "proj_1"
        assert ch.id == ch.channel_id

    def test_create_channel_legacy_topic(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("design", bot_ids=["bot_a", "bot_b"])
        ch = engine.get_channel(ch_id)
        assert ch is not None
        # Both bot_ids and members are populated.
        assert "bot_a" in ch.bot_ids
        assert "bot_a" in ch.members
        assert "bot_b" in ch.bot_ids

    def test_add_and_remove_member(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("team")
        assert engine.add_member_to_channel(ch_id, "user_1") is True
        assert engine.add_member_to_channel(ch_id, "bot_abc") is True
        ch = engine.get_channel(ch_id)
        assert "user_1" in ch.members
        assert "bot_abc" in ch.members
        assert "bot_abc" in ch.bot_ids

        # Idempotent add
        assert engine.add_member_to_channel(ch_id, "user_1") is True

        assert engine.remove_member_from_channel(ch_id, "user_1") is True
        ch = engine.get_channel(ch_id)
        assert "user_1" not in ch.members
        # Removing again is a no-op (returns True because member wasn't there, but doesn't error).
        engine.remove_member_from_channel(ch_id, "user_1")  # no exception

    def test_add_remove_unknown_channel(self, engine: OctoEngine) -> None:
        assert engine.add_member_to_channel("chan_missing", "user_1") is False
        assert engine.remove_member_from_channel("chan_missing", "user_1") is False

    def test_list_channels(self, engine: OctoEngine) -> None:
        engine.create_channel("a")
        engine.create_channel("b")
        chans = engine.list_channels()
        assert len(chans) == 2
        assert {c.name for c in chans} == {"a", "b"}


# --------------------------------------------------------------------------- #
#  Matter lifecycle (5 tests)
# --------------------------------------------------------------------------- #
class TestMatterLifecycle:
    def test_create_matter_v5_signature_requires_channel(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        matter_id = engine.create_matter(
            ch_id, "Build WebDataset",
            assignee_type="bot", assignee_id="bot_alice",
            deliverable={"format": "tar", "samples": 1000},
            acceptance_criteria=["deliverable.format", "deliverable.samples"],
        )
        matter = engine.get_matter(matter_id)
        assert isinstance(matter, OctoMatter)
        assert matter is not None
        assert matter.title == "Build WebDataset"
        assert matter.assignee_type == "bot"
        assert matter.assignee_id == "bot_alice"
        assert matter.deliverable == {"format": "tar", "samples": 1000}
        assert matter.acceptance_criteria == ["deliverable.format", "deliverable.samples"]
        assert matter.status == MatterStatus.DRAFT.value
        # A thread was created in the channel with a system message.
        ch = engine.get_channel(ch_id)
        assert len(ch.threads) == 1
        assert ch.threads[0].matter_id == matter_id

    def test_create_matter_v5_unknown_channel_raises(self, engine: OctoEngine) -> None:
        with pytest.raises(ValueError, match="Channel"):
            engine.create_matter("chan_ghost", "Ghost Matter", assignee_type="user", assignee_id="u_1")

    def test_assign_matter_marks_assigned(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        matter_id = engine.create_matter(ch_id, "task")
        assert engine.assign_matter(matter_id, "bot_alice") is True
        m = engine.get_matter(matter_id)
        assert m.assignee_id == "bot_alice"
        assert m.assignee_type == "bot"
        assert m.status == MatterStatus.ASSIGNED.value
        # Idempotent re-assign.
        assert engine.assign_matter(matter_id, "bot_alice") is True

    def test_complete_matter_with_criteria_met(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        matter_id = engine.create_matter(
            ch_id, "task",
            deliverable={"format": "tar", "samples": 1000},
            acceptance_criteria=["format", "samples"],
        )
        engine.assign_matter(matter_id, "bot_alice")
        result = {"format": "tar", "samples": 1000}
        assert engine.complete_matter(matter_id, result) is True
        m = engine.get_matter(matter_id)
        assert m.status == MatterStatus.DONE.value
        assert m.closed_at is not None
        assert m.deliverable["result"] == result

    def test_complete_matter_with_criteria_unmet_goes_to_review(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        matter_id = engine.create_matter(
            ch_id, "task",
            deliverable={"format": "tar"},
            acceptance_criteria=["format", "samples"],
        )
        # result lacks 'samples' so criteria are not met
        assert engine.complete_matter(matter_id, {"format": "tar"}) is False
        m = engine.get_matter(matter_id)
        assert m.status == MatterStatus.REVIEW.value
        assert m.feedback is not None
        assert "samples" in m.feedback["criteria_unmet"]

    def test_complete_matter_force_skips_criteria(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        matter_id = engine.create_matter(
            ch_id, "task",
            acceptance_criteria=["format", "samples"],
        )
        # force=True bypasses the criteria check.
        assert engine.complete_matter(matter_id, {}, force=True) is True
        assert engine.get_matter(matter_id).status == MatterStatus.DONE.value

    def test_list_matters(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        engine.create_matter(ch_id, "a")
        engine.create_matter(ch_id, "b")
        all_matters = engine.list_matters()
        assert len(all_matters) == 2
        ch_matters = engine.list_matters(channel_id=ch_id)
        assert len(ch_matters) == 2
        assert engine.list_matters(channel_id="chan_other") == []


# --------------------------------------------------------------------------- #
#  Thread / message tests (3 tests)
# --------------------------------------------------------------------------- #
class TestThreadMessages:
    def test_post_message_returns_thread_message(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        msg = engine.post_message(ch_id, "user_1", "Hello world")
        assert isinstance(msg, ThreadMessage)
        assert msg.sender_id == "user_1"
        assert msg.content == "Hello world"
        assert msg.role == "user"
        assert msg.metadata.get("channel_id") == ch_id
        assert msg.metadata.get("thread_id")  # auto-created

    def test_post_message_unknown_channel_returns_none(self, engine: OctoEngine) -> None:
        assert engine.post_message("chan_ghost", "u_1", "hi") is None

    def test_list_messages_filtered(self, engine: OctoEngine) -> None:
        ch_id = engine.create_channel("proj")
        engine.post_message(ch_id, "user_1", "msg-1")
        engine.post_message(ch_id, "bot_alice", "msg-2")
        msgs = engine.list_messages(channel_id=ch_id)
        assert len(msgs) == 2
        assert {m.sender_id for m in msgs} == {"user_1", "bot_alice"}
        assert engine.list_messages(channel_id="chan_other") == []


# --------------------------------------------------------------------------- #
#  Bus event coverage (1 test, all 6 topics)
# --------------------------------------------------------------------------- #
class TestBusEvents:
    def test_all_six_octo_bus_topics_emitted(self, engine: OctoEngine, bus: _StubBus) -> None:
        topics_seen: set[str] = set()

        ch_id = engine.create_channel("proj")
        topics_seen.add(TOPIC_CHANNEL_CREATED)
        bot_id = engine.create_bot("Alice", capabilities=["python"])
        topics_seen.add(TOPIC_BOT_CREATED)
        # Create matter without pre-assigning so the assign step actually fires.
        matter_id = engine.create_matter(ch_id, "task", assignee_type="bot")
        topics_seen.add(TOPIC_MATTER_CREATED)
        engine.assign_matter(matter_id, bot_id)
        topics_seen.add(TOPIC_MATTER_ASSIGNED)
        engine.complete_matter(matter_id, {"ok": True}, force=True)
        topics_seen.add(TOPIC_MATTER_COMPLETED)
        engine.post_message(ch_id, bot_id, "Working on it")
        topics_seen.add(TOPIC_MESSAGE_POSTED)

        # All 6 expected topics reached the real bus.
        bus_topics = {ev["topic"] for ev in bus.events}
        assert {
            TOPIC_BOT_CREATED,
            TOPIC_CHANNEL_CREATED,
            TOPIC_MATTER_CREATED,
            TOPIC_MATTER_ASSIGNED,
            TOPIC_MATTER_COMPLETED,
            TOPIC_MESSAGE_POSTED,
        }.issubset(bus_topics)

        # And the local bus_events recorder has the same topics.
        local_topics = {ev["topic"] for ev in engine.bus_events}
        for t in topics_seen:
            assert t in local_topics

        # source_module tag is "octo"
        for ev in bus.events:
            assert ev["source_module"] == "octo"

    def test_engine_works_without_bus_or_skill_engine(self) -> None:
        # No bus, no skill_engine — permissive fallback should still allow full flow.
        eng = OctoEngine()
        ch_id = eng.create_channel("proj")
        bot_id = eng.create_bot("Solo", capabilities=["python"])
        matter_id = eng.create_matter(ch_id, "task", assignee_type="bot", assignee_id=bot_id)
        eng.assign_matter(matter_id, bot_id)
        # Without a skill engine, every skill id is accepted.
        assert eng.assign_skill_to_bot(bot_id, "any_skill") is True
        assert eng.complete_matter(matter_id, {"ok": True}, force=True) is True
        # Local bus_events were recorded.
        assert any(ev["topic"] == TOPIC_BOT_CREATED for ev in eng.bus_events)


# --------------------------------------------------------------------------- #
#  End-to-end example (1 test) — exact scenario from the V5 doc & task brief
# --------------------------------------------------------------------------- #
class TestE2EExample:
    def test_create_coder_bot_alice_full_pipeline(self) -> None:
        """E2E — documented example from V5 ch.25 / task brief."""
        bus = _StubBus()
        skill_engine = _StubSkillEngine(allowed=["python", "testing"])
        eng = OctoEngine(skill_engine=skill_engine, bus=bus)

        # 1. create coder bot 'Alice' with python+testing skills
        alice_id = eng.create_bot(
            "Alice",
            agent_type=AgentType.CODER.value,
            capabilities=["python", "testing"],
        )
        assert eng.assign_skill_to_bot(alice_id, "python") is True
        assert eng.assign_skill_to_bot(alice_id, "testing") is True
        alice = eng.get_bot(alice_id)
        assert "python" in alice.capabilities
        assert "testing" in alice.capabilities
        assert alice.agent_type == AgentType.CODER.value

        # 2. create channel 'DataPipeline' with Alice + 2 human members
        ch_id = eng.create_channel(
            "DataPipeline",
            description="ETL pipeline coordination",
            members=[alice_id, "user_bob", "user_carol"],
            project_id="proj_dp",
        )
        ch = eng.get_channel(ch_id)
        assert "user_bob" in ch.members
        assert "user_carol" in ch.members
        assert alice_id in ch.members

        # 3. create matter 'Build WebDataset' — then assign to Alice
        matter_id = eng.create_matter(
            ch_id,
            "Build WebDataset",
            assignee_type="bot",
            deliverable={"format": "tar", "samples": 1000, "shard_size_mb": 50},
            acceptance_criteria=[
                "deliverable.format",
                "deliverable.samples",
                "deliverable.shard_size_mb",
            ],
        )
        m = eng.get_matter(matter_id)
        assert m.status == MatterStatus.DRAFT.value
        # Now assign Alice (this fires the matter_assigned bus event).
        eng.assign_matter(matter_id, alice_id)
        m = eng.get_matter(matter_id)
        assert m.assignee_id == alice_id
        assert m.assignee_type == "bot"
        assert m.status == MatterStatus.ASSIGNED.value

        # 4. post messages
        msg1 = eng.post_message(ch_id, "user_bob", "Please start today")
        msg2 = eng.post_message(ch_id, alice_id, "Acknowledged, ETA tomorrow")
        msg3 = eng.post_message(ch_id, alice_id, "Done — see deliverables", role="bot")
        assert msg1 is not None and msg2 is not None and msg3 is not None
        msgs = eng.list_messages(channel_id=ch_id)
        assert len(msgs) >= 3
        assert {m.sender_id for m in msgs} >= {"user_bob", alice_id}

        # 5. complete matter when acceptance criteria met
        result = {
            "deliverable": {
                "format": "tar",
                "samples": 1000,
                "shard_size_mb": 50,
            }
        }
        assert eng.complete_matter(matter_id, result) is True
        finished = eng.get_matter(matter_id)
        assert finished.status == MatterStatus.DONE.value
        assert finished.closed_at is not None

        # 6. status snapshot reflects all 4 concepts
        snap = eng.status()
        assert snap["bots"] == 1
        assert snap["channels"] == 1
        assert snap["matters"] == 1
        assert snap["open_matters"] == 0  # matter is done
        assert snap["messages"] >= 3
        assert snap["skill_bindings"] == 2  # python + testing

        # 7. all 6 bus topics reached the real bus
        bus_topics = {ev["topic"] for ev in bus.events}
        assert {TOPIC_BOT_CREATED, TOPIC_CHANNEL_CREATED, TOPIC_MATTER_CREATED,
                TOPIC_MATTER_ASSIGNED, TOPIC_MATTER_COMPLETED, TOPIC_MESSAGE_POSTED}.issubset(bus_topics)


# --------------------------------------------------------------------------- #
#  Backward-compat smoke (1 test) — legacy 6-mode API still works
# --------------------------------------------------------------------------- #
class TestBackwardCompat:
    def test_legacy_6_mode_solo_still_works(self) -> None:
        eng = OctoEngine()
        bot = eng.create_bot("solo")
        matter = eng.create_matter("one", "body")
        result = eng.execute_collab(OctoCollabMode.SOLO, matter, [bot])
        assert isinstance(result, CollabResult)
        assert result.mode == OctoCollabMode.SOLO
        assert result.participants == [bot]

    def test_legacy_engine_state_idle(self) -> None:
        eng = OctoEngine()
        assert eng.status()["state"] == OctoEngineState.IDLE.value
        eng.start()
        assert eng.status()["state"] == OctoEngineState.RUNNING.value
        eng.stop()
        assert eng.status()["state"] == OctoEngineState.STOPPED.value
