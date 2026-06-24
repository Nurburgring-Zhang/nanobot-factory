"""Collection template: Web image crawl (批量网页图片采集).

Pipeline:
  1. seed_urls    — 输入一组起始 URL (或 sitemap)
  2. bfs_crawl    — 广度优先爬取 (max_depth / max_pages 限速)
  3. image_extract — 解析 HTML, 抽取 <img>/<source>/og:image
  4. hash_dedup   — pHash 去重
  5. oss_upload   — 上传到对象存储, 写 manifest.jsonl
"""
from __future__ import annotations
from typing import Any, Dict, List


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-coll-001",
    "name": "Web Image Crawl (网页图片批量采集)",
    "category": "collection",
    "description": (
        "从一组起始 URL 出发 BFS 爬取, 抽取页面图片, "
        "pHash 去重后上传对象存储, 输出 manifest.jsonl。"
    ),
    "tags": ["crawl", "image", "collection", "html"],
    "version": "1.0.0",
    "inputs": {
        "seed_urls": {"type": "array<string>", "required": True,
                       "description": "起始 URL 列表"},
        "max_depth": {"type": "int", "default": 2, "min": 0, "max": 5},
        "max_pages": {"type": "int", "default": 500, "min": 1, "max": 50000},
        "oss_bucket": {"type": "string", "default": "raw-images"},
    },
    "outputs": ["manifest.jsonl", "dedup_report.json"],
    "steps": [
        {"id": "seed", "name": "Seed URLs",
         "operator": "http.fetch", "config": {"urls": "$inputs.seed_urls"}},
        {"id": "bfs", "name": "BFS Crawl",
         "operator": "crawl.bfs",
         "config": {"max_depth": "$inputs.max_depth",
                    "max_pages": "$inputs.max_pages",
                    "respect_robots": True,
                    "rate_limit_rps": 2.0}},
        {"id": "extract", "name": "Extract Images",
         "operator": "html.extract_images",
         "config": {"selectors": ["img[src]", "source[srcset]",
                                  "meta[property='og:image']"],
                    "min_width": 256, "min_height": 256}},
        {"id": "dedup", "name": "pHash Dedup",
         "operator": "image.phash_dedup",
         "config": {"hash_bits": 64, "hamming_threshold": 6}},
        {"id": "upload", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "collection/web_crawl/",
                    "manifest": True}},
    ],
    "metrics": ["pages_crawled", "images_extracted", "images_unique",
                "images_uploaded", "duration_seconds"],
}


__all__ = ["TEMPLATE"]