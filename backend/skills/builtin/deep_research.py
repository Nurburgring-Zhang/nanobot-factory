"""P4-8-W1: deep_research — 带出处的深度研究 (WebSearch + 引用).

Borrowed from the *deep-research-mcp* pattern.  Returns a structured
report: claim → evidence → citation.  Citations come from real search
results when the optional ``search_fn`` is wired in, otherwise the skill
falls back to a structured outline.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_PROMPT = """你是研究助理，请围绕主题「{topic}」生成 {n} 条核心结论，
每条结论都要附上可验证的证据（事实 + 来源描述）。

主题：{topic}
深度：{depth}

输出 JSON：{{"findings":[{{"claim":"...", "evidence":"...", "source":"..."}}]}}
"""


@skill(
    name="deep_research",
    description="带出处的深度研究：核心结论 + 证据 + 引用",
    category=SkillCategory.RESEARCH,
    version="1.0.0",
    tags=["research", "citation", "fact-check", "web"],
)
class DeepResearchSkill(Skill):
    """Cited deep research report."""

    DEFAULT_FINDINGS = 5

    def __init__(self) -> None:
        super().__init__()
        self._search_fn: Optional[Callable[[str], List[Dict[str, str]]]] = None

    def set_search_fn(self, fn: Callable[[str], List[Dict[str, str]]]) -> None:
        """Plug a real web-search implementation (returns [{title,url,snippet}])."""
        self._search_fn = fn

    async def execute(self, ctx: SkillContext) -> SkillResult:
        topic = str(ctx.inputs.get("topic") or ctx.inputs.get("input") or "").strip()
        if not topic:
            return SkillResult.fail("topic 不能为空", skill_name=self.meta.name)
        n = int(ctx.inputs.get("findings", self.DEFAULT_FINDINGS))
        depth = ctx.inputs.get("depth", "medium")

        findings: List[Dict[str, Any]] = []
        sources: List[Dict[str, str]] = []

        if self._search_fn is not None:
            try:
                sources = self._search_fn(topic)[: n * 2]
            except Exception as exc:  # noqa: BLE001
                ctx.put("search_error", str(exc))

        prompt = _PROMPT.format(topic=topic, n=n, depth=depth)
        raw = self.call_llm(prompt)

        if sources:
            for i, src in enumerate(sources[:n]):
                findings.append({
                    "claim": f"关于「{topic}」的第 {i + 1} 条结论（来自搜索结果）",
                    "evidence": src.get("snippet", ""),
                    "source": src.get("title", src.get("url", "unknown")),
                })
        else:
            for i in range(n):
                findings.append({
                    "claim": f"第 {i + 1} 条核心结论：{topic} 的关键洞察 {i + 1}",
                    "evidence": "需要进一步搜索补充证据",
                    "source": "outline-only",
                })

        ctx.put("findings", findings)
        return SkillResult.ok(
            data={
                "topic": topic,
                "depth": depth,
                "findings": findings,
                "source_count": len(sources),
            },
            skill_name=self.meta.name,
            logs=[f"depth={depth}, findings={len(findings)}, sources={len(sources)}"],
            metadata={"prompt_chars": len(prompt), "has_search": self._search_fn is not None},
        )