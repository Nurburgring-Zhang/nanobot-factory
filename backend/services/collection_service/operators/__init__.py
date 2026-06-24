"""collection_service.operators — 15 collection operators registry (P3-5-W2).

All operators share signature:  run(query: str, params: dict) -> dict

Exports:
  OPERATORS: dict[str, callable]
  OPERATOR_META: dict[str, dict]
  list_operators(source, modality) / get_operator(id) / get_meta(id)
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import (
    web_crawler,
    youtube_dl,
    twitter_dl,
    bilibili_dl,
    instagram_dl,
    tiktok_dl,
    wikipedia_api,
    unsplash_api,
    pexels_api,
    pixabay_api,
    common_crawl,
    arxiv_api,
    github_api,
    kaggle_api,
    huggingface_api,
)


_META_TABLE: List[Dict[str, Any]] = [
    {"id": "collect.web.crawler", "name": "Web Page Crawler",
     "source": "web", "modality": "html",
     "description": "Generic HTTP fetch + HTML strip → text",
     "params": [
         {"name": "max_chars", "type": "int", "default": 4096, "required": False},
         {"name": "timeout", "type": "float", "default": 5.0, "required": False},
     ], "run": web_crawler.run},

    {"id": "collect.video.youtube", "name": "YouTube Video",
     "source": "youtube", "modality": "video",
     "description": "YouTube video metadata + thumbnail (sandbox: deterministic mock)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "include_meta", "type": "bool", "default": True, "required": False},
     ], "run": youtube_dl.run},

    {"id": "collect.social.twitter", "name": "Twitter / X Post",
     "source": "twitter", "modality": "text",
     "description": "Twitter post / thread collection (sandbox: mock)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
     ], "run": twitter_dl.run},

    {"id": "collect.video.bilibili", "name": "Bilibili Video",
     "source": "bilibili", "modality": "video",
     "description": "Bilibili video metadata + subtitle (sandbox: mock)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
     ], "run": bilibili_dl.run},

    {"id": "collect.social.instagram", "name": "Instagram Post",
     "source": "instagram", "modality": "image",
     "description": "Instagram post / reel / TV (sandbox: mock)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
     ], "run": instagram_dl.run},

    {"id": "collect.video.tiktok", "name": "TikTok Video",
     "source": "tiktok", "modality": "video",
     "description": "TikTok short video (sandbox: mock)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
     ], "run": tiktok_dl.run},

    {"id": "collect.api.wikipedia", "name": "Wikipedia Article",
     "source": "wikipedia", "modality": "text",
     "description": "Wikipedia REST summary (live) / mock fallback",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
     ], "run": wikipedia_api.run},

    {"id": "collect.image.unsplash", "name": "Unsplash Image Search",
     "source": "unsplash", "modality": "image",
     "description": "Unsplash photo search (needs UNSPLASH_ACCESS_KEY)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "api_key", "type": "str", "default": "", "required": False},
     ], "run": unsplash_api.run},

    {"id": "collect.video.pexels", "name": "Pexels Video / Photo Search",
     "source": "pexels", "modality": "video",
     "description": "Pexels videos or photos search (needs PEXELS_API_KEY)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "media_type", "type": "str", "default": "videos", "required": False},
         {"name": "api_key", "type": "str", "default": "", "required": False},
     ], "run": pexels_api.run},

    {"id": "collect.media.pixabay", "name": "Pixabay Image / Video / Audio",
     "source": "pixabay", "modality": "image",
     "description": "Pixabay multi-media search (needs PIXABAY_API_KEY)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "media_type", "type": "str", "default": "image", "required": False},
         {"name": "api_key", "type": "str", "default": "", "required": False},
     ], "run": pixabay_api.run},

    {"id": "collect.web.common_crawl", "name": "Common Crawl WARC Index",
     "source": "commoncrawl", "modality": "html",
     "description": "Common Crawl CDX index query (sandbox: mock)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "match_type", "type": "str", "default": "domain", "required": False},
     ], "run": common_crawl.run},

    {"id": "collect.academic.arxiv", "name": "arXiv Paper Search",
     "source": "arxiv", "modality": "text",
     "description": "arXiv Atom API search (live) / mock fallback",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
     ], "run": arxiv_api.run},

    {"id": "collect.code.github", "name": "GitHub Repo / Code / Issues",
     "source": "github", "modality": "text",
     "description": "GitHub search (repositories|code|issues)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "resource", "type": "str", "default": "repositories", "required": False},
     ], "run": github_api.run},

    {"id": "collect.dataset.kaggle", "name": "Kaggle Dataset / Competition",
     "source": "kaggle", "modality": "dataset",
     "description": "Kaggle search (datasets|competitions); needs KAGGLE_USERNAME/KEY",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "resource", "type": "str", "default": "datasets", "required": False},
     ], "run": kaggle_api.run},

    {"id": "collect.dataset.huggingface", "name": "HuggingFace Hub",
     "source": "huggingface", "modality": "dataset",
     "description": "HuggingFace Hub search (datasets|models|spaces)",
     "params": [
         {"name": "max_results", "type": "int", "default": 5, "required": False},
         {"name": "resource", "type": "str", "default": "datasets", "required": False},
     ], "run": huggingface_api.run},
]


OPERATORS: Dict[str, Callable] = {entry["id"]: entry["run"] for entry in _META_TABLE}


def _meta_without_callable(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "run"}


OPERATOR_META: Dict[str, Dict[str, Any]] = {
    entry["id"]: _meta_without_callable(entry) for entry in _META_TABLE
}


def list_operators(source: str = None, modality: str = None) -> List[Dict[str, Any]]:
    out = [_meta_without_callable(e) for e in _META_TABLE]
    if source:
        out = [e for e in out if e.get("source") == source]
    if modality:
        out = [e for e in out if e.get("modality") == modality]
    return out


def get_operator(op_id: str) -> Callable:
    return OPERATORS.get(op_id)


def get_meta(op_id: str) -> Dict[str, Any]:
    return OPERATOR_META.get(op_id)


__all__ = [
    "OPERATORS",
    "OPERATOR_META",
    "list_operators",
    "get_operator",
    "get_meta",
]
