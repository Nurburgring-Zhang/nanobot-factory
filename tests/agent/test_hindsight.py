"""P4-3-W2: Hindsight 4-layer Memory Stack tests.

5 tests:

  1. test_hindsight_retain_and_recall
  2. test_hindsight_layer_0_identity
  3. test_hindsight_layer_2_wing_trigger
  4. test_hindsight_layer_3_full_search
  5. test_hindsight_l1_auto_compress

Run with::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_hindsight.py -v
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("IMDF_DATA_DIR", str(_BACKEND / "imdf" / "data"))
os.environ.setdefault("JWT_SECRET", "test-secret-DO-NOT-USE-IN-PROD-abcdef123456")
os.environ.setdefault("IMDF_TEST_MODE", "1")


def _fresh(tmp_path=None):
    """Reset the Hindsight singleton to a fresh instance."""
    import tempfile

    from services.agent_service.hindsight import (
        HindsightConfig,
        reset_hindsight_for_test,
    )

    if tmp_path is None:
        tmp_path = tempfile.mkdtemp(prefix="hindsight_")
    return reset_hindsight_for_test(
        config=HindsightConfig(db_path=str(tmp_path / "hindsight.db"))
    )


# ── 1. retain + recall ──────────────────────────────────────────────────────
def test_hindsight_retain_and_recall(tmp_path):
    hs = _fresh(tmp_path)
    item = hs.retain("User said hello", role="user", source="session:abc")
    assert item.layer == "L3_full"
    assert item.item_id.startswith("mem-")
    recalled = hs.recall(item.item_id)
    assert recalled is not None
    assert recalled.content == "User said hello"


# ── 2. L0 identity ──────────────────────────────────────────────────────────
def test_hindsight_layer_0_identity(tmp_path):
    hs = _fresh(tmp_path)
    a = hs.retain_identity("SOUL: 智影")
    b = hs.retain_identity("user_name: alice")
    items = hs.list_identity()
    assert {i.item_id for i in items} == {a.item_id, b.item_id}
    # Verbatim property: stored text == input text
    assert any(i.content == "SOUL: 智影" for i in items)


# ── 3. L2 wing trigger ─────────────────────────────────────────────────────
def test_hindsight_layer_2_wing_trigger(tmp_path):
    hs = _fresh(tmp_path)
    hs.register_wing("prompt-engineering", ["prompt", "system prompt"])
    hs.register_wing("data-quality", ["nsfw", "blur", "aesthetic"])
    # Text containing a trigger keyword
    triggered = hs.trigger_wings("Help me design a new system prompt for the agent.")
    names = {t["name"] for t in triggered}
    assert "prompt-engineering" in names
    assert "data-quality" not in names


# ── 4. L3 full-text search ─────────────────────────────────────────────────
def test_hindsight_layer_3_full_search(tmp_path):
    hs = _fresh(tmp_path)
    hs.retain("The agent should call hindsight.search before responding.", role="agent", source="s1")
    hs.retain("User profile: alice is a data engineer.", role="user", source="s1")
    hs.retain("Loader error: missing module 'hindsight'", role="tool", source="s2")
    results = hs.search("hindsight", k=10)
    assert len(results) >= 1
    # At least one match should be L3_full
    layers = {r["match_layer"] for r in results}
    assert "L3_full" in layers
    # The actual content should appear somewhere in the matched items
    parts = []
    for r in results:
        item = r.get("item")
        if item is not None:
            # MemoryItem dataclass — support either object or dict for safety
            if isinstance(item, dict):
                parts.append(item.get("content", ""))
            else:
                parts.append(getattr(item, "content", ""))
    all_text = " ".join(parts)
    assert "hindsight" in all_text


# ── 5. L1 auto-compress (deterministic stub LLM) ───────────────────────────
def test_hindsight_l1_auto_compress(tmp_path):
    from services.agent_service.hindsight import HindsightConfig, reset_hindsight_for_test

    def stub_llm(prompt: str) -> str:
        return f"COMPRESSED: {prompt[:60]}..."

    cfg = HindsightConfig(
        db_path=str(tmp_path / "hindsight_l1.db"),
        llm=stub_llm,
        l1_compress_threshold=3,  # compress every 3 items
    )
    hs = reset_hindsight_for_test(config=cfg)
    # Write 3 items under same source to trigger compress at item 3
    for i in range(3):
        hs.retain(f"user message {i}", role="user", source="session:comp")
    stories = hs.list_l1_stories()
    assert len(stories) >= 1
    assert stories[0]["summary"].startswith("COMPRESSED:")


__all__ = [
    "test_hindsight_retain_and_recall",
    "test_hindsight_layer_0_identity",
    "test_hindsight_layer_2_wing_trigger",
    "test_hindsight_layer_3_full_search",
    "test_hindsight_l1_auto_compress",
]
