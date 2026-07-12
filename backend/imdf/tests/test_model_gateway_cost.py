"""P10-B: Tests for model_gateway.py cost / usage_tracker / audit_chain integration.

Verifies:
1. ``compute_cost_usd(model, tokens, provider)`` returns correct USD for 5 providers
   (deepseek / openai / anthropic / google / zhipu) and various token shapes
   (OpenAI prompt/completion, Anthropic input/output, Google promptTokenCount).
2. ``ModelGateway.chat_with_observability`` records usage via UsageTracker
   (fallback jsonl when DB unavailable) and audit via AuditChain.
3. Cost + usage appear in ChatResponse._extras after call.
4. Provider inference from model id works.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from engines.model_gateway import (
    ChatResponse,
    ModelGateway,
    ModelInfo,
    ModelProvider,
    _DEFAULT_MODEL_COST_TABLE,
    _infer_provider,
    _record_call_observability,
    _usage_dict_compat,
    compute_cost_usd,
    get_gateway,
)


# ── 1. compute_cost_usd — pure function ──────────────────────────────────
def test_compute_cost_usd_deepseek_chat():
    # deepseek-chat: input=0.00014, output=0.00028 per 1k
    cost = compute_cost_usd(
        model="deepseek-chat",
        tokens={"prompt_tokens": 1000, "completion_tokens": 500},
        provider="deepseek",
    )
    expected = (1000 / 1000.0) * 0.00014 + (500 / 1000.0) * 0.00028
    assert abs(cost - expected) < 1e-6, f"expected={expected}, got={cost}"


def test_compute_cost_usd_openai_gpt4o():
    # gpt-4o: input=0.005, output=0.015 per 1k
    cost = compute_cost_usd(
        model="gpt-4o",
        tokens={"prompt_tokens": 2000, "completion_tokens": 1000},
        provider="openai",
    )
    expected = 2 * 0.005 + 1 * 0.015
    assert abs(cost - expected) < 1e-6


def test_compute_cost_usd_anthropic_input_output_alias():
    # Anthropic usage uses input_tokens/output_tokens
    cost = compute_cost_usd(
        model="claude-sonnet-4-20250514",
        tokens={"input_tokens": 1500, "output_tokens": 500},
        provider="anthropic",
    )
    # sonnet-4: input=0.003, output=0.015 per 1k
    expected = 1.5 * 0.003 + 0.5 * 0.015
    assert abs(cost - expected) < 1e-6


def test_compute_cost_usd_google_prompt_token_count():
    # Google uses promptTokenCount / candidatesTokenCount / totalTokenCount
    cost = compute_cost_usd(
        model="gemini-2.5-flash",
        tokens={"promptTokenCount": 800, "candidatesTokenCount": 400, "totalTokenCount": 1200},
        provider="google",
    )
    # flash: 0.000075 / 0.0003 per 1k
    expected = 0.8 * 0.000075 + 0.4 * 0.0003
    assert abs(cost - expected) < 1e-6


def test_compute_cost_usd_zero_tokens_returns_zero():
    assert compute_cost_usd("gpt-4o", {"prompt_tokens": 0, "completion_tokens": 0}) == 0.0
    assert compute_cost_usd("gpt-4o", {}) == 0.0


def test_compute_cost_usd_inferred_provider():
    # no provider passed — should infer from model
    cost = compute_cost_usd("deepseek-chat", {"prompt_tokens": 1000, "completion_tokens": 200})
    assert cost > 0
    cost_openai = compute_cost_usd("gpt-4o-mini", {"prompt_tokens": 1000, "completion_tokens": 200})
    assert cost_openai > cost  # openai is more expensive


def test_compute_cost_usd_unknown_model_falls_back_to_provider_default():
    cost = compute_cost_usd("unknown-model-xyz", {"prompt_tokens": 1000, "completion_tokens": 200}, provider="openai")
    # openai *: 0.005, 0.015
    expected = 0.005 + 0.2 * 0.015
    assert abs(cost - expected) < 1e-6


# ── 2. _infer_provider ───────────────────────────────────────────────────
def test_infer_provider_all_branches():
    assert _infer_provider("deepseek-chat") == "deepseek"
    assert _infer_provider("deepseek-v4-pro") == "deepseek"
    assert _infer_provider("gpt-4o") == "openai"
    assert _infer_provider("o1-mini") == "openai"
    assert _infer_provider("claude-3-5-sonnet") == "anthropic"
    assert _infer_provider("gemini-2.5-pro") == "google"
    assert _infer_provider("glm-4-plus") == "zhipu"
    assert _infer_provider("unknown-model") == "deepseek"  # default


# ── 3. _usage_dict_compat ────────────────────────────────────────────────
def test_usage_dict_compat_openai():
    u = _usage_dict_compat(ChatResponse(success=True, usage={
        "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150
    }))
    assert u == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}


def test_usage_dict_compat_anthropic():
    u = _usage_dict_compat(ChatResponse(success=True, usage={
        "input_tokens": 200, "output_tokens": 80
    }))
    assert u["prompt_tokens"] == 200
    assert u["completion_tokens"] == 80
    assert u["total_tokens"] == 280  # auto-sum


def test_usage_dict_compat_google():
    u = _usage_dict_compat(ChatResponse(success=True, usage={
        "promptTokenCount": 300, "candidatesTokenCount": 100, "totalTokenCount": 400
    }))
    assert u["prompt_tokens"] == 300
    assert u["completion_tokens"] == 100
    assert u["total_tokens"] == 400


def test_usage_dict_compat_empty():
    u = _usage_dict_compat(ChatResponse(success=True))
    assert u == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# ── 4. _record_call_observability (integration with fallback tracker + audit) ──
@pytest.fixture
def tmp_dirs(monkeypatch, tmp_path):
    """Redirect UsageTracker fallback log + AuditChain DB to tmp.

    Forces usage_tracker.record() to take the fallback jsonl path by patching
    db.SessionLocal to raise (so the test doesn't depend on real DB state).
    """
    fallback_log = tmp_path / "usage_fallback.jsonl"
    audit_db = tmp_path / "audit_chain.db"
    monkeypatch.setenv("AUDIT_CHAIN_SECRET", "test-secret-for-p10b-1234567890")
    monkeypatch.setenv("USAGE_FALLBACK_LOG", str(fallback_log))

    from engines import usage_tracker as ut
    from engines import audit_chain as ac

    # Force fallback path: make db import raise
    import sys as _sys
    real_db = _sys.modules.get("db")
    real_models = _sys.modules.get("models")

    class _BoomSessionLocal:
        def __call__(self, *a, **kw):
            raise RuntimeError("test: force fallback path")
        def __enter__(self): raise RuntimeError("force fallback")
        def __exit__(self, *a): return False

    class _BoomModule:
        SessionLocal = _BoomSessionLocal()
    _sys.modules["db"] = _BoomModule()
    if "models" in _sys.modules:
        del _sys.modules["models"]
    _sys.modules["models"] = _BoomModule()

    # Patch _FALLBACK_LOG so record() writes to tmp
    monkeypatch.setattr(ut, "_FALLBACK_LOG", fallback_log)
    # Reset usage_tracker singleton so it picks up new fallback path
    ut.UsageTracker._instance = None

    # Reset audit chain
    ac.reset_singleton_for_tests(audit_db, "test-secret-for-p10b-1234567890")

    yield {"fallback_log": fallback_log, "audit_db": audit_db}

    # Restore real db module if present
    if real_db is not None:
        _sys.modules["db"] = real_db
    if real_models is not None:
        _sys.modules["models"] = real_models


def test_record_call_observability_writes_usage_and_audit(tmp_dirs):
    """End-to-end: usage_tracker.record (fallback) + audit_chain.append both fire."""
    _record_call_observability(
        tenant_id="tenant-abc",
        model="deepseek-chat",
        provider="deepseek",
        usage={"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        cost_usd=0.000126,
        latency_ms=123.4,
        success=True,
    )
    # 1. usage_tracker should have written a fallback row
    log_path = tmp_dirs["fallback_log"]
    assert log_path.exists(), f"fallback log not written to {log_path}"
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1, f"expected 1 row, got {len(lines)}"
    row = lines[0]
    assert row["user_id"] == "tenant-abc"
    assert row["provider_id"] == "deepseek"
    assert row["model"] == "deepseek-chat"
    assert row["prompt_tokens"] == 500
    assert row["completion_tokens"] == 200
    assert row["total_tokens"] == 700
    assert abs(row["cost_usd"] - 0.000126) < 1e-6
    assert row["status"] == "ok"

    # 2. audit_chain should have appended an entry
    from engines.audit_chain import get_chain
    chain = get_chain()
    entries = chain.load_all()
    assert len(entries) >= 1
    last = entries[-1]
    assert last.method == "MODEL_CALL"
    assert "deepseek-chat" in last.path
    # audit chain appends actor to user — just check prefix
    assert last.user.startswith("tenant-abc"), f"unexpected user field: {last.user}"
    assert last.status_code == 200
    # verify chain integrity
    ok, bad_seq = chain.verify_chain()
    assert ok, f"audit chain integrity broken at seq={bad_seq}"


def test_record_call_observability_failure_status(tmp_dirs):
    _record_call_observability(
        tenant_id="tenant-xyz",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 100, "completion_tokens": 50},
        cost_usd=0.0,
        latency_ms=50.0,
        success=False,
        error="HTTP 429 rate limit",
    )
    log_path = tmp_dirs["fallback_log"]
    assert log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    row = lines[0]
    assert row["status"] == "error"
    assert row["error_code"] == "model_call_failed"
    assert "429" in row["error_message"]


# ── 5. ModelGateway.chat_with_observability with mocked provider ────────
class _MockProvider(ModelProvider):
    provider_name = "mock-deepseek"

    DEFAULT_MODELS = [
        ModelInfo(id="mock-deepseek-chat", provider="mock-deepseek",
                  display_name="Mock DS Chat", max_tokens=8192, default=True),
    ]

    def __init__(self, *, ok: bool = True, usage: dict | None = None):
        self._ok = ok
        self._usage = usage or {
            "prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300,
        }

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096):
        if not self._ok:
            return ChatResponse(
                success=False, error="mock failure", provider="mock-deepseek", model=model
            )
        return ChatResponse(
            success=True,
            content="mock reply",
            model=model,
            provider="mock-deepseek",
            usage=self._usage,
        )

    def get_models(self):
        return self.DEFAULT_MODELS

    async def health_check(self, model):
        return {"status": "ok" if self._ok else "error", "latency_ms": 10.0}


@pytest.mark.asyncio
async def test_chat_with_observability_records_cost_and_audit(tmp_dirs):
    """Real flow: mock provider → chat_with_observability → tracker + audit filled."""
    gateway = ModelGateway.__new__(ModelGateway)  # bypass __init__
    gateway._providers = {"mock-deepseek": type("E", (), {
        "provider": _MockProvider(ok=True),
        "breaker": MagicMock(allow_request=MagicMock(return_value=True)),
    })()}
    # rebuild _models from this
    gateway._models = [
        ModelInfo(id="mock-deepseek-chat", provider="mock-deepseek", default=True, priority=0)
    ]
    gateway._default_model = "mock-deepseek-chat"

    resp = await gateway.chat_with_observability(
        messages=[{"role": "user", "content": "hello"}],
        model="mock-deepseek-chat",
        tenant_id="tenant-foo",
    )
    assert resp.success is True
    assert resp._extras is not None
    cost = resp._extras.get("cost_usd", 0.0)
    assert cost > 0
    usage = resp._extras.get("usage", {})
    assert usage.get("prompt_tokens") == 100
    assert usage.get("completion_tokens") == 200

    # verify fallback jsonl was written
    log_path = tmp_dirs["fallback_log"]
    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["user_id"] == "tenant-foo"
    assert rows[0]["model"] == "mock-deepseek-chat"

    # verify audit chain
    from engines.audit_chain import get_chain
    chain = get_chain()
    ok, _ = chain.verify_chain()
    assert ok


@pytest.mark.asyncio
async def test_chat_with_observability_failure_records_error(tmp_dirs):
    gateway = ModelGateway.__new__(ModelGateway)
    gateway._providers = {"mock-deepseek": type("E", (), {
        "provider": _MockProvider(ok=False),
        "breaker": MagicMock(allow_request=MagicMock(return_value=True)),
    })()}
    gateway._models = [
        ModelInfo(id="mock-deepseek-chat", provider="mock-deepseek", default=True, priority=0)
    ]
    gateway._default_model = "mock-deepseek-chat"

    resp = await gateway.chat_with_observability(
        messages=[{"role": "user", "content": "hello"}],
        model="mock-deepseek-chat",
        tenant_id="tenant-err",
    )
    assert resp.success is False
    assert resp._extras is not None
    # usage record should still exist with status=error
    log_path = tmp_dirs["fallback_log"]
    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert "mock failure" in rows[0]["error_message"]
