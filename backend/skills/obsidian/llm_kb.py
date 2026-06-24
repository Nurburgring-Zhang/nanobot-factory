"""P4-8-W1: LLM-driven knowledge base builder.

Inspired by claude-obsidian-view's auto-KB feature: extract
wiki-ready snippets from session messages / ticket transcripts /
annotation samples, ask the LLM (or deterministic mock) for a title
and tags, then upsert into a :class:`KnowledgeGraph`.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .wiki import KnowledgeGraph, WikiPage

logger = logging.getLogger(__name__)


@dataclass
class KBIngestItem:
    """One piece of raw material to ingest."""

    source: str               # "session" / "ticket" / "annotation"
    source_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KBIngestReport:
    pages: List[Dict[str, Any]] = field(default_factory=list)
    skipped: int = 0
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.ended_at <= 0 or self.started_at <= 0:
            return 0.0
        return (self.ended_at - self.started_at) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ingested": len(self.pages),
            "skipped": self.skipped,
            "duration_ms": round(self.duration_ms, 2),
            "pages": list(self.pages),
        }


class LLMKnowledgeBase:
    """Pull items from sources → summarise → upsert into a wiki page."""

    def __init__(self, graph: KnowledgeGraph, *, llm: Any = None) -> None:
        self.graph = graph
        self._llm = llm

    def set_llm(self, llm: Any) -> None:
        self._llm = llm

    # ── Public ingest API ──────────────────────────────────────────────────
    def ingest(self, items: Sequence[KBIngestItem], *,
               dedupe: bool = True) -> KBIngestReport:
        report = KBIngestReport(started_at=time.time())
        seen_hashes: set[str] = set()
        for item in items:
            content = (item.content or "").strip()
            if not content:
                report.skipped += 1
                continue
            if dedupe:
                digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
                if digest in seen_hashes:
                    report.skipped += 1
                    continue
                seen_hashes.add(digest)

            slug, title, body, tags = self._summarise(item)
            page = self.graph.upsert(
                slug=slug,
                title=title,
                content=body,
                tags=tags + [f"src:{item.source}"],
                metadata={
                    "source": item.source,
                    "source_id": item.source_id,
                    "ingested_at": time.time(),
                },
            )
            report.pages.append(page.to_dict())
        report.ended_at = time.time()
        return report

    def ingest_session(
        self,
        session_id: str,
        messages: Sequence[Dict[str, Any]],
        *,
        dedupe: bool = True,
    ) -> KBIngestReport:
        content = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in messages
            if m.get("content")
        )
        return self.ingest(
            [KBIngestItem(source="session", source_id=session_id, content=content)],
            dedupe=dedupe,
        )

    # ── Summarise (LLM or deterministic) ───────────────────────────────────
    def _summarise(self, item: KBIngestItem) -> tuple[str, str, str, List[str]]:
        """Return (slug, title, body, tags).

        When ``llm`` is None, uses a deterministic extractor that produces
        a usable wiki page from the raw content.
        """
        content = item.content
        if self._llm is not None:
            try:
                out = self._llm.generate(
                    prompt=(
                        "请把以下内容总结成一个 wiki 页面，输出 JSON: "
                        "{\"slug\": \"kebab-case\", \"title\": \"...\", "
                        "\"body\": \"markdown\", \"tags\": [\"...\"]}\n\n"
                        f"内容：{content[:2000]}"
                    ),
                )
                import json as _json
                obj = _json.loads(out)
                return (
                    obj.get("slug") or _slug(content),
                    obj.get("title") or "未命名",
                    obj.get("body") or content[:1200],
                    list(obj.get("tags") or []),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM summarise failed: %s", exc)

        # Deterministic fallback
        head = content.splitlines()[0] if content else "untitled"
        body = content[:1200] + ("\n\n…(truncated)…" if len(content) > 1200 else "")
        tags = _extract_tags_zh(content, top_k=3)
        return _slug(head), head[:60], body, tags


def _slug(text: str) -> str:
    import re
    text = re.sub(r"[^\w\-]+", "-", (text or "").strip().lower())[:48]
    return text or f"page-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:6]}"


def _extract_tags_zh(text: str, top_k: int = 3) -> List[str]:
    import re
    text = re.sub(r"[^\w\u4e00-\u9fff\s]+", " ", text or "")
    words = [w for w in re.split(r"[\s,。!?;:]+", text) if 2 <= len(w) <= 10]
    counts: Dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]]


__all__ = ["LLMKnowledgeBase", "KBIngestItem", "KBIngestReport"]