"""P4-8-W1: Obsidian view tests — wiki parser, graph, LLM KB ingest."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

from skills.obsidian import (  # noqa: E402
    KBIngestItem,
    KnowledgeGraph,
    LLMKnowledgeBase,
    WikiLinkParser,
    reset_singletons_for_test,
)


@pytest.fixture
def graph():
    g = KnowledgeGraph()
    yield g


# ── 1. WikiLinkParser ────────────────────────────────────────────────────────
def test_wikilink_parser_finds_links_and_aliases():
    text = "See [[Project Phoenix]] and [[design-phoenix|the design docs]] for context."
    pairs = WikiLinkParser.find_links(text)
    slugs = [s for s, _ in pairs]
    aliases = [a for _, a in pairs]
    assert "Project Phoenix" in slugs
    assert "design-phoenix" in slugs
    assert "the design docs" in aliases


def test_wikilink_parser_extracts_tags():
    text = "Working on #machine-learning #ops #vdp-2026 today."
    tags = WikiLinkParser.extract_tags(text)
    assert set(tags) == {"machine-learning", "ops", "vdp-2026"}


# ── 2. Knowledge graph + backlinks ───────────────────────────────────────────
def test_graph_builds_backlinks_and_tag_cloud(graph):
    p1 = graph.upsert(slug="alpha", content="Hello #intro and link to [[beta]]")
    p2 = graph.upsert(slug="beta", content="See also [[alpha]] and [[gamma]] #main")
    assert p1.slug == "alpha"
    assert "beta" in p1.outgoing_links
    assert graph.backlinks("alpha") == ["beta"]
    assert graph.backlinks("beta") == ["alpha"]
    cloud = graph.tag_cloud()
    tag_names = {c["tag"] for c in cloud}
    assert {"intro", "main"}.issubset(tag_names)


def test_graph_export(graph):
    graph.upsert(slug="x", content="[[y]]")
    graph.upsert(slug="y", content="[[x]]")
    g = graph.graph()
    assert g["node_count"] == 2
    assert g["edge_count"] == 2
    edges = {(e["source"], e["target"]) for e in g["edges"]}
    assert ("x", "y") in edges and ("y", "x") in edges


# ── 3. LLM auto-KB ingest (deterministic mode) ──────────────────────────────
def test_llm_kb_ingest_dedupe_and_summary():
    g = KnowledgeGraph()
    kb = LLMKnowledgeBase(g)
    report = kb.ingest([
        KBIngestItem(source="session", source_id="s1",
                     content="AI 工厂正在改变数据生产方式 #ai #factory"),
        # Duplicate of the first — should be skipped.
        KBIngestItem(source="session", source_id="s2",
                     content="AI 工厂正在改变数据生产方式 #ai #factory"),
        KBIngestItem(source="ticket", source_id="t1",
                     content="用户反馈：希望增加自定义 skill。"),
    ])
    assert len(report.pages) == 2
    assert report.skipped == 1
    slugs = [p["slug"] for p in report.pages]
    assert any("ai" in s for s in slugs)


def test_llm_kb_ingest_session():
    g = KnowledgeGraph()
    kb = LLMKnowledgeBase(g)
    report = kb.ingest_session("sess42", [
        {"role": "user", "content": "我想要做 PPT"},
        {"role": "assistant", "content": "好的，请告诉我主题。"},
        {"role": "user", "content": "AI 工厂"},
    ])
    assert len(report.pages) == 1
    assert report.pages[0]["metadata"]["source"] == "session"
    assert "ppt" in (report.pages[0]["content"] or "").lower() or \
           "PPT" in (report.pages[0]["content"] or "")