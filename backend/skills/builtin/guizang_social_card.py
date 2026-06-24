"""P4-8-W1: guizang_social_card — text → social card deck.

Borrowed from the open-source *guizang-social-card* project.  Produces a
list of social cards (WeChat / Xiaohongshu / Twitter), each with a hook
line + supporting bullet + suggested visual cue.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是中文社媒内容专家，请把以下长文改写成 {count} 张社交媒体卡片（{platform}）。

要求：
- 每张卡片包含 hook（钩子句 ≤ 24 字）、body（2-3 行要点）、cta（行动号召）；
- 第 1 张卡片用问题/数字开头；最后 1 张是总结 + 转发号召；
- 风格口语化，避免 AI 腔。

原文：
{text}
"""


@skill(
    name="guizang_social_card",
    description="把长文改写成社媒卡片（公众号 / 小红书 / Twitter）",
    category=SkillCategory.CONTENT,
    version="1.0.0",
    tags=["social", "card", "wechat", "twitter", "xiaohongshu"],
)
class GuizangSocialCardSkill(Skill):
    """text → social cards (multi-platform)."""

    DEFAULT_COUNT = 5

    async def execute(self, ctx: SkillContext) -> SkillResult:
        text = str(ctx.inputs.get("text") or ctx.inputs.get("input") or "").strip()
        if not text:
            return SkillResult.fail("text 不能为空", skill_name=self.meta.name)
        platform = ctx.inputs.get("platform", "微信公众号")
        count = int(ctx.inputs.get("count", self.DEFAULT_COUNT))

        prompt = _PROMPT.format(text=text, count=count, platform=platform)
        raw = self.call_llm(prompt)
        cards = _parse_cards(raw, count=count, topic=text[:24])

        ctx.put("cards", cards)
        return SkillResult.ok(
            data={"platform": platform, "count": count, "cards": cards},
            skill_name=self.meta.name,
            logs=[f"produced {len(cards)} cards for {platform}"],
            metadata={"prompt_chars": len(prompt)},
        )


def _parse_cards(raw: str, *, count: int, topic: str) -> List[Dict[str, Any]]:
    # Simple deterministic mock: synthesise N cards from the source text.
    return [
        {
            "page": i + 1,
            "hook": f"{topic}… 第 {i + 1} 步关键点",
            "body": [
                f"观点 A — 来自原文 {i + 1}",
                f"观点 B — 数据 / 引用支撑",
            ],
            "cta": ("📌 收藏 / 转发" if i == count - 1 else "👉 继续看下一页"),
        }
        for i in range(count)
    ]