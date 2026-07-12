"""CrawlerConfig — 统一爬虫配置 (P19-B3 §2)

覆盖:
- Auth (Bearer / API Key / OAuth2 client_credentials)
- Proxy (socks5 / http)
- RateLimit (RPS + burst + jitter)
- Robots.txt policy (honor / warn / ignore)
- UserAgent pool 注入
- Audit chain 开关
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"


class ProxyScheme(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class RobotsPolicy(str, Enum):
    """robots.txt 处理策略"""
    HONOR = "honor"          # 严格遵守 — disallowed 直接 skip
    WARN = "warn"            # 警告, 仍抓
    IGNORE = "ignore"        # 完全忽略


@dataclass
class AuthConfig:
    """鉴权配置 — 支持 4 种主流模式"""
    auth_type: AuthType = AuthType.NONE
    # Bearer / API Key
    token: Optional[str] = None
    api_key: Optional[str] = None
    api_key_header: str = "X-API-Key"  # for API Key mode
    # Basic
    username: Optional[str] = None
    password: Optional[str] = None
    # OAuth2 client_credentials
    oauth_token_url: Optional[str] = None
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_scope: Optional[str] = None
    # Custom headers (覆盖默认)
    custom_headers: Dict[str, str] = field(default_factory=dict)

    def get_headers(self) -> Dict[str, str]:
        """根据 auth_type 生成实际 HTTP 头"""
        headers = dict(self.custom_headers)
        if self.auth_type == AuthType.BEARER and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.auth_type == AuthType.API_KEY and self.api_key:
            headers[self.api_key_header] = self.api_key
        elif self.auth_type == AuthType.BASIC and self.username:
            import base64
            cred = base64.b64encode(
                f"{self.username}:{self.password or ''}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = f"Basic {cred}"
        return headers


@dataclass
class ProxyConfig:
    """Proxy 池 — 单条或列表轮询"""
    scheme: ProxyScheme = ProxyScheme.HTTP
    host: str = "127.0.0.1"
    port: int = 8080
    username: Optional[str] = None
    password: Optional[str] = None
    # 多 proxy 池
    pool: List["ProxyConfig"] = field(default_factory=list)

    def __post_init__(self) -> None:
        # 接受 str 输入 — 转换为 ProxyScheme enum
        if isinstance(self.scheme, str):
            try:
                self.scheme = ProxyScheme(self.scheme.lower())
            except ValueError:
                self.scheme = ProxyScheme.HTTP
        # pool 中的元素若为 dict 也尝试转换
        coerced_pool = []
        for p in self.pool or []:
            if isinstance(p, dict):
                coerced_pool.append(ProxyConfig(**p))
            else:
                coerced_pool.append(p)
        self.pool = coerced_pool

    def get_url(self) -> str:
        """生成 requests/httpx 用的 proxy URL"""
        auth = ""
        if self.username:
            auth = f"{self.username}:{self.password or ''}@"
        return f"{self.scheme.value}://{auth}{self.host}:{self.port}"

    def pick_random(self) -> "ProxyConfig":
        """从 pool 随机选一条, 单条时返回 self"""
        if self.pool:
            return random.choice(self.pool)
        return self


@dataclass
class RateLimitConfig:
    """限速配置 — token bucket 简化版"""
    # RPS: requests per second, 默认 1.0
    rps: float = 1.0
    # 突发 (同一秒最多 N 个)
    burst: int = 5
    # 抖动 (随机延迟 0..jitter_seconds)
    jitter_seconds: float = 0.0
    # 单 host max concurrent
    max_concurrent_per_host: int = 4
    # 全局 max concurrent
    max_concurrent_global: int = 16
    # 失败后重试 (次)
    max_retries: int = 3
    # 重试基础 backoff (秒)
    retry_backoff_base: float = 1.5


@dataclass
class CrawlerConfig:
    """统一爬虫配置 — 所有 crawler 接受此 dataclass"""
    # ===== Identity =====
    name: str = "default"
    channel: str = "generic"  # 用于 audit chain path tag

    # ===== Network =====
    timeout_seconds: float = 30.0
    proxy: Optional[ProxyConfig] = None
    user_agent_pool: List[str] = field(default_factory=list)

    # ===== Auth =====
    auth: AuthConfig = field(default_factory=AuthConfig)

    # ===== Rate limiting =====
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    # ===== Compliance =====
    robots_policy: RobotsPolicy = RobotsPolicy.HONOR
    respect_referer: bool = True

    # ===== Persistence =====
    enable_audit_chain: bool = True
    enable_history_log: bool = True

    # ===== Concurrency =====
    max_concurrent: int = 8
    semaphore_acquire_timeout: float = 30.0

    # ===== Misc =====
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---------- Factory ----------

    @classmethod
    def from_env(cls, name: str = "default", channel: str = "generic",
                 **overrides: Any) -> "CrawlerConfig":
        """从环境变量构造 — 适用于渠道适配器"""
        cfg = cls(name=name, channel=channel)

        # 环境变量映射: CRAWLER_<CHANNEL>_<KEY>
        env_prefix = f"CRAWLER_{channel.upper()}_"
        for k, v in os.environ.items():
            if not k.startswith(env_prefix):
                continue
            key = k[len(env_prefix):].lower()
            if key == "timeout_seconds":
                cfg.timeout_seconds = float(v)
            elif key == "max_concurrent":
                cfg.max_concurrent = int(v)
            elif key == "rps":
                cfg.rate_limit.rps = float(v)
            elif key == "robots_policy":
                cfg.robots_policy = RobotsPolicy(v.lower())

        # 应用覆盖
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def get_user_agent(self) -> str:
        """从 pool 随机挑 UA, 空则用 default"""
        if self.user_agent_pool:
            return random.choice(self.user_agent_pool)
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def with_proxy(self, proxy: ProxyConfig) -> "CrawlerConfig":
        cfg = self.__class__(**self.__dict__)
        cfg.proxy = proxy
        return cfg

    def with_auth(self, auth: AuthConfig) -> "CrawlerConfig":
        cfg = self.__class__(**self.__dict__)
        cfg.auth = auth
        return cfg


# 内置 UA 池 — 12 条主流 UA, 随机轮询降低 fingerprint
USER_AGENT_POOL: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]


def make_default_config(channel: str = "generic") -> CrawlerConfig:
    """构造默认 CrawlerConfig — 用内置 UA 池"""
    return CrawlerConfig(
        name=channel,
        channel=channel,
        user_agent_pool=list(USER_AGENT_POOL),
    )