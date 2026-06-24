"""P4-8-W1: awesome_gpt_image — AI image prompt library.

Borrowed from *Awesome-GPT-Image-Prompts* (a curated corpus of Midjourney /
Stable Diffusion / DALL-E prompt templates).  This skill surfaces the
top-N prompts for a category and lets the caller refine / mix.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


# A small curated catalogue.  Real deployment plugs a larger corpus here.
_CATALOGUE: Dict[str, List[Dict[str, str]]] = {
    "portrait": [
        {"title": "Cinematic headshot", "prompt": "85mm f/1.4, Rembrandt lighting, bokeh background"},
        {"title": "Studio portrait", "prompt": "softbox key, rim light, neutral grey backdrop"},
    ],
    "landscape": [
        {"title": "Misty mountain", "prompt": "layered ridges, golden hour, volumetric fog"},
        {"title": "Coastal sunset", "prompt": "low tide, wet sand reflections, vivid sky"},
    ],
    "product": [
        {"title": "Hero shot", "prompt": "white cyc, 45° angle, soft shadow"},
        {"title": "Lifestyle flat-lay", "prompt": "top-down, prop arrangement, neutral palette"},
    ],
    "concept": [
        {"title": "Cyberpunk street", "prompt": "neon reflections, rain puddles, narrow alley"},
        {"title": "Pastel dreamscape", "prompt": "cotton candy clouds, soft pinks, surreal scale"},
    ],
}


_PROMPT = """你是图像生成 prompt 专家，请基于以下风格 + 关键词生成 {n} 条高级 prompt（英文）：

风格：{category}
关键词：{kw}
约束：每条 ≤ 60 词，包含镜头 / 光线 / 材质 / 情绪。
"""


@skill(
    name="awesome_gpt_image",
    description="AI 图片 prompt 素材库（按风格 / 关键词检索 + 改写）",
    category=SkillCategory.IMAGE,
    version="1.0.0",
    tags=["image", "prompt", "midjourney", "stable-diffusion", "dall-e"],
)
class AwesomeGPTImageSkill(Skill):
    """Image-prompt catalogue + rewriter."""

    async def execute(self, ctx: SkillContext) -> SkillResult:
        category = str(ctx.inputs.get("category") or ctx.inputs.get("input") or "concept").strip().lower()
        kw = ctx.inputs.get("keywords", ctx.inputs.get("kw", ""))
        n = int(ctx.inputs.get("n", 4))

        catalogue = list(_CATALOGUE.get(category, []))
        if not catalogue:
            catalogue = _CATALOGUE["concept"]

        # Always generate fresh variants via the LLM (or mock).
        prompt = _PROMPT.format(n=n, category=category, kw=kw)
        raw = self.call_llm(prompt)

        variants: List[Dict[str, Any]] = []
        for i in range(n):
            base = catalogue[i % len(catalogue)]
            variants.append({
                "title": f"{base['title']} v{i + 1}",
                "prompt": f"{base['prompt']}, variant {i + 1}, {kw}".strip(", "),
                "seed": 1000 + i,
                "category": category,
            })

        ctx.put("prompts", variants)
        return SkillResult.ok(
            data={"category": category, "count": len(variants), "prompts": variants},
            skill_name=self.meta.name,
            logs=[f"served {len(variants)} prompts for category '{category}'"],
            metadata={"prompt_chars": len(prompt)},
        )