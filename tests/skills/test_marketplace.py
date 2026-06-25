"""P4-8-W1: marketplace tests — publish, install, rate."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

import skills.builtin  # noqa: F401, E402  -- ensure registry populated
from skills.marketplace import (  # noqa: E402
    SkillEntry,
    SkillMarketplace,
    new_community_skill,
    reset_marketplace_for_test,
)


@pytest.fixture
def tmp_mp(tmp_path):
    reset_marketplace_for_test()
    mp = SkillMarketplace(persist_path=str(tmp_path / "mp.json"))
    yield mp
    reset_marketplace_for_test()


def test_sync_from_registry_publishes_all_builtins(tmp_mp):
    added = tmp_mp.sync_from_registry()
    assert added >= 10
    items = tmp_mp.list()
    assert any(it["name"] == "guizang_ppt" for it in items)
    assert items[0]["builtin"] is True


def test_install_and_rate(tmp_mp):
    tmp_mp.sync_from_registry()
    res = tmp_mp.install("guizang_ppt")
    assert res["success"] is True
    assert res["downloads"] >= 1

    rate1 = tmp_mp.rate("guizang_ppt", user_id="alice", stars=5, review="好用")
    assert rate1["success"] is True
    assert rate1["new_rating_avg"] == 5.0

    rate2 = tmp_mp.rate("guizang_ppt", user_id="bob", stars=3, review="不错")
    assert rate2["success"] is True
    assert rate2["new_rating_avg"] == 4.0  # (5+3)/2

    bad = tmp_mp.rate("guizang_ppt", user_id="x", stars=10)
    assert bad["success"] is False

    reviews = tmp_mp.reviews("guizang_ppt")
    assert len(reviews) == 2


def test_publish_community_skill(tmp_mp):
    entry = new_community_skill(
        name="my_cool_skill",
        description="A community-built skill.",
        category="content",
        tags=["community", "demo"],
    )
    tmp_mp.publish(entry)
    items = tmp_mp.list(query="cool")
    assert any(it["id"] == "my_cool_skill" for it in items)


def test_persist_roundtrip(tmp_path):
    path = str(tmp_path / "persist.json")
    mp1 = SkillMarketplace(persist_path=path)
    mp1.publish(new_community_skill("alpha", "first", "content"))
    mp1.install("alpha")
    mp1.rate("alpha", "u1", 4, "good")
    del mp1

    mp2 = SkillMarketplace(persist_path=path)
    items = mp2.list()
    assert any(it["id"] == "alpha" for it in items)
    entry = mp2.get("alpha")
    assert entry.downloads == 1
    assert entry.rating_count == 1
    assert entry.rating_avg == 4.0