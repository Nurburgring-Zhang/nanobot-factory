"""Jobs 渠道适配器 (P20-B2)

4 公开 jobs 招聘网站:
    - LagouChannel       拉勾网 (www.lagou.com)
    - BossZhipinChannel  BOSS直聘 (www.zhipin.com)
    - ZhilianChannel     智联招聘 (www.zhaopin.com)
    - Job51Channel       前程无忧 (www.51job.com)

公共契约:
    class BaseCrawlerChannel(ABC)
        async search(query: str, max_results: int = 20) -> List[CrawlResult]
        @staticmethod parse(html: str) -> List[JobPosting]

每个渠道:
    - 默认走公开搜索端点 (无 key)
    - 限速 1 req/sec (可调)
    - 失败 → [] (不抛)
    - Pydantic v2 输出 JobPosting, 包成 CrawlResult
    - 真实 UA 池轮换 (4 个)
    - 尊重 robots.txt (默认关闭, 可开)
    - httpx.AsyncClient 支持注入 transport (测试用)

Usage:
    async with LagouChannel() as ch:
        results = await ch.search("Python 后端", max_results=10)
        for r in results:
            print(r.posting.title, r.posting.salary, r.posting.url)
"""
from __future__ import annotations

from ._base import (
    USER_AGENT_POOL,
    BaseCrawlerChannel,
    CrawlResult,
    JobPosting,
)
from .bosszhipin import BossZhipinChannel
from .job51 import Job51Channel
from .lagou import LagouChannel
from .zhilian import ZhilianChannel

__all__ = [
    "BaseCrawlerChannel",
    "CrawlResult",
    "JobPosting",
    "USER_AGENT_POOL",
    # 4 渠道
    "LagouChannel",
    "BossZhipinChannel",
    "ZhilianChannel",
    "Job51Channel",
    # Registry factory
    "get_channel",
    "list_channels",
    "CHANNEL_REGISTRY",
]


# ============================================================
# Registry — 渠道名 → 类
# ============================================================
CHANNEL_REGISTRY: dict = {
    "lagou": LagouChannel,
    "bosszhipin": BossZhipinChannel,
    "zhilian": ZhilianChannel,
    "job51": Job51Channel,
}


def get_channel(name: str, **kwargs) -> BaseCrawlerChannel:
    """工厂函数: 按名字获取 channel 实例.

    Args:
        name: 'lagou' / 'bosszhipin' / 'zhilian' / 'job51'
        **kwargs: 透传给渠道构造函数 (timeout, rate_limit_rps, transport 等)

    Raises:
        ValueError: 渠道名不存在
    """
    name = (name or "").lower().strip()
    cls = CHANNEL_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown jobs channel: {name!r}. "
            f"Available: {sorted(CHANNEL_REGISTRY.keys())}"
        )
    return cls(**kwargs)


def list_channels() -> list:
    """返回所有可用 channel 名."""
    return sorted(CHANNEL_REGISTRY.keys())
