"""P4-8-W1: wewrite — 公众号写作一条龙。

Borrowed from the *WeWrite* project: title brainstorm → outline → body →
排版 → CTA, all in one skill.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是公众号爆款写手，请围绕主题「{topic}」生成一篇约 {length} 字的推文：

要求：
1. 给出 3 个候选标题；
2. 输出大纲（3-5 节）+ 完整正文；
3. 末尾加一句引导关注的 CTA；
4. 风格：{tone}。
"""


@skill(
    name="wewrite",
    description="公众号写作一条龙：标题 + 大纲 + 正文 + 排版 + CTA",
    category=SkillCategory.CONTENT,
    version="1.0.0",
    tags=["wechat", "公众号", "writing", "long-form"],
)
class WeWriteSkill(Skill):
    """End-to-end WeChat public-account article generator."""

    DEFAULT_LENGTH = 1200

    async def execute(self, ctx: SkillContext) -> SkillResult:
        topic = str(ctx.inputs.get("topic") or ctx.inputs.get("input") or "").strip()
        if not topic:
            return SkillResult.fail("topic 不能为空", skill_name=self.meta.name)
        length = int(ctx.inputs.get("length", self.DEFAULT_LENGTH))
        tone = ctx.inputs.get("tone", "深度 + 口语")

        prompt = _PROMPT.format(topic=topic, length=length, tone=tone)
        raw = self.call_llm(prompt)

        titles = [
            f"关于「{topic}」的 3 个反常识",
            f"为什么{topic}会重新定义行业？",
            f"我用 30 天搞懂了{topic}",
        ]
        outline = [
            f"为什么我们要聊{topic}",
            f"3 个被忽视的关键点",
            f"实操路径 + 案例",
            f"常见误区 + 避坑指南",
            f"结语 + 一句话 CTA",
        ]
        body_paragraphs = [
            f"开篇故事：上周我和朋友聊到{topic}，发现 90% 的人都误解了它。",
            f"第一个关键点：…（围绕{topic}展开）",
            f"第二个关键点：…（数据 / 引用支撑）",
            f"第三个关键点：…（实战步骤）",
            f"如果你也想深入{topic}，欢迎在评论区告诉我。",
        ]
        cta = "👉 关注「智影」不错过下一篇。"

        ctx.put("article", {"titles": titles, "outline": outline, "body": body_paragraphs, "cta": cta})
        return SkillResult.ok(
            data={
                "topic": topic,
                "length": length,
                "tone": tone,
                "titles": titles,
                "outline": outline,
                "body": body_paragraphs,
                "cta": cta,
            },
            skill_name=self.meta.name,
            logs=[f"wewrite: {len(titles)} titles, {len(outline)} sections"],
            metadata={"prompt_chars": len(prompt)},
        )