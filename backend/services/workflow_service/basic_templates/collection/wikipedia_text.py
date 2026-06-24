"""Collection template: Wikipedia text scrape.

Pipeline:
  1. title_list   — 输入 Wikipedia 文章标题列表 (支持多语言)
  2. fetch_html   — 通过 MediaWiki API 拉 HTML
  3. parse_text   — 提取正文 + 清理 (去除脚注/编辑链接)
  4. lang_detect  — 语言检测, 过滤非目标语言
  5. chunk_split  — 按段落/句子切块 (用于 RAG 训练)
  6. oss_upload   — 上传分块 JSONL
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-coll-003",
    "name": "Wikipedia Text Scrape (维基百科文本抓取)",
    "category": "collection",
    "description": (
        "批量抓取 Wikipedia 文章, 提取正文并按段落切块, "
        "适用于 RAG / 通用语料训练。"
    ),
    "tags": ["wikipedia", "text", "collection", "rag"],
    "version": "1.0.0",
    "inputs": {
        "titles": {"type": "array<string>", "required": True,
                    "description": "Wikipedia 文章标题"},
        "language": {"type": "string", "default": "en",
                      "description": "ISO 639-1, e.g. en/zh/de"},
        "target_language": {"type": "string", "default": "en"},
        "chunk_size_tokens": {"type": "int", "default": 512},
        "oss_bucket": {"type": "string", "default": "raw-text"},
    },
    "outputs": ["chunks.jsonl", "summary.json"],
    "steps": [
        {"id": "titles", "name": "Resolve Titles",
         "operator": "wikipedia.resolve_titles",
         "config": {"titles": "$inputs.titles",
                    "language": "$inputs.language"}},
        {"id": "fetch", "name": "Fetch HTML",
         "operator": "wikipedia.fetch_html",
         "config": {"language": "$inputs.language",
                    "rate_limit_rps": 5.0}},
        {"id": "parse", "name": "Parse Text",
         "operator": "wikipedia.parse_text",
         "config": {"strip": ["references", "edit-links",
                              "citation", "navbox", "infobox"]}},
        {"id": "lang", "name": "Language Filter",
         "operator": "text.lang_detect",
         "config": {"target": "$inputs.target_language",
                    "min_confidence": 0.9}},
        {"id": "chunk", "name": "Chunk Split",
         "operator": "text.chunk_split",
         "config": {"strategy": "paragraph",
                    "max_tokens": "$inputs.chunk_size_tokens",
                    "overlap_tokens": 64}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "collection/wikipedia/",
                    "manifest": True}},
    ],
    "metrics": ["articles_resolved", "articles_kept",
                "chunks_total", "duration_seconds"],
}


__all__ = ["TEMPLATE"]