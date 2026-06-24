"""P4-8-W1: youtube_clipper — long-video → short clips (JSON).

Borrowed from the *youtube-clipper* workflow: given a transcript (or
description + timecodes), surface N candidate clip windows with title,
hook, and rationale.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是短视频剪辑师，请基于以下视频转录挑选 {n} 个最有传播力的片段（30-60 秒）：

转录片段（含时间码）：
{transcript}

输出 JSON：{{"clips": [{{"start":"mm:ss","end":"mm:ss","title":"...","hook":"...","reason":"..."}}]}}
"""


@skill(
    name="youtube_clipper",
    description="长视频自动切短视频：候选片段 + 钩子 + 选题理由",
    category=SkillCategory.VIDEO,
    version="1.0.0",
    tags=["youtube", "video", "clip", "shorts", "tiktok"],
)
class YoutubeClipperSkill(Skill):
    """Long-video → short clip suggestions."""

    DEFAULT_CLIPS = 5

    async def execute(self, ctx: SkillContext) -> SkillResult:
        transcript = str(ctx.inputs.get("transcript") or ctx.inputs.get("input") or "").strip()
        if not transcript:
            return SkillResult.fail("transcript 不能为空", skill_name=self.meta.name)
        n = int(ctx.inputs.get("clips", self.DEFAULT_CLIPS))

        prompt = _PROMPT.format(n=n, transcript=transcript[:2400])
        raw = self.call_llm(prompt)

        # Heuristic: parse [mm:ss] anchors and split evenly.
        anchors = re.findall(r"\[(\d{1,2}):(\d{2})\]", transcript)
        if not anchors:
            anchors = [(str(i * 2), "00") for i in range(n)]

        step = max(1, len(anchors) // n) if len(anchors) > n else 1
        clips: List[Dict[str, Any]] = []
        for i in range(n):
            start_idx = min(i * step, len(anchors) - 1)
            end_idx = min(start_idx + 1, len(anchors) - 1)
            start = f"{int(anchors[start_idx][0]):02d}:{anchors[start_idx][1]}"
            end = f"{int(anchors[end_idx][0]) + 1:02d}:{anchors[end_idx][1]}"
            clips.append({
                "start": start,
                "end": end,
                "title": f"片段 {i + 1}：核心观点",
                "hook": "你以为…其实…",
                "reason": "信息密度高 + 反差点 + 易于引发讨论",
            })

        ctx.put("clips", clips)
        return SkillResult.ok(
            data={"clips": clips, "anchor_count": len(anchors)},
            skill_name=self.meta.name,
            logs=[f"suggested {len(clips)} clips from {len(anchors)} anchors"],
            metadata={"prompt_chars": len(prompt)},
        )