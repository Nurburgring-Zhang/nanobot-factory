"""
Agent-Reach渠道集成适配器
=====================

本模块提供对Agent-Reach多平台渠道的集成支持，包括：
- Twitter/X (xreach CLI)
- Reddit
- YouTube
- GitHub
- Bilibili
- XiaoHongShu (小红书)
- Douyin (抖音)
- LinkedIn
- Boss直聘
- WeChat公众号
- RSS
- Web页面
- Exa搜索

作者：MiniMax Agent
日期：2026-03-05
"""

import asyncio
import subprocess
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ChannelResult:
    """渠道执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    raw_output: Optional[str] = None


class AgentReachChannel:
    """
    Agent-Reach渠道基类

    提供统一的渠道访问接口
    """

    def __init__(self, channel_name: str, config: Optional[Dict[str, Any]] = None):
        self.channel_name = channel_name
        self.config = config or {}
        self.enabled = False

    async def check_status(self) -> ChannelResult:
        """检查渠道状态"""
        try:
            result = subprocess.run(
                ["agent-reach", "doctor"],
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout + result.stderr
            enabled = self.channel_name in output and "✅" in output
            return ChannelResult(success=True, data={"enabled": enabled, "output": output})
        except Exception as e:
            return ChannelResult(success=False, error=str(e))

    async def configure(self, credentials: Dict[str, str]) -> ChannelResult:
        """配置渠道凭证"""
        raise NotImplementedError

    async def search(self, query: str, **kwargs) -> ChannelResult:
        """搜索内容"""
        raise NotImplementedError

    async def fetch(self, identifier: str, **kwargs) -> ChannelResult:
        """获取内容"""
        raise NotImplementedError


class TwitterChannel(AgentReachChannel):
    """Twitter/X渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("twitter", config)

    async def search(self, query: str, limit: int = 10) -> ChannelResult:
        """搜索推文"""
        try:
            cmd = ["xreach", "search", query, "--json", "-n", str(limit)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                data = json.loads(result.stdout) if result.stdout else []
                return ChannelResult(success=True, data=data, raw_output=result.stdout)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))

    async def configure(self, credentials: Dict[str, str]) -> ChannelResult:
        """配置Twitter凭证"""
        try:
            if "auth_token" in credentials and "ct0" in credentials:
                cookie = f"auth_token={credentials['auth_token']}; ct0={credentials['ct0']}"
                cmd = ["agent-reach", "configure", "twitter-cookies", cookie]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    self.enabled = True
                    return ChannelResult(success=True, data={"message": "Twitter配置成功"})
            return ChannelResult(success=False, error="缺少必需的凭证")
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class YouTubeChannel(AgentReachChannel):
    """YouTube渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("youtube", config)

    async def fetch_transcript(self, video_id: str) -> ChannelResult:
        """获取YouTube视频字幕"""
        try:
            cmd = ["yt-dlp", "--write-subs", "--write-auto-subs",
                   f"https://www.youtube.com/watch?v={video_id}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return ChannelResult(success=True, data={"video_id": video_id})
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))

    async def download(self, url: str, format: str = "mp4") -> ChannelResult:
        """下载YouTube视频"""
        try:
            cmd = ["yt-dlp", "-f", f"bestvideo[ext={format}]+bestaudio[ext=m4a]",
                   "-o", "/tmp/%(title)s.%(ext)s", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return ChannelResult(success=True, data={"url": url, "format": format})
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class GitHubChannel(AgentReachChannel):
    """GitHub渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("github", config)

    async def search_repos(self, query: str, limit: int = 10) -> ChannelResult:
        """搜索GitHub仓库"""
        try:
            cmd = ["gh", "search", "repos", query, "--limit", str(limit), "--json",
                   "name,description,url,stars"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout) if result.stdout else []
                return ChannelResult(success=True, data=data, raw_output=result.stdout)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))

    async def get_issues(self, owner: str, repo: str, state: str = "open") -> ChannelResult:
        """获取GitHub仓库问题"""
        try:
            cmd = ["gh", "issue", "list", "--repo", f"{owner}/{repo}",
                   "--state", state, "--json", "number,title,state,url"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout) if result.stdout else []
                return ChannelResult(success=True, data=data)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class BilibiliChannel(AgentReachChannel):
    """Bilibili渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("bilibili", config)

    async def search(self, query: str, limit: int = 10) -> ChannelResult:
        """搜索Bilibili视频"""
        try:
            # 使用bili个人品牌工具
            cmd = ["bili", "search", query, "-n", str(limit)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return ChannelResult(success=True, data=result.stdout, raw_output=result.stdout)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))

    async def download(self, bvid: str, format: str = "mp4") -> ChannelResult:
        """下载Bilibili视频"""
        try:
            cmd = ["bili", "download", bvid, "-o", "/tmp/"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return ChannelResult(success=True, data={"bvid": bvid})
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class XiaoHongShuChannel(AgentReachChannel):
    """小红书渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("xiaohongshu", config)

    async def search(self, query: str, limit: int = 10) -> ChannelResult:
        """搜索小红书内容"""
        try:
            # 使用xhs个人品牌工具
            cmd = ["xhs", "search", query, "-n", str(limit)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return ChannelResult(success=True, data=result.stdout)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class RSSChannel(AgentReachChannel):
    """RSS渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("rss", config)

    async def fetch(self, feed_url: str) -> ChannelResult:
        """获取RSS订阅内容"""
        try:
            cmd = ["feedparser", feed_url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout) if result.stdout else {}
                return ChannelResult(success=True, data=data)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class WebChannel(AgentReachChannel):
    """Web页面渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("web", config)

    async def fetch(self, url: str) -> ChannelResult:
        """获取网页内容"""
        try:
            cmd = ["curl", "-s", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return ChannelResult(success=True, data=result.stdout)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class ExaSearchChannel(AgentReachChannel):
    """Exa搜索引擎渠道"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("exa_search", config)

    async def search(self, query: str, limit: int = 10) -> ChannelResult:
        """使用Exa搜索"""
        try:
            cmd = ["exa-search", query, "--num-results", str(limit), "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                data = json.loads(result.stdout) if result.stdout else []
                return ChannelResult(success=True, data=data)
            return ChannelResult(success=False, error=result.stderr)
        except Exception as e:
            return ChannelResult(success=False, error=str(e))


class ChannelFactory:
    """渠道工厂类"""

    _channels = {
        "twitter": TwitterChannel,
        "youtube": YouTubeChannel,
        "github": GitHubChannel,
        "bilibili": BilibiliChannel,
        "xiaohongshu": XiaoHongShuChannel,
        "rss": RSSChannel,
        "web": WebChannel,
        "exa_search": ExaSearchChannel,
    }

    @classmethod
    def create_channel(cls, channel_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[AgentReachChannel]:
        """创建渠道实例"""
        channel_class = cls._channels.get(channel_name)
        if channel_class:
            return channel_class(config)
        logger.warning(f"未知的渠道: {channel_name}")
        return None

    @classmethod
    def get_available_channels(cls) -> List[str]:
        """获取可用渠道列表"""
        return list(cls._channels.keys())


# 导出模块
__all__ = [
    "AgentReachChannel",
    "TwitterChannel",
    "YouTubeChannel",
    "GitHubChannel",
    "BilibiliChannel",
    "XiaoHongShuChannel",
    "RSSChannel",
    "WebChannel",
    "ExaSearchChannel",
    "ChannelFactory",
    "ChannelResult",
]
