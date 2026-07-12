"""china_social package — 5 中国社交平台渠道 (P20-H).

5 channels:
    - wechatmp      微信公众号   (mp.weixin.qq.com / weixin.sogou.com mirror)
    - weibomp       微博号文章    (media.weibo.cn)
    - douyinmp      抖音号       (www.douyin.com/user)
    - xigua         西瓜视频      (www.ixigua.com)
    - bilibilimp    B 站 UP 主   (space.bilibili.com)

所有渠道遵循统一 contract:
    async def search(query: str, max_results: int = 20) -> List[CrawlResult]
    @staticmethod
    def parse(html: str) -> List[CrawlResult]

约束:
    - httpx async client (NOT requests)
    - Rate limit: 1 req/sec per channel (Token bucket)
    - robots.txt: 尊重 Disallow (若 robots 不可达 → 视为 allow)
    - 网络错误 → 返回 [] + 日志警告
    - 公开搜索接口 → 无需 API key
    - Pydantic v2 输入/输出模型

注意:
    这些平台反爬严苛 — 真实生产环境大概率需要登录态/cookie/proxy.
    本模块默认只用于 (a) 单元测试 MockTransport; (b) 离线数据采集.
    真实抓取失败是设计内行为 (return []) 而非 exception.
"""
from __future__ import annotations

import logging

from ._base import BaseCrawlerChannel, CrawlResult, CrawlSearchRequest
from .wechatmp import WechatMPChannel
from .weibomp import WeiboMPChannel
from .douyinmp import DouyinMPChannel
from .xigua import XiguaChannel
from .bilibilimp import BilibiliMPChannel

logger = logging.getLogger(__name__)


# Re-export 包级常量 — 给 `from imdf.crawler.channels.china_social import ...` 用
__all__ = [
    "BaseCrawlerChannel",
    "CrawlResult",
    "CrawlSearchRequest",
    "WechatMPChannel",
    "WeiboMPChannel",
    "DouyinMPChannel",
    "XiguaChannel",
    "BilibiliMPChannel",
    "get_channel_registry",
]


def get_channel_registry() -> dict:
    """返回 5 渠道的注册表 {channel_name: ChannelClass}.

    用于 dispatcher / factory / 监控面板.
    """
    return {
        "wechatmp": WechatMPChannel,
        "weibomp": WeiboMPChannel,
        "douyinmp": DouyinMPChannel,
        "xigua": XiguaChannel,
        "bilibilimp": BilibiliMPChannel,
    }