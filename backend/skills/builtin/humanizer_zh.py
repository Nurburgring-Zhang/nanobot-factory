"""P4-8-W1: humanizer_zh — AI 腔 → 人话 (中文 humanizer).

Borrowed from the *humanizer-zh* project.  Strips the AI tell-tales:
过度排比、连接词堆砌、空泛总结、模板化开头/结尾。
"""
from __future__ import annotations

import re
from typing import Any, Dict

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是中文写作「人味儿」编辑，请把下面这段 AI 腔文字改写成自然口语化的中文。

要求：
1. 去掉「综上所述 / 总而言之 / 在当今时代 / 值得注意的是」等模板化表达；
2. 把长排比拆成短句，允许偶尔用「其实 / 不过 / 反正 / 你想」等口语词；
3. 保留信息量，不杜撰内容；
4. 输出只给改写后的正文，不要附加解释。

原文：
{text}
"""


_AI_TELLS = [
    "综上所述",
    "总而言之",
    "在当今时代",
    "值得注意的是",
    "首先，其次，最后",
    "作为一款",
    "赋能",
    "打造",
    "全方位",
]


@skill(
    name="humanizer_zh",
    description="把 AI 腔中文改写成自然口语化文本",
    category=SkillCategory.CONTENT,
    version="1.0.0",
    tags=["humanizer", "writing", "chinese", "tone"],
)
class HumanizerZhSkill(Skill):
    """AI-voice → human-voice (zh)."""

    async def execute(self, ctx: SkillContext) -> SkillResult:
        text = str(ctx.inputs.get("text") or ctx.inputs.get("input") or "").strip()
        if not text:
            return SkillResult.fail("text 不能为空", skill_name=self.meta.name)

        prompt = _PROMPT.format(text=text)
        raw = self.call_llm(prompt)
        rewritten = _humanize(text, raw)

        # Heuristic score: how many AI tells remain?
        score_before = sum(text.count(t) for t in _AI_TELLS)
        score_after = sum(rewritten.count(t) for t in _AI_TELLS)
        human_score = max(0, min(100, 100 - 15 * (score_after - score_before) - 5))

        ctx.put("humanized", rewritten)
        return SkillResult.ok(
            data={
                "original": text,
                "humanized": rewritten,
                "human_score": human_score,
                "ai_tells_before": score_before,
                "ai_tells_after": score_after,
            },
            skill_name=self.meta.name,
            logs=[f"human_score={human_score}, ai_tells {score_before}→{score_after}"],
            metadata={"prompt_chars": len(prompt)},
        )


def _humanize(original: str, llm_output: str) -> str:
    """Use the LLM output if it looks substantive, otherwise do a cheap rewrite."""
    if llm_output and len(llm_output) >= max(20, len(original) // 4) and not llm_output.startswith("[mock"):
        return llm_output.strip()
    # Cheap deterministic rewrite as a guaranteed fallback.
    out = original
    out = out.replace("综上所述，", "")
    out = out.replace("总而言之，", "")
    out = out.replace("在当今时代，", "")
    out = out.replace("值得注意的是，", "")
    out = re.sub(r"首先[，,、]\s*", "", out)
    out = re.sub(r"其次[，,、]\s*", "", out)
    out = re.sub(r"最后[，,、]\s*", "", out)
    return out.strip()