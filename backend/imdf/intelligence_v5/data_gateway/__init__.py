"""智影 V5 — Data Gateway 子包: 13 平台数据 API (RedFox)

迁移自 RedFox AI / Browse AI:
- 13 大平台: Amazon/Taobao/JD/Xiaohongshu/Douyin/Kuaishou/Meituan/Bilibili/Weibo/Zhihu/Reddit/X/LinkedIn
- 0.02 元/次, 一个 API Key 通全网
- 公开数据无登录, 私有数据需 cookie 上传
- 一次 SDK 调用 → 自动选择最佳平台 → 标准化返回
"""
from .client import (
    Platform,
    DataCategory,
    DataItem,
    PlatformRegistry,
    DataGatewayConfig,
    DataGatewayClient,
    platform_registry,
    data_gateway,
)

__all__ = [
    "Platform",
    "DataCategory",
    "DataItem",
    "PlatformRegistry",
    "DataGatewayConfig",
    "DataGatewayClient",
    "platform_registry",
    "data_gateway",
]
