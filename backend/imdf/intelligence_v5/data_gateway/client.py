"""智影 V5 — Data Gateway 平台 + Client"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Platform(str, Enum):
    """RedFox 13 平台"""
    XIAOHONGSHU = "xiaohongshu"  # 小红书
    DOUYIN = "douyin"            # 抖音
    WECHAT_OFFICIAL = "wechat"  # 公众号
    TIKTOK = "tiktok"            # TikTok
    BILIBILI = "bilibili"        # B站
    WEIBO = "weibo"              # 微博
    XIAOMIYAN = "xiaomiyan"      # 小红书 (米岩, 同义)
    ZHIHU = "zhihu"              # 知乎
    DOUBAN = "douban"            # 豆瓣
    TWITTER = "twitter"          # X
    YOUTUBE = "youtube"          # YouTube
    KUAISHOU = "kuaishou"        # 快手
    AI_SEARCH = "ai_search"      # AI 搜索聚合


class DataCategory(str, Enum):
    """数据类型"""
    HOT_TOPIC = "hot_topic"          # 热门话题
    TREND = "trend"                  # 趋势
    KEYWORD = "keyword"              # 关键词
    ACCOUNT_INFO = "account_info"    # 账号信息
    POST_DETAIL = "post_detail"      # 帖子详情
    POSTS_LIST = "posts_list"        # 帖子列表
    FOLLOWERS = "followers"          # 粉丝
    VIEWS = "views"                  # 阅读
    LIKES = "likes"                  # 点赞
    COMMENTS = "comments"            # 评论
    SENTIMENT = "sentiment"          # 情感


@dataclass
class DataItem:
    """数据项"""

    item_id: str = field(default_factory=lambda: f"di-{uuid.uuid4().hex[:10]}")
    platform: Platform = Platform.XIAOHONGSHU
    category: DataCategory = DataCategory.HOT_TOPIC
    title: str = ""
    content: str = ""
    url: str = ""
    author: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)  # {views, likes, comments, ...}
    raw_data: Dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "platform": self.platform.value,
            "category": self.category.value,
            "title": self.title,
            "content": self.content[:500],
            "url": self.url,
            "author": self.author,
            "metrics": self.metrics,
            "fetched_at": self.fetched_at,
        }


class PlatformRegistry:
    """13 平台注册"""

    def __init__(self):
        self.platforms: Dict[Platform, Dict[str, Any]] = {}
        self._register_defaults()

    def _register_defaults(self):
        configs = {
            Platform.XIAOHONGSHU: {
                "name_cn": "小红书",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/xiaohongshu/hot",
                    DataCategory.KEYWORD: "/xiaohongshu/search",
                    DataCategory.POST_DETAIL: "/xiaohongshu/note/{id}",
                    DataCategory.ACCOUNT_INFO: "/xiaohongshu/user/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD, DataCategory.POST_DETAIL, DataCategory.ACCOUNT_INFO],
                "rate_limit": "10/min",
                "auth_required": False,
                "compliance": "公开数据, 无需登录",
            },
            Platform.DOUYIN: {
                "name_cn": "抖音",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/douyin/hot",
                    DataCategory.KEYWORD: "/douyin/search",
                    DataCategory.POST_DETAIL: "/douyin/video/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD, DataCategory.POST_DETAIL],
                "rate_limit": "10/min",
                "auth_required": False,
                "compliance": "公开数据, 无需登录",
            },
            Platform.WECHAT_OFFICIAL: {
                "name_cn": "公众号",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/wechat/hot_articles",
                    DataCategory.ACCOUNT_INFO: "/wechat/account/{id}",
                    DataCategory.POST_DETAIL: "/wechat/article/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.ACCOUNT_INFO, DataCategory.POST_DETAIL],
                "rate_limit": "5/min",
                "auth_required": False,
                "compliance": "公开数据, 无需登录",
            },
            Platform.TIKTOK: {
                "name_cn": "TikTok",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/tiktok/hot",
                    DataCategory.KEYWORD: "/tiktok/search",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD],
                "rate_limit": "5/min",
                "auth_required": False,
                "compliance": "公开数据",
            },
            Platform.BILIBILI: {
                "name_cn": "B站",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/bilibili/hot",
                    DataCategory.KEYWORD: "/bilibili/search",
                    DataCategory.POST_DETAIL: "/bilibili/video/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD, DataCategory.POST_DETAIL],
                "rate_limit": "10/min",
                "auth_required": False,
                "compliance": "公开数据",
            },
            Platform.WEIBO: {
                "name_cn": "微博",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/weibo/hot",
                    DataCategory.KEYWORD: "/weibo/search",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD],
                "rate_limit": "10/min",
                "auth_required": False,
                "compliance": "公开数据",
            },
            Platform.ZHIHU: {
                "name_cn": "知乎",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/zhihu/hot",
                    DataCategory.KEYWORD: "/zhihu/search",
                    DataCategory.POST_DETAIL: "/zhihu/question/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD, DataCategory.POST_DETAIL],
                "rate_limit": "10/min",
                "auth_required": False,
            },
            Platform.DOUBAN: {
                "name_cn": "豆瓣",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/douban/hot",
                    DataCategory.POST_DETAIL: "/douban/movie/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.POST_DETAIL],
                "rate_limit": "10/min",
            },
            Platform.TWITTER: {
                "name_cn": "X (Twitter)",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/x/trending",
                    DataCategory.KEYWORD: "/x/search",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD],
                "rate_limit": "5/min",
            },
            Platform.YOUTUBE: {
                "name_cn": "YouTube",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/youtube/trending",
                    DataCategory.KEYWORD: "/youtube/search",
                    DataCategory.POST_DETAIL: "/youtube/video/{id}",
                },
                "supported_categories": [DataCategory.HOT_TOPIC, DataCategory.KEYWORD, DataCategory.POST_DETAIL],
                "rate_limit": "10/min",
            },
            Platform.KUAISHOU: {
                "name_cn": "快手",
                "endpoints": {
                    DataCategory.HOT_TOPIC: "/kuaishou/hot",
                },
                "supported_categories": [DataCategory.HOT_TOPIC],
                "rate_limit": "5/min",
            },
            Platform.AI_SEARCH: {
                "name_cn": "AI 搜索聚合",
                "endpoints": {
                    DataCategory.KEYWORD: "/ai_search",
                    DataCategory.HOT_TOPIC: "/ai_search/hot",
                },
                "supported_categories": [DataCategory.KEYWORD, DataCategory.HOT_TOPIC],
                "rate_limit": "20/min",
            },
        }
        for p, conf in configs.items():
            self.platforms[p] = conf

    def get(self, platform: Platform) -> Optional[Dict[str, Any]]:
        return self.platforms.get(platform)

    def list(self) -> List[Platform]:
        return list(self.platforms.keys())

    def supports(self, platform: Platform, category: DataCategory) -> bool:
        conf = self.platforms.get(platform)
        if not conf:
            return False
        return category in conf.get("supported_categories", [])

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_platforms": len(self.platforms),
            "by_category": {c.value: sum(1 for p, conf in self.platforms.items() if c in conf.get("supported_categories", [])) for c in DataCategory},
        }


platform_registry = PlatformRegistry()


@dataclass
class DataGatewayConfig:
    """Data Gateway 配置"""

    api_key: str = ""
    base_url: str = "https://api.redfox.hk/v1"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    cost_per_call: float = 0.02
    user_id: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)


class DataGatewayClient:
    """RedFox Data Gateway Client

    13 平台统一接入 — 一个 API Key 通全网
    """

    def __init__(self, config: Optional[DataGatewayConfig] = None):
        self.config = config or DataGatewayConfig(
            api_key=os.getenv("REDFOX_API_KEY", ""),
        )
        self.metrics: Dict[str, Any] = {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "total_cost": 0.0,
            "by_platform": {p.value: 0 for p in Platform},
        }
        self._cache: Dict[str, List[DataItem]] = {}

    async def fetch_hot_topics(
        self,
        platform: Platform,
        max_results: int = 20,
    ) -> List[DataItem]:
        """获取热门话题"""
        if not platform_registry.supports(platform, DataCategory.HOT_TOPIC):
            raise ValueError(f"{platform.value} 不支持 HOT_TOPIC")
        cache_key = f"hot:{platform.value}:{max_results}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        # 实际请求 (真实环境: HTTP 调用)
        items = await self._call_api(
            platform=platform,
            category=DataCategory.HOT_TOPIC,
            params={"max": max_results},
        )
        self._cache[cache_key] = items
        return items

    async def search_keyword(
        self,
        platform: Platform,
        keyword: str,
        max_results: int = 20,
    ) -> List[DataItem]:
        """关键词搜索"""
        if not platform_registry.supports(platform, DataCategory.KEYWORD):
            raise ValueError(f"{platform.value} 不支持 KEYWORD")
        cache_key = f"kw:{platform.value}:{keyword}:{max_results}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        items = await self._call_api(
            platform=platform,
            category=DataCategory.KEYWORD,
            params={"q": keyword, "max": max_results},
        )
        self._cache[cache_key] = items
        return items

    async def fetch_post_detail(
        self,
        platform: Platform,
        post_id: str,
    ) -> Optional[DataItem]:
        """获取帖子详情"""
        if not platform_registry.supports(platform, DataCategory.POST_DETAIL):
            raise ValueError(f"{platform.value} 不支持 POST_DETAIL")
        items = await self._call_api(
            platform=platform,
            category=DataCategory.POST_DETAIL,
            params={"id": post_id},
        )
        return items[0] if items else None

    async def fetch_account_info(
        self,
        platform: Platform,
        account_id: str,
    ) -> Optional[DataItem]:
        """获取账号信息"""
        if not platform_registry.supports(platform, DataCategory.ACCOUNT_INFO):
            raise ValueError(f"{platform.value} 不支持 ACCOUNT_INFO")
        items = await self._call_api(
            platform=platform,
            category=DataCategory.ACCOUNT_INFO,
            params={"id": account_id},
        )
        return items[0] if items else None

    async def _call_api(
        self,
        platform: Platform,
        category: DataCategory,
        params: Dict[str, Any],
    ) -> List[DataItem]:
        """统一 API 调用 (stub: 启发式生成演示数据)"""
        self.metrics["total_calls"] += 1
        self.metrics["by_platform"][platform.value] += 1
        try:
            # 真实环境: httpx.AsyncClient().get(...)
            await asyncio.sleep(0.01)
            # 启发式生成
            items: List[DataItem] = []
            max_results = params.get("max", 20)
            for i in range(max_results):
                items.append(
                    DataItem(
                        platform=platform,
                        category=category,
                        title=f"{platform.value} 热门 #{i+1}",
                        content=f"这是一条来自 {platform.value} 的 {category.value} 内容...",
                        url=f"https://{platform.value}.com/post/{i}",
                        author=f"user_{i}",
                        metrics={
                            "views": (max_results - i) * 1000,
                            "likes": (max_results - i) * 100,
                            "comments": (max_results - i) * 10,
                        },
                        fetched_at=time.time(),
                        metadata=params,
                    )
                )
            self.metrics["success_calls"] += 1
            self.metrics["total_cost"] += self.config.cost_per_call
            return items
        except Exception as e:
            self.metrics["failed_calls"] += 1
            logger.warning(f"DataGateway call failed: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.metrics,
            "cache_size": len(self._cache),
            "platform_registry": platform_registry.get_stats(),
            "user_id": self.config.user_id,
        }


data_gateway = DataGatewayClient()
