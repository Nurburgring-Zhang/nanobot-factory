"""P4-8-W1: guizang_ppt — idea → PPT outline + slide deck.

Borrowed from the open-source *guizangPPTX* pattern: take a topic (and
optional outline), and produce a structured slide deck as JSON ready for
export to .pptx via python-pptx.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..base import Skill, SkillCategory, skill
from ..context import SkillContext
from ..result import SkillResult


_log = logging.getLogger(__name__)


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
        # Surface parse diagnostics so callers can see whether the deck came
        # from the LLM or fell back to the synthetic template.
        warnings: List[str] = []
        if deck.get("_parse_source") == "fallback_template":
            warnings.append(
                "ppt deck fell back to synthetic template: "
                + "; ".join(deck.get("_parse_errors") or ["no JSON found"])
            )
        return SkillResult.ok(
            data={"topic": topic, "slide_count": slide_count, "deck": deck},
            skill_name=self.meta.name,
            logs=[f"generated {len(deck['slides'])} slides for '{topic}'",
                  f"parse_source={deck.get('_parse_source')}"],
            metadata={
                "prompt_chars": len(prompt),
                "model": "mock" if self._llm is None else "live",
                "parse_source": deck.get("_parse_source", "unknown"),
                "parse_errors": list(deck.get("_parse_errors") or []),
            },
        ) if not warnings else SkillResult.ok(
            data={"topic": topic, "slide_count": slide_count, "deck": deck},
            skill_name=self.meta.name,
            logs=[f"generated {len(deck['slides'])} slides for '{topic}'",
                  f"parse_source={deck.get('_parse_source')}",
                  warnings[0]],
            metadata={
                "prompt_chars": len(prompt),
                "model": "mock" if self._llm is None else "live",
                "parse_source": deck.get("_parse_source", "unknown"),
                "parse_errors": list(deck.get("_parse_errors") or []),
                "warning": warnings[0],
            },
        )


def _synthesize_deck(topic: str, slide_count: int,
                     parse_errors: List[str]) -> Dict[str, Any]:
    """Synthesise a fallback deck template.

    Returns a dict with ``_parse_source="fallback_template"`` and the
    accumulated ``_parse_errors`` so callers can audit why the LLM output
    was rejected.
    """
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
        "_parse_source": "fallback_template",
        "_parse_errors": list(parse_errors),
    }


def _coerce_deck_obj(obj: Any, topic: str) -> Optional[Dict[str, Any]]:
    """Return a deck dict if ``obj`` is a valid deck, otherwise ``None``.

    Accepts both ``{title, slides:[...]}`` and bare ``[slide1, slide2]``
    shapes so we degrade gracefully on permissive LLM output.
    """
    if isinstance(obj, dict) and isinstance(obj.get("slides"), list):
        obj.setdefault("title", topic)
        return obj
    if isinstance(obj, list) and obj and all(isinstance(s, dict) for s in obj):
        return {"title": topic, "slides": list(obj)}
    return None


def _parse_deck(raw: str, *, topic: str, slide_count: int) -> Dict[str, Any]:
    """Parse the LLM response into a deck dict, falling back to a template.

    Returns a deck dict that always carries:

      * ``_parse_source`` — one of ``"direct_json"`` / ``"json_block"`` /
        ``"bare_list"`` / ``"fallback_template"``.
      * ``_parse_errors`` — list of human-readable reasons the parse path
        failed before the final source was selected (empty on success).
    """
    errors: List[str] = []
    text = (raw or "").strip()

    # 1. Direct JSON object.
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            coerced = _coerce_deck_obj(obj, topic)
            if coerced is not None:
                coerced["_parse_source"] = (
                    "direct_json" if isinstance(obj, dict) else "bare_list")
                coerced["_parse_errors"] = []
                return coerced
            errors.append(
                f"direct_json: top-level shape rejected "
                f"(type={type(obj).__name__})")
        except json.JSONDecodeError as exc:
            errors.append(
                f"direct_json: JSONDecodeError at pos {exc.pos}: {exc.msg}")
            _log.debug("guizang_ppt.direct_json_failed: %s", exc)

    # 2. Trailing JSON object/array in the response.
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])\s*$", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            coerced = _coerce_deck_obj(obj, topic)
            if coerced is not None:
                coerced["_parse_source"] = (
                    "json_block" if isinstance(obj, dict) else "bare_list")
                coerced["_parse_errors"] = []
                return coerced
            errors.append(
                f"json_block: shape rejected (type={type(obj).__name__})")
        except json.JSONDecodeError as exc:
            errors.append(
                f"json_block: JSONDecodeError at pos {exc.pos}: {exc.msg}")
            _log.debug("guizang_ppt.json_block_failed: %s", exc)
    else:
        errors.append("json_block: no trailing { or [ found in LLM output")

    # 3. Fallback: synthesize a deck template.
    _log.warning(
        "guizang_ppt.fallback_template: topic=%r errors=%s",
        topic, errors,
    )
    return _synthesize_deck(topic, slide_count, errors)