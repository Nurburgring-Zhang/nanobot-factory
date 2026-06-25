"""Tests for youtube_clipper skill (P4-8-W1)."""
import pytest

from skills.builtin.youtube_clipper import YoutubeClipperSkill


@pytest.mark.asyncio
async def test_youtube_clipper_empty_transcript_fails(make_ctx):
    skill = YoutubeClipperSkill()
    ctx = make_ctx(inputs={"transcript": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "transcript" in result.error.lower()


@pytest.mark.asyncio
async def test_youtube_clipper_default_clips(make_ctx):
    skill = YoutubeClipperSkill()
    ctx = make_ctx(inputs={
        "transcript": "[00:00] 开场白。[02:30] 第一个观点。[05:00] 第二个观点。"
                      "[07:30] 第三个观点。[10:00] 结尾。"
    })
    result = await skill.execute(ctx)
    assert result.success is True
    assert len(result.data["clips"]) == skill.DEFAULT_CLIPS


@pytest.mark.asyncio
async def test_youtube_clipper_custom_clip_count(make_ctx):
    skill = YoutubeClipperSkill()
    transcript = " ".join([f"[{i*2:02d}:00] 段落 {i}。" for i in range(10)])
    ctx = make_ctx(inputs={"transcript": transcript, "clips": 3})
    result = await skill.execute(ctx)
    assert result.success is True
    assert len(result.data["clips"]) == 3


@pytest.mark.asyncio
async def test_youtube_clipper_no_timecodes_uses_synth(make_ctx):
    skill = YoutubeClipperSkill()
    ctx = make_ctx(inputs={"transcript": "没有时间码的纯文本内容。" * 20, "clips": 4})
    result = await skill.execute(ctx)
    assert result.success is True
    assert len(result.data["clips"]) == 4
    # All clips have required fields
    for c in result.data["clips"]:
        assert "start" in c and "end" in c
        assert "title" in c
        assert "hook" in c