"""Social crawler channel registry.

Six public social-search channels are exposed here for crawler orchestration:
Weibo, Douyin, Bilibili, Xiaohongshu, Zhihu, and Baidu Tieba.
"""
from __future__ import annotations

from .bilibili import BilibiliChannel
from .douyin import DouyinChannel
from .tieba import TiebaChannel
from .weibo import WeiboChannel
from .xiaohongshu import XiaohongshuChannel
from .zhihu import ZhihuChannel

SOCIAL_CHANNEL_REGISTRY = {
    "weibo": WeiboChannel,
    "douyin": DouyinChannel,
    "bilibili": BilibiliChannel,
    "xiaohongshu": XiaohongshuChannel,
    "zhihu": ZhihuChannel,
    "tieba": TiebaChannel,
}

__all__ = [
    "BilibiliChannel",
    "DouyinChannel",
    "TiebaChannel",
    "WeiboChannel",
    "XiaohongshuChannel",
    "ZhihuChannel",
    "SOCIAL_CHANNEL_REGISTRY",
]
