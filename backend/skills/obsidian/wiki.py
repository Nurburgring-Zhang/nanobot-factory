"""P4-8-W1: ClaudeObsidianView — wiki links + knowledge graph.

Borrowed from claude-obsidian-view (7200★).  Provides:

  * ``WikiLinkParser``              — parses ``[[Page Name]]`` / ``[[slug|alias]]``
  * ``KnowledgeGraph``              — nodes + edges over wiki pages
  * ``backlinks(slug)``             — who links to this page?
  * ``tag_cloud(pages)``            — frequency-tagged list
  * 3-pane metadata (Karpathy LLM Wiki style) for HTML export

Storage is in-memory + JSON file (no DB dependency).  The optional
``vault_dir`` parameter points the writer at an Obsidian vault on disk.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Match [[Page Name]] or [[slug|alias]] or [[slug#heading]]
_WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]]+)?(?:\|([^\]]+))?\]\]")
# Match #tag at word boundaries (ASCII) or following whitespace
_TAG_RE = re.compile(r"(?:^|\s)#([\w\-/]+)")


@dataclass
class WikiPage:
    """A single wiki page."""

    slug: str
    title: str
    content: str = ""
    tags: List[str] = field(default_factory=list)
    outgoing_links: List[str] = field(default_factory=list)  # slugs
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "content": self.content,
            "tags": list(self.tags),
            "outgoing_links": list(self.outgoing_links),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "char_count": len(self.content),
        }


class WikiLinkParser:
    """Pure-function [[wiki link]] parser.  Stateless."""

    @staticmethod
    def find_links(text: str) -> List[Tuple[str, str]]:
        """Return [(slug, alias)] for every ``[[...]]`` in ``text``."""
        out: List[Tuple[str, str]] = []
        for m in _WIKILINK_RE.finditer(text or ""):
            slug = m.group(1).strip()
            alias = (m.group(2) or "").strip()
            out.append((slug, alias or slug))
        return out

    @staticmethod
    def extract_tags(text: str) -> List[str]:
        return list({m.group(1) for m in _TAG_RE.finditer(text or "")})


class KnowledgeGraph:
    """Bidirectional wiki graph.

    Backed by an in-memory dict + JSON file.  Thread-safe via RLock.
    """

    def __init__(self, vault_dir: Optional[str] = None) -> None:
        self._pages: Dict[str, WikiPage] = {}
        self._vault_dir = vault_dir
        # Reverse index: slug → set of slugs that link TO it
        self._backlinks: Dict[str, Set[str]] = {}
        # Tag → slugs
        self._tag_index: Dict[str, Set[str]] = {}
        try:
            import threading
            self._lock = threading.RLock()
        except ImportError:  # pragma: no cover
            self._lock = None  # type: ignore[assignment]

    # ── CRUD ───────────────────────────────────────────────────────────────
    def upsert(self, slug: str, content: str = "",
               title: Optional[str] = None,
               tags: Optional[List[str]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> WikiPage:
        slug = _slugify(slug)
        title = title or slug.replace("-", " ").title()
        tags = list(tags or []) + WikiLinkParser.extract_tags(content)
        tags = sorted({t for t in tags if t})

        with self._lock:
            existing = self._pages.get(slug)
            old_links = set(existing.outgoing_links) if existing else set()
            old_tags = set(existing.tags) if existing else set()

            outgoing = sorted({s for s, _ in WikiLinkParser.find_links(content)})
            page = WikiPage(
                slug=slug,
                title=title,
                content=content,
                tags=tags,
                outgoing_links=outgoing,
                metadata=dict(metadata or {}),
            )
            if existing:
                page.created_at = existing.created_at
            page.updated_at = time.time()
            self._pages[slug] = page

            # Update backlink index.
            for tgt in old_links - set(outgoing):
                self._backlinks.get(tgt, set()).discard(slug)
                self._backlinks.setdefault(tgt, set())
            for tgt in set(outgoing) - old_links:
                self._backlinks.setdefault(tgt, set()).add(slug)

            # Update tag index.
            for t in old_tags - set(tags):
                self._tag_index.get(t, set()).discard(slug)
            for t in set(tags) - old_tags:
                self._tag_index.setdefault(t, set()).add(slug)

            self._maybe_persist(page)
            return page

    def delete(self, slug: str) -> bool:
        slug = _slugify(slug)
        with self._lock:
            page = self._pages.pop(slug, None)
            if page is None:
                return False
            for tgt in page.outgoing_links:
                if tgt in self._backlinks:
                    self._backlinks[tgt].discard(slug)
            for t in page.tags:
                if t in self._tag_index:
                    self._tag_index[t].discard(slug)
            return True

    def get(self, slug: str) -> Optional[WikiPage]:
        return self._pages.get(_slugify(slug))

    def list_pages(self, tag: Optional[str] = None) -> List[WikiPage]:
        with self._lock:
            if tag is None:
                return list(self._pages.values())
            slugs = self._tag_index.get(tag, set())
            return [p for p in self._pages.values() if p.slug in slugs]

    # ── Graph queries ──────────────────────────────────────────────────────
    def backlinks(self, slug: str) -> List[str]:
        slug = _slugify(slug)
        with self._lock:
            return sorted(self._backlinks.get(slug, set()))

    def tag_cloud(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(
                ({"tag": t, "count": len(slugs)} for t, slugs in self._tag_index.items()),
                key=lambda d: (-d["count"], d["tag"]),
            )

    def graph(self) -> Dict[str, Any]:
        """Export the full graph as nodes + edges."""
        with self._lock:
            nodes = []
            for p in self._pages.values():
                nodes.append({
                    "id": p.slug,
                    "label": p.title,
                    "tag_count": len(p.tags),
                    "size": 10 + 4 * len(p.outgoing_links) + 2 * len(self._backlinks.get(p.slug, set())),
                })
            edges = []
            for p in self._pages.values():
                for tgt in p.outgoing_links:
                    edges.append({"source": p.slug, "target": tgt})
            return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    # ── Persistence ────────────────────────────────────────────────────────
    def _maybe_persist(self, page: WikiPage) -> None:
        if not self._vault_dir:
            return
        try:
            os.makedirs(self._vault_dir, exist_ok=True)
            path = os.path.join(self._vault_dir, f"{page.slug}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"# {page.title}\n\n")
                for tag in page.tags:
                    fh.write(f"#{tag} ")
                fh.write("\n\n")
                fh.write(page.content)
                fh.write("\n")
        except OSError:
            pass

    def load_from_vault(self) -> int:
        """Load every ``*.md`` file from ``vault_dir`` as a wiki page.

        Returns the number of pages loaded.  Missing vault dir = 0.
        """
        if not self._vault_dir or not os.path.isdir(self._vault_dir):
            return 0
        count = 0
        for fname in sorted(os.listdir(self._vault_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self._vault_dir, fname)
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
            slug = fname[:-3]
            title = raw.splitlines()[0].lstrip("# ").strip() if raw else slug
            body = "\n".join(raw.splitlines()[1:]) if raw else ""
            self.upsert(slug=slug, title=title, content=body)
            count += 1
        return count

    def export_json(self) -> str:
        with self._lock:
            return json.dumps(
                {"pages": [p.to_dict() for p in self._pages.values()]},
                ensure_ascii=False, indent=2,
            )


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w\-/]", "", text)
    return text or f"page-{uuid.uuid4().hex[:6]}"


__all__ = [
    "WikiPage",
    "WikiLinkParser",
    "KnowledgeGraph",
    "_slugify",
]