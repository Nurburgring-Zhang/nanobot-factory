"""Tests for :mod:`engines.agent_engine` (P19-B4)."""
from __future__ import annotations

import pytest

from engines.agent_engine import (
    AgentEngine,
    AgentEngineState,
    AgentInvocation,
    AgentSession,
)


class TestAgentEngine:
    def test_instantiate(self):
        engine = AgentEngine(auto_register_builtin=False)
        status = engine.status()
        assert status["state"] == AgentEngineState.IDLE.value

    def test_lifecycle_transitions(self):
        engine = AgentEngine(auto_register_builtin=False)
        engine.start()
        assert engine.status()["state"] == AgentEngineState.RUNNING.value
        engine.pause()
        assert engine.status()["state"] == AgentEngineState.PAUSED.value
        engine.resume()
        assert engine.status()["state"] == AgentEngineState.RUNNING.value
        engine.stop()
        assert engine.status()["state"] == AgentEngineState.STOPPED.value

    def test_registered_agents_returns_list(self):
        engine = AgentEngine(auto_register_builtin=False)
        assert engine.registered_agents() == []

    def test_invoke_agent_creates_record(self):
        engine = AgentEngine(auto_register_builtin=False)
        record = engine.invoke_agent("cleaning", {"items": []}, mode="full_auto")
        assert isinstance(record, AgentInvocation)
        assert record.agent_type == "cleaning"
        assert record.status in {"submitted", "done", "failed"}
        # routing metadata captured
        assert "routing" in record.output

    def test_invoke_agent_validates_input(self):
        engine = AgentEngine(auto_register_builtin=False)
        with pytest.raises(ValueError):
            engine.invoke_agent("", {"items": []})
        with pytest.raises(TypeError):
            engine.invoke_agent("cleaning", [])  # type: ignore[arg-type]

    def test_agent_session_roundtrip(self):
        engine = AgentEngine(auto_register_builtin=False)
        sess = engine.agent_session("sess-1", memory={"k": "v"})
        assert isinstance(sess, AgentSession)
        assert sess.session_id == "sess-1"
        assert sess.memory["k"] == "v"

    def test_agent_memory_get_set(self):
        engine = AgentEngine(auto_register_builtin=False)
        engine.agent_session("sess-2")
        engine.agent_memory("sess-2", "k1", "v1")
        assert engine.agent_memory("sess-2", "k1") == "v1"
        mem = engine.agent_memory("sess-2")
        assert mem["k1"] == "v1"

    def test_invoke_persists_under_session(self):
        engine = AgentEngine(auto_register_builtin=False)
        record = engine.invoke_agent("scoring", {"x": 1}, session_id="sess-3")
        sess = engine.get_session("sess-3")
        assert sess is not None
        assert record.invocation_id in sess.invocations

    def test_status_envelope(self):
        engine = AgentEngine(auto_register_builtin=False)
        s = engine.status()
        assert set(s.keys()) == {"state", "registered_agents", "invocations", "sessions"}