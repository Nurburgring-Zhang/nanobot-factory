"""P4-8-W1: marketingskills — 营销能力工具箱。

Borrowed from the open-source *marketingskills* project: a toolkit with
SEO / landing-page / email subject lines / ad-copy / lead magnet briefs.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是营销专家，请基于产品「{product}」+ 受众「{audience}」生成 {tool} 输出：

约束：{constraints}

输出 JSON，包含 title / body / cta。
"""


_TOOLS = {
    "seo_brief": {"label": "SEO 文章大纲", "fields": ["title", "outline", "keywords"]},
    "landing_page": {"label": "落地页", "fields": ["headline", "subhead", "bullets", "cta"]},
    "email_subject": {"label": "邮件主题", "fields": ["subjects"]},
    "ad_copy": {"label": "广告文案", "fields": ["headlines", "primary_text", "cta"]},
    "lead_magnet": {"label": "Lead Magnet", "fields": ["title", "promise", "outline"]},
}


@skill(
    name="marketingskills",
    description="营销能力工具箱：SEO / 落地页 / 邮件主题 / 广告文案 / Lead Magnet",
    category=SkillCategory.MARKETING,
    version="1.0.0",
    tags=["marketing", "seo", "copy", "ads", "email", "landing"],
)
class MarketingSkills(Skill):
    """Marketing toolkit (multi-tool)."""

    DEFAULT_TOOL = "landing_page"

    async def execute(self, ctx: SkillContext) -> SkillResult:
        tool = str(ctx.inputs.get("tool") or self.DEFAULT_TOOL).strip().lower()
        if tool not in _TOOLS:
            return SkillResult.fail(f"unsupported tool: {tool}", skill_name=self.meta.name)
        product = str(ctx.inputs.get("product") or ctx.inputs.get("input") or "未指定").strip()
        audience = ctx.inputs.get("audience", "B2B 决策者")
        constraints = ctx.inputs.get("constraints", "中文输出，≤ 200 字")

        prompt = _PROMPT.format(product=product, audience=audience, tool=_TOOLS[tool]["label"], constraints=constraints)
        raw = self.call_llm(prompt)

        output = _synth(tool=tool, product=product, audience=audience)
        ctx.put("marketing", output)
        return SkillResult.ok(
            data={"tool": tool, "label": _TOOLS[tool]["label"], "output": output},
            skill_name=self.meta.name,
            logs=[f"marketing tool={tool}, product='{product}'"],
            metadata={"prompt_chars": len(prompt)},
        )


def _synth(*, tool: str, product: str, audience: str) -> Dict[str, Any]:
    if tool == "seo_brief":
        return {
            "title": f"{product} 完整指南（{audience} 必读）",
            "outline": [
                "为什么 {p} 重要".format(p=product),
                "3 大核心误区",
                "实操步骤 + 案例",
                "常见问题 FAQ",
            ],
            "keywords": [product, f"{product} 教程", f"{product} 案例", f"{audience} 痛点"],
        }
    if tool == "landing_page":
        return {
            "headline": f"让 {audience} 爱上 {product} 的 5 个理由",
            "subhead": "3 分钟看完，立刻上手",
            "bullets": [
                "理由 1：节省 80% 时间",
                "理由 2：效果可量化",
                "理由 3：行业头部都在用",
            ],
            "cta": "立即免费试用",
        }
    if tool == "email_subject":
        return {
            "subjects": [
                f"{product} 上新了，专属你的福利",
                f"[限时] {audience} 不可错过的 5 个洞察",
                "你可能错过了一个 10 倍效率的秘密",
            ]
        }
    if tool == "ad_copy":
        return {
            "headlines": [f"{product}：3 分钟上手", f"{audience} 的效率神器"],
            "primary_text": f"如果你是 {audience}，{product} 可以帮你节省 80% 的时间。",
            "cta": "立即了解",
        }
    if tool == "lead_magnet":
        return {
            "title": f"《{product} 实操手册》",
            "promise": f"读完这份手册，{audience} 可以在 7 天内跑通 {product} 的完整流程。",
            "outline": ["第 1 章 入门", "第 2 章 进阶", "第 3 章 案例", "附录 模板"],
        }
    return {}