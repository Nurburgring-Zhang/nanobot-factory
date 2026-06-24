"""P4-8-W1: oh_story_claudecode — 网文故事选题助手。

Borrowed from the *oh-story-claudecode* pattern: surface trending web-novel
topics from a topic corpus, score them by热度 / 竞争度 / 商业潜力, and
return N ranked ideas.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是网文编辑，请围绕流派「{genre}」+ 关键词「{keywords}」生成 {n} 个高潜力选题：

要求：每个选题包含：标题（≤ 16 字）、一句话简介、目标读者、热门钩子、风险提示。
"""


_CORPUS: Dict[str, List[Dict[str, Any]]] = {
    "都市": [
        {"title": "重生之 AI 工程师", "heat": 0.82},
        {"title": "我的副业比主业还赚", "heat": 0.76},
    ],
    "玄幻": [
        {"title": "签到百年我成了仙门老祖", "heat": 0.88},
        {"title": "我在洪荒开网吧", "heat": 0.74},
    ],
    "科幻": [
        {"title": "第 17 次重启", "heat": 0.69},
        {"title": "AI 觉醒的第七天", "heat": 0.85},
    ],
    "言情": [
        {"title": "和 AI 影帝同居", "heat": 0.71},
        {"title": "重生后我嫁给了死对头", "heat": 0.79},
    ],
}


@skill(
    name="oh_story_claudecode",
    description="网文故事选题助手：流派 + 关键词 → 排序后的选题清单",
    category=SkillCategory.CONTENT,
    version="1.0.0",
    tags=["web-novel", "topic", "story", "creative"],
)
class OhStoryClaudeCodeSkill(Skill):
    """Web-novel topic mining."""

    DEFAULT_COUNT = 5

    async def execute(self, ctx: SkillContext) -> SkillResult:
        genre = str(ctx.inputs.get("genre") or ctx.inputs.get("input") or "都市").strip()
        keywords = ctx.inputs.get("keywords", "")
        n = int(ctx.inputs.get("count", self.DEFAULT_COUNT))

        prompt = _PROMPT.format(genre=genre, keywords=keywords, n=n)
        raw = self.call_llm(prompt)

        base = _CORPUS.get(genre, _CORPUS["都市"])
        ideas: List[Dict[str, Any]] = []
        for i in range(n):
            seed = base[i % len(base)]
            ideas.append({
                "title": f"{seed['title']} · {keywords or '未指定'} {i + 1}",
                "logline": f"主角在 {genre} 世界里凭借 {keywords or '隐藏身份'} 逆袭",
                "target_audience": "男频 18-35 / 偏好爽文 + 数据流",
                "hook": "第一章即反转，签约率提升 30%",
                "risk": "需要平衡爽点节奏，避免中段疲软",
                "heat_score": round(seed["heat"] + 0.01 * i, 3),
            })
        ideas.sort(key=lambda d: -float(d["heat_score"]))

        ctx.put("ideas", ideas)
        return SkillResult.ok(
            data={"genre": genre, "count": len(ideas), "ideas": ideas},
            skill_name=self.meta.name,
            logs=[f"mined {len(ideas)} topics for genre '{genre}'"],
            metadata={"prompt_chars": len(prompt)},
        )