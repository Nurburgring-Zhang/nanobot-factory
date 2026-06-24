"""P4-8-W1: anything_to_notebooklm — source → multi-format summary.

Borrowed from the *anything-to-notebooklm* project: takes a source
(article / video transcript / PDF text / URL) and produces a
NotebookLM-style briefing: TL;DR + key topics + FAQ + quotes.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是 NotebookLM 风格的内容提炼助手，请把以下源材料整理成结构化笔记：

源材料：
{source}

输出 JSON：{{
  "tldr": "≤ 50 字",
  "topics": ["主题 1", "主题 2", "..."],
  "faq": [{{"q": "...", "a": "..."}}],
  "quotes": ["原文金句 1", "原文金句 2"]
}}
"""


@skill(
    name="anything_to_notebooklm",
    description="把任意素材整理成 NotebookLM 风格的笔记（TL;DR + FAQ + 金句）",
    category=SkillCategory.RESEARCH,
    version="1.0.0",
    tags=["notebooklm", "summary", "tldr", "faq", "notes"],
)
class AnythingToNotebookLMSkill(Skill):
    """source → structured briefing."""

    DEFAULT_FAQ = 3
    DEFAULT_QUOTES = 2

    async def execute(self, ctx: SkillContext) -> SkillResult:
        source = str(ctx.inputs.get("source") or ctx.inputs.get("input") or "").strip()
        if not source:
            return SkillResult.fail("source 不能为空", skill_name=self.meta.name)

        prompt = _PROMPT.format(source=source[:2000])
        raw = self.call_llm(prompt)

        # Heuristic fallback note generation (works without a real LLM).
        sentences = [s.strip() for s in source.replace("。", ".").split(".") if s.strip()]
        tldr = (sentences[0] if sentences else source)[:80]
        topics = _extract_keywords(source, top_k=5)
        faq = _build_faq(source, sentences, n=self.DEFAULT_FAQ)
        quotes = [s for s in sentences[: self.DEFAULT_QUOTES * 2] if 8 <= len(s) <= 60][: self.DEFAULT_QUOTES]

        briefing = {
            "tldr": tldr,
            "topics": topics,
            "faq": faq,
            "quotes": quotes or [sentences[0][:60] if sentences else ""],
        }
        ctx.put("briefing", briefing)
        return SkillResult.ok(
            data={"source_chars": len(source), "briefing": briefing},
            skill_name=self.meta.name,
            logs=[f"topics={len(topics)}, faq={len(faq)}, quotes={len(quotes)}"],
            metadata={"prompt_chars": len(prompt)},
        )


def _extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """Cheap keyword extractor — splits on Chinese / English word boundaries."""
    import re
    text = re.sub(r"[^\w\u4e00-\u9fff\s]+", " ", text)
    words = [w for w in re.split(r"[\s,。!?;:]+", text) if 2 <= len(w) <= 12]
    counts: Dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    sorted_words = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in sorted_words[:top_k]]


def _build_faq(source: str, sentences: List[str], *, n: int) -> List[Dict[str, str]]:
    faq: List[Dict[str, str]] = []
    if not sentences:
        return faq
    for i in range(n):
        anchor = sentences[i % len(sentences)]
        faq.append({
            "q": f"关于源材料的第 {i + 1} 个常见问题？",
            "a": anchor[:120] + ("…" if len(anchor) > 120 else ""),
        })
    return faq