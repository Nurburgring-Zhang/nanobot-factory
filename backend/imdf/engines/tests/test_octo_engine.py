"""Tests for :mod:`engines.octo_engine` (P19-B4)."""
from __future__ import annotations

import pytest

from engines.octo_engine import (
    CollabResult,
    OctoBot,
    OctoChannel,
    OctoCollabMode,
    OctoEngine,
    OctoEngineState,
    OctoMatter,
)


class TestOctoEngine:
    def test_instantiate(self):
        engine = OctoEngine()
        assert engine.status()["state"] == OctoEngineState.IDLE.value

    def test_lifecycle(self):
        engine = OctoEngine()
        engine.start()
        assert engine.status()["state"] == OctoEngineState.RUNNING.value
        engine.pause()
        assert engine.status()["state"] == OctoEngineState.PAUSED.value
        engine.resume()
        assert engine.status()["state"] == OctoEngineState.RUNNING.value
        engine.stop()
        assert engine.status()["state"] == OctoEngineState.STOPPED.value

    def test_create_bot_returns_id_and_stores(self):
        engine = OctoEngine()
        bot_id = engine.create_bot("alpha", persona="explorer", capabilities=["search"])
        assert isinstance(bot_id, str)
        bot = engine.get_bot(bot_id)
        assert isinstance(bot, OctoBot)
        assert bot.name == "alpha"
        assert "search" in bot.capabilities

    def test_create_channel_and_matter(self):
        engine = OctoEngine()
        ch_id = engine.create_channel("design", bot_ids=[])
        assert isinstance(engine.get_channel(ch_id), OctoChannel)
        m_id = engine.create_matter("how to onboard", "explain onboarding")
        m = engine.get_matter(m_id)
        assert isinstance(m, OctoMatter)
        assert m.title == "how to onboard"

    def test_execute_solo(self):
        engine = OctoEngine()
        bot = engine.create_bot("solo")
        matter = engine.create_matter("one-question", "answer me")
        result = engine.execute_collab(OctoCollabMode.SOLO, matter, [bot])
        assert isinstance(result, CollabResult)
        assert result.mode == OctoCollabMode.SOLO
        assert result.participants == [bot]
        # SOLO has no transcript
        assert result.transcript == []

    def test_execute_roundtable(self):
        engine = OctoEngine()
        b1 = engine.create_bot("a")
        b2 = engine.create_bot("b")
        m = engine.create_matter("q", "body")
        result = engine.execute_collab(OctoCollabMode.ROUNDTABLE, m, [b1, b2])
        assert result.mode == OctoCollabMode.ROUNDTABLE
        assert len(result.transcript) >= 2

    def test_execute_critic(self):
        engine = OctoEngine()
        proposer = engine.create_bot("p")
        critic = engine.create_bot("c")
        m = engine.create_matter("q", "body")
        result = engine.execute_collab(OctoCollabMode.CRITIC, m, [proposer, critic])
        assert result.mode == OctoCollabMode.CRITIC

    def test_execute_pipeline(self):
        engine = OctoEngine()
        b1 = engine.create_bot("step1")
        b2 = engine.create_bot("step2")
        m = engine.create_matter("q", "body")
        result = engine.execute_collab(OctoCollabMode.PIPELINE, m, [b1, b2])
        assert result.mode == OctoCollabMode.PIPELINE
        assert "payload" in result.output

    def test_execute_split_creates_sub_matters(self):
        engine = OctoEngine()
        b1 = engine.create_bot("shard-1")
        b2 = engine.create_bot("shard-2")
        m = engine.create_matter("q", "body")
        result = engine.execute_collab(OctoCollabMode.SPLIT, m, [b1, b2])
        assert result.mode == OctoCollabMode.SPLIT
        assert len(result.output["shards"]) == 2

    def test_execute_swarm(self):
        engine = OctoEngine()
        b1 = engine.create_bot("bee-1")
        b2 = engine.create_bot("bee-2")
        m = engine.create_matter("q", "body")
        result = engine.execute_collab(OctoCollabMode.SWARM, m, [b1, b2])
        assert result.mode == OctoCollabMode.SWARM
        assert result.output["count"] == 2

    def test_execute_collab_unknown_matter_raises(self):
        engine = OctoEngine()
        with pytest.raises(KeyError):
            engine.execute_collab(OctoCollabMode.SOLO, "missing-matter", [])

    def test_status_envelope_shape(self):
        engine = OctoEngine()
        b = engine.create_bot("b")
        engine.create_matter("m", "")
        s = engine.status()
        assert set(s.keys()) >= {"state", "bots", "channels", "matters", "open_matters"}
        assert s["bots"] == 1
        assert s["open_matters"] == 1