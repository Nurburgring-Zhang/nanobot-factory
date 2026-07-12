"""11 个自媒体平台客户端 — 注册到 PLATFORMS dict (registry.py)."""
from .wechat_mp import WeChatMPClient
from .weibo import WeiboClient
from .douyin import DouyinClient
from .xiaohongshu import XiaohongshuClient
from .bilibili import BilibiliClient

__all__ = [
    "WeChatMPClient",
    "WeiboClient",
    "DouyinClient",
    "XiaohongshuClient",
    "BilibiliClient",
]