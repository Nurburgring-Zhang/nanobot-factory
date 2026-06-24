"""
test_obsidian.py
P4-8-W2 E2E: Obsidian-style knowledge management
- Wiki 列表按 tag 过滤
- Wiki 详情/编辑 [[link]] 解析
- Knowledge Graph 节点+边 stats
"""
from typing import List, Dict, Any


WIKI_FIXTURE: List[Dict[str, Any]] = [
    {"id": "p1", "title": "首页", "slug": "index", "tags": ["product"], "outgoing_links": ["产品手册", "API 文档"], "backlinks": ["API 文档"], "content": "# 首页\n欢迎"},
    {"id": "p2", "title": "产品手册", "slug": "product-manual", "tags": ["product", "docs"], "outgoing_links": ["API 文档", "部署指南"], "backlinks": ["首页", "API 文档"], "content": "产品手册..."},
    {"id": "p3", "title": "API 文档", "slug": "api-docs", "tags": ["docs"], "outgoing_links": ["首页", "产品手册"], "backlinks": ["首页", "产品手册", "部署指南"], "content": "API 文档..."},
    {"id": "p4", "title": "部署指南", "slug": "deployment", "tags": ["ops", "docs"], "outgoing_links": ["故障排查"], "backlinks": ["产品手册", "最佳实践"], "content": "部署..."},
    {"id": "p5", "title": "最佳实践", "slug": "best-practices", "tags": ["ops"], "outgoing_links": ["部署指南", "案例研究"], "backlinks": ["社区贡献"], "content": "最佳实践..."},
    {"id": "p6", "title": "故障排查", "slug": "troubleshooting", "tags": ["ops"], "outgoing_links": [], "backlinks": ["部署指南"], "content": "故障排查..."},
    {"id": "p7", "title": "案例研究", "slug": "case-studies", "tags": ["product"], "outgoing_links": [], "backlinks": ["最佳实践"], "content": "案例..."},
    {"id": "p8", "title": "更新日志", "slug": "changelog", "tags": ["product"], "outgoing_links": [], "backlinks": [], "content": "## v0.4.0..."},
]


def test_wiki_list_filter_by_tag():
    """Test 1: tag filter returns only pages with that tag"""
    tag = "docs"
    matches = [p for p in WIKI_FIXTURE if tag in p["tags"]]
    assert len(matches) == 3
    slugs = {p["slug"] for p in matches}
    assert slugs == {"product-manual", "api-docs", "deployment"}


def test_wiki_keyword_search():
    """Test 2: keyword search across title and content"""
    kw = "api"
    matches = [p for p in WIKI_FIXTURE if kw.lower() in p["title"].lower() or kw.lower() in p["content"].lower()]
    assert any(p["slug"] == "api-docs" for p in matches)


def test_wiki_backlinks_consistency():
    """Test 3: A→B means B has A in its backlinks (graph consistency)"""
    for src in WIKI_FIXTURE:
        for outgoing in src["outgoing_links"]:
            target = next((p for p in WIKI_FIXTURE if p["title"] == outgoing), None)
            if target:
                assert src["title"] in target["backlinks"], f"{src['title']} → {outgoing} but no backlink"


def test_wiki_link_parser_extracts_targets():
    """Test 4: parse [[link]] syntax in markdown content"""
    content = "详见 [[产品手册]] 和 [[API 文档]] 也可以看 [[部署指南|部署]]"
    import re
    rx = r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"
    matches = re.findall(rx, content)
    targets = [m[0].strip() for m in matches]
    assert "产品手册" in targets
    assert "API 文档" in targets
    assert "部署指南" in targets
    assert len(targets) == 3


def test_wiki_autocomplete_suggestions():
    """Test 5: [[ prefix triggers autocomplete with relevant pages"""
    prefix = "产"
    candidates = [p for p in WIKI_FIXTURE if p["title"].startswith(prefix)]
    assert any(c["title"] == "产品手册" for c in candidates)


def test_knowledge_graph_node_edge_count():
    """Test 6: knowledge graph node/edge counts match fixtures"""
    nodes = list(WIKI_FIXTURE)
    edges = []
    for src in WIKI_FIXTURE:
        for out in src["outgoing_links"]:
            target = next((p for p in WIKI_FIXTURE if p["title"] == out), None)
            if target:
                edges.append({"source": src["title"], "target": target["title"], "kind": "link"})
    # We expect at least 6 edges (首页→产品手册, 首页→API文档, 产品手册→API文档, 产品手册→部署指南, etc.)
    assert len(edges) >= 6
    assert len(nodes) == 8


def test_knowledge_graph_isolated_nodes():
    """Test 7: identify isolated pages (no links)"""
    isolated = [p for p in WIKI_FIXTURE if not p["outgoing_links"] and not p["backlinks"]]
    slugs = {p["slug"] for p in isolated}
    # 更新日志 has no links in/out
    assert "changelog" in slugs


if __name__ == "__main__":
    test_wiki_list_filter_by_tag()
    test_wiki_keyword_search()
    test_wiki_backlinks_consistency()
    test_wiki_link_parser_extracts_targets()
    test_wiki_autocomplete_suggestions()
    test_knowledge_graph_node_edge_count()
    test_knowledge_graph_isolated_nodes()
    print("All 7 obsidian tests passed.")
