"""conftest.py — shared helpers for china_social tests.

Provides:
    - _run(coro)        同步运行 async coroutine (兼容已存在 event loop)
    - _mock_transport(handler)  把 handler 函数包装成 httpx.MockTransport
    - sample fixtures for each channel (HTML / JSON payloads)
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Callable, Dict

import httpx

# 让 tests 不依赖 conftest discovery — 直接 import 时也能用
_THIS = os.path.dirname(os.path.abspath(__file__))
_CHINA_SOCIAL = os.path.dirname(_THIS)
_CHANNELS = os.path.dirname(_CHINA_SOCIAL)
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_CHANNELS))))
for p in (_BACKEND, _CHANNELS, _CHINA_SOCIAL):
    if p not in sys.path:
        sys.path.insert(0, p)


def _run(coro):
    """Run coroutine and return result, even if there's already a loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, coro)
                return fut.result(timeout=60)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _mock_transport(handler: Callable[[httpx.Request], httpx.Response]
                    ) -> httpx.MockTransport:
    """Wrap a request handler into a MockTransport."""
    return httpx.MockTransport(handler)


# ============================================================
# Sample payloads
# ============================================================

WECHAT_HTML = """
<html><body>
<ul class="news-list">
  <li class="news-list__item">
    <div class="txt-box">
      <a href="/link?url=https%3A%2F%2Fmp.weixin.qq.com%2Fs%2Fabc123&k=xxx" target="_blank">
        AI 大模型最新进展深度解读
      </a>
      <p class="txt-info">本文深度分析了 2024 年 AI 大模型的最新技术进展...</p>
      <div class="s-p">
        <a class="account">机器之心</a>
        <span class="time">2天前</span>
      </div>
    </div>
    <div class="img-box">
      <img src="https://example.com/wx_thumb_1.jpg"/>
    </div>
  </li>
  <li class="news-list__item">
    <div class="txt-box">
      <a href="https://mp.weixin.qq.com/s/def456" target="_blank">
        Python 数据科学实战手册
      </a>
      <p class="txt-info">从零开始学习 Python 数据科学...</p>
      <div class="s-p">
        <a class="account">Python 开发者</a>
        <span class="time">5小时前</span>
      </div>
    </div>
  </li>
</ul>
</body></html>
"""

WEIBO_JSON = {
    "ok": 1,
    "data": {
        "cards": [
            {
                "card_type": 9,
                "mblog": {
                    "id": "4900000001",
                    "text": "<a>AI</a> 大模型时代来了！深度学习新进展",
                    "created_at": "Mon Jan 01 12:34:56 +0800 2024",
                    "user": {
                        "screen_name": "AI观察家",
                        "profile_image_url": "https://example.com/wb_avatar.jpg",
                        "verified": True,
                        "followers_count": 50000,
                    },
                    "page_info": {
                        "page_title": "AI 大模型时代深度报告",
                        "content1": "深度报告内容...",
                        "page_url": "https://media.weibo.cn/article?id=4900000001",
                    },
                },
            },
            {
                "card_type": 9,
                "mblog": {
                    "id": "4900000002",
                    "text": "Python 教程推荐",
                    "created_at": "Tue Jan 02 09:00:00 +0800 2024",
                    "user": {
                        "screen_name": "Python爱好者",
                        "profile_image_url": "https://example.com/wb_avatar2.jpg",
                        "verified": False,
                        "followers_count": 1200,
                    },
                    "page_info": {
                        "page_title": "Python 入门到精通",
                        "page_url": "https://media.weibo.cn/article?id=4900000002",
                    },
                },
            },
        ]
    },
}

DOUYIN_JSON = {
    "status_code": 0,
    "user_list": [
        {
            "user_info": {
                "uid": "100000001",
                "sec_uid": "MS4wLjABAAAAxxxx",
                "nickname": "美食探店达人",
                "signature": "探遍全国美食",
                "follower_count": 1234567,
                "aweme_count": 200,
                "avatar_thumb": {
                    "url_list": ["https://example.com/dy_avatar1.jpg"]
                },
                "share_info": {
                    "share_url": "https://www.douyin.com/user/MS4wLjABAAAAxxxx"
                },
                "enterprise_verify_reason": "",
            }
        },
        {
            "user_info": {
                "uid": "100000002",
                "sec_uid": "MS4wLjABAAAAyyyy",
                "nickname": "Python 编程教学",
                "signature": "每天学点 Python",
                "follower_count": 88888,
                "aweme_count": 150,
                "avatar_thumb": {
                    "url_list": ["https://example.com/dy_avatar2.jpg"]
                },
                "share_info": {
                    "share_url": "https://www.douyin.com/user/MS4wLjABAAAAyyyy"
                },
            }
        },
    ],
}

XIGUA_JSON = {
    "data": [
        {
            "title": "家常菜红烧肉教程",
            "abstract": "从选材到出锅完整教学",
            "video_id": "7000000001",
            "video_url": "https://www.ixigua.com/7000000001",
            "user": {"name": "厨房日记"},
            "play_count": 12345,
            "duration": 320,
            "publish_time": "2024-01-01",
            "poster_url": "https://example.com/xg_poster1.jpg",
        },
        {
            "title": "Python 数据可视化",
            "abstract": "matplotlib + seaborn 全攻略",
            "video_id": "7000000002",
            "video_url": "https://www.ixigua.com/7000000002",
            "user": {"name": "数据科学家"},
            "play_count": 9999,
            "duration": 600,
            "publish_time": "2024-02-01",
            "poster_url": "https://example.com/xg_poster2.jpg",
        },
    ],
}

BILIBILI_JSON = {
    "code": 0,
    "message": "0",
    "ttl": 1,
    "data": {
        "result": [
            {
                "mid": 12345,
                "uname": "Python 教程 UP 主",
                "usign": "专注 Python 教学 5 年",
                "level": 6,
                "fans": 100000,
                "videos": 200,
                "upic": "https://example.com/bili_avatar1.jpg",
                "room_id": 123456,
                "official_verify": {"type": 0, "desc": "知名 UP 主"},
            },
            {
                "mid": 67890,
                "uname": "AI 科技前沿",
                "usign": "AI 行业观察",
                "level": 5,
                "fans": 50000,
                "videos": 80,
                "upic": "https://example.com/bili_avatar2.jpg",
                "room_id": 0,
                "official_verify": {"type": -1, "desc": ""},
            },
        ],
        "numResults": 2,
        "pages": 1,
    },
}