"""P4-8-W1: Obsidian view — public surface for the ClaudeObsidianView module.

Re-exports the most commonly used pieces and provides a tiny helper
to build a singleton knowledge graph bound to the platform's
``imdf`` data dir.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from .wiki import KnowledgeGraph, WikiLinkParser, WikiPage, _slugify
from .llm_kb import KBIngestItem, KBIngestReport, LLMKnowledgeBase

logger = logging.getLogger(__name__)


# ── Singleton knowledge graph ────────────────────────────────────────────────
_DEFAULT_VAULT_DIR = os.environ.get(
    "NANOBOT_OBSIDIAN_VAULT",
    os.path.join(os.path.expanduser("~"), ".nanobot", "obsidian_vault"),
)


_GRAPH_SINGLETON: Optional[KnowledgeGraph] = None
_GRAPH_LOCK = threading.Lock()


def get_knowledge_graph(vault_dir: Optional[str] = None) -> KnowledgeGraph:
    """Return the platform-wide KnowledgeGraph (lazy singleton)."""
    global _GRAPH_SINGLETON
    with _GRAPH_LOCK:
        if _GRAPH_SINGLETON is None:
            _GRAPH_SINGLETON = KnowledgeGraph(vault_dir=vault_dir or _DEFAULT_VAULT_DIR)
            loaded = _GRAPH_SINGLETON.load_from_vault()
            if loaded:
                logger.info("obsidian: loaded %d pages from vault", loaded)
        return _GRAPH_SINGLETON


def get_llm_kb(llm: object = None) -> LLMKnowledgeBase:
    return LLMKnowledgeBase(get_knowledge_graph(), llm=llm)


def reset_singletons_for_test() -> None:
    """Drop the singleton so the next call rebuilds it.  Test-only."""
    global _GRAPH_SINGLETON
    with _GRAPH_LOCK:
        _GRAPH_SINGLETON = None


__all__ = [
    "KnowledgeGraph",
    "WikiLinkParser",
    "WikiPage",
    "LLMKnowledgeBase",
    "KBIngestItem",
    "KBIngestReport",
    "get_knowledge_graph",
    "get_llm_kb",
    "reset_singletons_for_test",
]