"""P4-8-W1: guizang_ppt — idea → PPT outline + slide deck.

Borrowed from the open-source *guizangPPTX* pattern: take a topic (and
optional outline), and produce a structured slide deck as JSON ready for
export to .pptx via python-pptx.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是资深 PPT 设计师，请根据用户的想法生成结构化的演示稿大纲。
要求：
1. 每个 slide 必须包含 title + 3 个要点 + 演讲备注（speaker_notes）；
2. 共 {slide_count} 页，第一页是封面，最后一页是总结；
3. 使用中文输出，JSON 格式。

主题：{topic}
补充：{extra}

输出格式示例（仅参考结构）：
{{"title": "...", "slides": [{{"page": 1, "title": "...", "bullets": ["..."], "speaker_notes": "..."}}]}}
"""


@skill(
    name="guizang_ppt",
    description="把想法变成结构化 PPT 大纲 + 演讲备注",
    category=SkillCategory.CONTENT,
    version="1.0.0",
    tags=["ppt", "presentation", "slides", "deck"],
)
class GuizangPPTSkill(Skill):
    """Idea → structured PPT (JSON ready for python-pptx)."""

    DEFAULT_SLIDES = 8

    async def execute(self, ctx: SkillContext) -> SkillResult:
        topic = str(ctx.inputs.get("topic") or ctx.inputs.get("input") or "").strip()
        if not topic:
            return SkillResult.fail("topic 不能为空", skill_name=self.meta.name)
        slide_count = int(ctx.inputs.get("slides", self.DEFAULT_SLIDES))
        extra = ctx.inputs.get("extra", "")

        prompt = _PROMPT.format(slide_count=slide_count, topic=topic, extra=extra)
        raw = self.call_llm(prompt)
        deck = _parse_deck(raw, topic=topic, slide_count=slide_count)

        ctx.put("ppt_deck", deck)
        ctx.put("topic", topic)
        return SkillResult.ok(
            data={"topic": topic, "slide_count": slide_count, "deck": deck},
            skill_name=self.meta.name,
            logs=[f"generated {len(deck['slides'])} slides for '{topic}'"],
            metadata={"prompt_chars": len(prompt), "model": "mock" if self._llm is None else "live"},
        )


def _parse_deck(raw: str, *, topic: str, slide_count: int) -> Dict[str, Any]:
    """Parse the LLM response into a deck dict, falling back to a template."""
    # 1. Try direct JSON parse.
    text = raw.strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "slides" in obj:
                obj.setdefault("title", topic)
                return obj
        except json.JSONDecodeError:
            pass
    # 2. Try to locate the first JSON block in the response.
    m = re.search(r"\{[\s\S]*\}\s*$", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "slides" in obj:
                obj.setdefault("title", topic)
                return obj
        except json.JSONDecodeError:
            pass
    # 3. Fallback: synthesize a deck template.
    return {
        "title": topic,
        "slides": [
            {
                "page": i + 1,
                "title": ("封面：介绍主题" if i == 0
                          else ("总结与下步" if i == slide_count - 1
                                else f"第 {i + 1} 页：要点")),
                "bullets": [
                    f"要点 1（来自 {topic}）",
                    f"要点 2（解释与例子）",
                    f"要点 3（数据 / 引用）",
                ],
                "speaker_notes": f"围绕「{topic}」的第 {i + 1} 页讲解重点。",
            }
            for i in range(slide_count)
        ],
    }