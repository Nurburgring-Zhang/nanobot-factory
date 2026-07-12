"""智影 V5 — 广告数据源抽象 (Meta Ad Library / Google Ads Transparency / X / Reddit)"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompetitorAd:
    """竞品广告"""

    ad_id: str = field(default_factory=lambda: f"ad-{uuid.uuid4().hex[:8]}")
    advertiser: str = ""
    platform: str = ""  # "meta" | "google" | "x" | "reddit"
    format: str = ""  # "image" | "video" | "carousel" | "text"
    headline: str = ""
    body: str = ""
    cta: str = ""
    landing_url: str = ""
    media_urls: List[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    region: str = ""
    language: str = ""
    impressions: int = 0
    spend_estimate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ad_id": self.ad_id,
            "advertiser": self.adiser if hasattr(self, "adiser") else self.advertiser,
            "platform": self.platform,
            "format": self.format,
            "headline": self.headline,
            "body": self.body[:300],
            "cta": self.cta,
            "landing_url": self.landing_url,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "region": self.region,
            "language": self.language,
            "impressions": self.impressions,
            "spend_estimate": self.spend_estimate,
        }


class AdSource(ABC):
    """广告数据源抽象"""

    def __init__(self, name: str, platform: str):
        self.name = name
        self.platform = platform
        self._cache: Dict[str, List[CompetitorAd]] = {}

    @abstractmethod
    async def fetch_ads(
        self, query: str, max_results: int = 50
    ) -> List[CompetitorAd]:
        pass

    def get_cached(self, query: str) -> Optional[List[CompetitorAd]]:
        return self._cache.get(query)

    def set_cache(self, query: str, ads: List[CompetitorAd]):
        self._cache[query] = ads


class MetaAdLibrary(AdSource):
    """Meta Ad Library 公开 API"""

    def __init__(self):
        super().__init__("Meta Ad Library", "meta")

    async def fetch_ads(
        self, query: str, max_results: int = 50
    ) -> List[CompetitorAd]:
        """实际访问 Meta Ad Library (需要 API token)

        这里实现 stub: 启发式生成演示数据
        真实环境: 调用 https://www.facebook.com/ads/library/async/search_ads/
        """
        # 模拟返回 30 条广告
        await asyncio.sleep(0.05)
        hooks = ["怕错过", "限时", "新品", "降30%", "专家推荐", "科学证明", "已售10万", "明星同款", "免费试用", "不满意退款"]
        ctas = ["立即购买", "马上领取", "了解更多", "立即试用", "Shop Now", "Learn More", "Sign Up", "Get Started", "Download", "Subscribe"]
        formats = ["image", "video", "carousel"]
        ads: List[CompetitorAd] = []
        for i in range(min(max_results, 30)):
            ads.append(
                CompetitorAd(
                    advertiser=query,
                    platform="meta",
                    format=formats[i % len(formats)],
                    headline=f"{query} {hooks[i % len(hooks)]}",
                    body=f"今天就来体验 {query} 的 {hooks[i % len(hooks)]} 优势。我们的产品已经帮助 10000+ 用户。",
                    cta=ctas[i % len(ctas)],
                    landing_url=f"https://example.com/{query.lower().replace(' ', '-')}",
                    start_date="2026-06-01",
                    end_date="",
                    region="US",
                    language="en",
                    impressions=10000 + i * 1000,
                    spend_estimate=100.0 + i * 50,
                )
            )
        self.set_cache(query, ads)
        return ads


class GoogleAdsTransparency(AdSource):
    """Google Ads Transparency Center"""

    def __init__(self):
        super().__init__("Google Ads Transparency", "google")

    async def fetch_ads(
        self, query: str, max_results: int = 50
    ) -> List[CompetitorAd]:
        await asyncio.sleep(0.05)
        hooks = ["Find Better", "Save More", "Top Rated", "Trusted", "Proven", "Award-Winning"]
        ctas = ["Visit Site", "Compare", "Try Free", "Get Quote", "Read More"]
        formats = ["text", "image", "video"]
        ads: List[CompetitorAd] = []
        for i in range(min(max_results, 20)):
            ads.append(
                CompetitorAd(
                    advertiser=query,
                    platform="google",
                    format=formats[i % len(formats)],
                    headline=f"{query} - {hooks[i % len(hooks)]}",
                    body=f"Compare {query} with competitors. Save more today.",
                    cta=ctas[i % len(ctas)],
                    landing_url=f"https://{query.lower().replace(' ', '')}.com",
                    region="US",
                    language="en",
                    impressions=5000 + i * 500,
                )
            )
        self.set_cache(query, ads)
        return ads


class XMonitor(AdSource):
    """X (Twitter) 趋势监控"""

    def __init__(self):
        super().__init__("X Monitor", "x")

    async def fetch_ads(
        self, query: str, max_results: int = 50
    ) -> List[CompetitorAd]:
        # X 监控帖子 (非广告)
        await asyncio.sleep(0.05)
        hooks = ["破防了", "离谱", "笑死", "泪目", "震撼", "安利", "踩雷", "惊艳", "续命", "封神"]
        ads: List[CompetitorAd] = []
        for i in range(min(max_results, 25)):
            ads.append(
                CompetitorAd(
                    advertiser=query,
                    platform="x",
                    format="text",
                    headline=f"关于 {query}",
                    body=f"{hooks[i % len(hooks)]} {query} 真的让我 {hooks[(i+1) % len(hooks)]}",
                    cta="查看",
                    start_date="2026-06-15",
                    region="US",
                    language="zh-CN" if i % 2 else "en",
                    impressions=2000 + i * 200,
                )
            )
        self.set_cache(query, ads)
        return ads


class RedditMonitor(AdSource):
    """Reddit 趋势监控"""

    def __init__(self):
        super().__init__("Reddit Monitor", "reddit")

    async def fetch_ads(
        self, query: str, max_results: int = 50
    ) -> List[CompetitorAd]:
        await asyncio.sleep(0.05)
        subreddits = ["r/MachineLearning", "r/Marketing", "r/technology", "r/BuyItForLife", "r/entrepreneur"]
        ads: List[CompetitorAd] = []
        for i in range(min(max_results, 25)):
            ads.append(
                CompetitorAd(
                    advertiser=query,
                    platform="reddit",
                    format="text",
                    headline=f"[{subreddits[i % len(subreddits)]}] {query} 讨论",
                    body=f"今天试了 {query}, 效果不错。推荐给大家。",
                    cta="查看讨论",
                    landing_url=f"https://reddit.com/{subreddits[i % len(subreddits)]}",
                    start_date="2026-06-20",
                    region="US",
                    language="en",
                    impressions=1500 + i * 150,
                )
            )
        self.set_cache(query, ads)
        return ads
