"""P4-6-W2: 3-module Director studio tests (4+ tests).

Covers:
  1. full pipeline: "1 minute make-up tutorial" → 8 shots → assets → final cut
  2. user override: edit storyboard between story and visual
  3. error: visual cannot run before story succeeds
  4. singleton + LLM info
"""
from __future__ import annotations

import pytest

from services.workflow_service.director import (
    DirectorState,
    DirectorStudio,
    Shot,
    get_director_studio,
)


# =====================================================================
# 1) full pipeline — 1 minute beauty tutorial → 8 shots
# =====================================================================

@pytest.mark.asyncio
async def test_full_pipeline_one_minute_beauty_tutorial():
    studio = DirectorStudio()
    sess = await studio.run_full("1 分钟美妆教程", shot_count=8)
    assert sess.story_state == DirectorState.SUCCEEDED
    assert sess.visual_state == DirectorState.SUCCEEDED
    assert sess.assembly_state == DirectorState.SUCCEEDED
    assert len(sess.shots) == 8
    # 3 assets per shot
    assert len(sess.assets) == 24
    # final cut
    assert sess.final_cut_uri.startswith("local://director/final-")


@pytest.mark.asyncio
async def test_full_pipeline_generic_brief():
    studio = DirectorStudio()
    sess = await studio.run_full("a 30 second product demo video")
    assert sess.state == DirectorState.SUCCEEDED
    assert len(sess.shots) >= 3
    assert sess.final_cut_uri


# =====================================================================
# 2) user override between story and visual
# =====================================================================

@pytest.mark.asyncio
async def test_user_override_shots_before_visual():
    studio = DirectorStudio()
    sess = studio.create_session("60 second tutorial")
    await studio.run_story(sess.session_id)
    assert len(sess.shots) >= 1
    # user replaces with custom 3-shot list
    custom = [
        Shot(shot_id="custom-1", index=0, title="Hook",
             description="Strong opener", duration_seconds=5.0,
             visual_prompt="bold visual", voiceover="Watch this"),
        Shot(shot_id="custom-2", index=1, title="Body",
             description="Main content", duration_seconds=20.0,
             visual_prompt="step by step", voiceover="Here is how"),
        Shot(shot_id="custom-3", index=2, title="CTA",
             description="Call to action", duration_seconds=5.0,
             visual_prompt="logo animation", voiceover="Try it now"),
    ]
    ok = studio.update_shots(sess.session_id, custom)
    assert ok is True
    # visual should now use the overridden list
    await studio.run_visual(sess.session_id)
    assert sess.visual_state == DirectorState.SUCCEEDED
    # assets are 3 per shot = 9
    assert len(sess.assets) == 9
    # ids are the custom ones
    asset_shot_ids = {a.shot_id for a in sess.assets}
    assert asset_shot_ids == {"custom-1", "custom-2", "custom-3"}


# =====================================================================
# 3) sequencing guard — visual cannot run before story
# =====================================================================

@pytest.mark.asyncio
async def test_visual_requires_story_succeeded():
    studio = DirectorStudio()
    sess = studio.create_session("anything")
    # story never ran
    with pytest.raises(RuntimeError, match="visual director requires story"):
        await studio.run_visual(sess.session_id)


@pytest.mark.asyncio
async def test_assembly_requires_visual_succeeded():
    studio = DirectorStudio()
    sess = studio.create_session("anything")
    await studio.run_story(sess.session_id)
    with pytest.raises(RuntimeError, match="assembly requires visual"):
        await studio.run_assembly(sess.session_id)


# =====================================================================
# 4) singleton + LLM info
# =====================================================================

def test_singleton():
    s1 = get_director_studio()
    s2 = get_director_studio()
    assert s1 is s2


def test_llm_is_deterministic():
    studio = DirectorStudio()
    assert studio.llm.model == "stub-deterministic"
    # Same brief → same shot count
    import asyncio
    n1 = len(asyncio.get_event_loop().run_until_complete(
        studio.story.run("1 分钟美妆教程")))
    n2 = len(asyncio.get_event_loop().run_until_complete(
        studio.story.run("1 分钟美妆教程")))
    assert n1 == n2 == 8
