"""83 渠道适配器 (P19-B3 §6)

首批 5 渠道 (P19-B3):
    - google_images: scrape via public search
    - open_images: REST API (公开, 无需 key)
    - flickr: REST API + OAuth (公开)
    - unsplash: REST API (公开, 需 demo key)
    - pixabay: REST API (公开, 需 key)

P20-B1 — 5 web image crawlers (公开, 无 key):
    - baidu_images:    image.baidu.com
    - sogou_images:    pic.sogou.com
    - so_images:       image.so.com (360)
    - bing_images:     bing.com/images
    - duckduckgo_images: duckduckgo.com (隐私, vqd token 两步抓取)

每个渠道在缺少 API key 时返回 mock/placeholder data, 保证测试与离线运行.

统一 item schema (P19-C1-fix P0 #2):
    每个渠道实现 _build_item(raw_dict, prep, idx) -> CrawledItem
    返回统一 10 字段 CrawledItem.

Pydantic v2 (P20-B1):
    现代 async search() API 使用 Pydantic v2 模型:
    - SearchRequest  : query / max_results / page 输入验证
    - CrawledItemModel : 10 字段输出 (与 dataclass CrawledItem 对应)
    - SearchResponse  : 完整搜索响应 (items + count + metadata)
    详见 _schemas.py.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import BaseCrawler, CrawledItem
from ..config import CrawlerConfig
from ._schemas import CrawledItemModel, SearchRequest, SearchResponse

logger = logging.getLogger(__name__)


# Pydantic 公开导出
__all_pydantic__ = ["CrawledItemModel", "SearchRequest", "SearchResponse"]


class ChannelCrawler(BaseCrawler):
    """渠道适配器基类 — 所有 channels 继承

    实现要点:
    - 继承 BaseCrawler
    - 重写 _prepare / _do_fetch / _parse
    - 缺少 API key 时返回 mock (用 mock=True 显式声明)
    - 实现 _build_item(raw, prep, idx) -> CrawledItem (P19-C1-fix P0 #2)
    """

    channel = "channel_base"
    api_endpoint: str = ""
    requires_key: bool = False
    key_env_var: str = ""

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 api_key: Optional[str] = None, mock: bool = False):
        super().__init__(config=config)
        self.api_key = api_key or os_environ(self.key_env_var)
        self.mock = mock or (self.requires_key and not self.api_key)
        if self.mock:
            logger.info(
                "%s running in MOCK mode (no API key)",
                self.__class__.__name__,
            )

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> tuple:
        raise NotImplementedError

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> tuple:
        raise NotImplementedError

    # 子类实现 — 把 raw 字典构建成统一的 10 字段 CrawledItem
    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        """渠道特定的 item 构造逻辑 — 默认实现基于通用 placeholder + raw 覆盖.

        子类可重写以使用渠道特定字段 (Pixabay 的 user 等).
        """
        url = (
            raw.get("url")
            or raw.get("largeImageURL")
            or raw.get("webformatURL")
            or raw.get("previewURL")
            or raw.get("link")
            or ""
        )
        thumbnail = raw.get("thumbnail_url", "") or url
        title = raw.get("title", "")
        # 处理 title 是 tags 字符串的情况 (Pixabay)
        if isinstance(title, str) and "," in title and len(title) > 80:
            # 看起来像 tags-list, 移到 keywords
            keywords = [t.strip() for t in title.split(",") if t.strip()]
        else:
            keywords = list(raw.get("tags") or raw.get("keywords") or [])
        return CrawledItem(
            id=str(raw.get("id") or f"{self.channel}_{idx:04d}"),
            url=url,
            title=title if not isinstance(title, str) or "," not in title else "",
            description=raw.get("description", "") or raw.get("snippet", ""),
            source=self.channel,
            author=raw.get("author", "") or raw.get("owner", "")
                   or raw.get("user", ""),
            keywords=keywords,
            created_at=datetime.utcnow(),
            thumbnail_url=thumbnail,
            extra={
                "width": raw.get("width", 0),
                "height": raw.get("height", 0),
                "license": raw.get("license", "unknown"),
                "mock": self.mock,
            },
        )


def os_environ(name: str) -> Optional[str]:
    import os
    return os.environ.get(name) if name else None


def placeholder_image_item(url: str, source: str, idx: int) -> Dict[str, Any]:
    """通用 placeholder data — 给 mock 渠道用 (legacy 用法)

    新代码请用 ChannelCrawler._build_item() 返回 CrawledItem.
    """
    return {
        "url": url,
        "thumbnail_url": url,
        "source": source,
        "id": f"{source}_{idx:04d}",
        "title": f"Sample {source} item {idx}",
        "width": 1024,
        "height": 768,
        "license": "mock",
        "tags": ["sample", "mock"],
        "mock": True,
    }