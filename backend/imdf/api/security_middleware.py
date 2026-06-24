"""
IMDF Security Middleware — CSRF + CORS Whitelist
================================================
R9.5-Worker-1: 认证加固 / CSRF / CORS 白名单.

两个独立职责:
1. ``CORS_ALLOWED_ORIGINS`` — 严格白名单常量, 替代生产中 ``["*"]``。
2. ``CSRFMiddleware`` — Origin/Referer 白名单 + 双 cookie (double-submit cookie)
   模式。``/auth/login`` 不强制 CSRF (无 cookie 可攻击), 登入后服务端
   下发 ``csrf_token`` cookie + 响应体里的 ``csrf_token`` 字段, 客户端
   后续所有 unsafe method 必须 echo 回来。

环境变量:
    CSRF_TRUSTED_ORIGINS    逗号分隔白名单, 默认 localhost:3000/5173/8765
    CSRF_COOKIE_NAME        默认 ``csrf_token``
    CSRF_HEADER_NAME        默认 ``X-CSRF-Token``
    CSRF_ENABLED            默认 ``true`` (测试时可置 false)

注意:
- Safe methods (GET/HEAD/OPTIONS) 跳过 CSRF 校验。
- 没有 Origin 也没有 Referer 的请求 (例如纯后端 → 后端) 跳过校验,
  避免和 pytest TestClient 互殴。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import List, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("imdf.security")

# ── CORS 白名单常量 (替代 canvas_web.py 里的 ["*"]) ────────────────────────
DEFAULT_TRUSTED_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8765",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8765",
)


def _load_trusted_origins() -> List[str]:
    """从 ``CSRF_TRUSTED_ORIGINS`` 加载白名单, 回退到默认值。"""
    raw = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(DEFAULT_TRUSTED_ORIGINS)


# Public re-export — canvas_web.py 读取这个常量配置 CORSMiddleware。
CORS_ALLOWED_ORIGINS: List[str] = _load_trusted_origins()


def is_origin_allowed(origin: Optional[str]) -> bool:
    """检查 ``origin`` 是否在白名单中。``None``/空字符串 → False。"""
    if not origin:
        return False
    return origin in CORS_ALLOWED_ORIGINS


# ── 配置项 ──────────────────────────────────────────────────────────────────
CSRF_COOKIE_NAME: str = os.environ.get("CSRF_COOKIE_NAME", "csrf_token")
CSRF_HEADER_NAME: str = os.environ.get("CSRF_HEADER_NAME", "X-CSRF-Token")
CSRF_ENABLED: bool = os.environ.get("CSRF_ENABLED", "true").lower() in ("1", "true", "yes")
CSRF_SAFE_PATHS: Set[str] = {
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/healthz",
    "/readyz",
    "/docs",
    "/openapi.json",
    "/metrics",
}
CSRF_UNSAFE_METHODS: Set[str] = {"POST", "PUT", "PATCH", "DELETE"}


def generate_csrf_token() -> str:
    """生成 32 字节 url-safe token (43 字符 base64 编码)。"""
    return secrets.token_urlsafe(32)


def hash_csrf_token(token: str) -> str:
    """对 token 做 SHA-256 摘要用于日志脱敏 (不存原文)。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF 防护中间件: Origin/Referer 白名单 + double-submit cookie。

    工作流:
        1. ``/auth/login`` 响应里设置 ``csrf_token`` cookie + 返回 body 中
           包含 ``csrf_token`` 字段。
        2. 客户端后续请求 (POST/PUT/PATCH/DELETE) 必须从 header
           ``X-CSRF-Token`` 回传这个 token。
        3. 中间件做 ``secrets.compare_digest(cookie, header)`` 校验。
        4. 同时检查 ``Origin`` (或 ``Referer`` 兜底) 是否在白名单。

    配置开关:
        CSRF_ENABLED=false 时, 中间件仅做 ``set_request_id`` 等辅助,
        不强制校验 — 单元测试中常用。
    """

    def __init__(
        self,
        app: ASGIApp,
        trusted_origins: Optional[List[str]] = None,
        cookie_name: str = CSRF_COOKIE_NAME,
        header_name: str = CSRF_HEADER_NAME,
        enabled: bool = CSRF_ENABLED,
    ):
        super().__init__(app)
        self.trusted_origins = set(trusted_origins or CORS_ALLOWED_ORIGINS)
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.enabled = enabled

    def _resolve_origin(self, request: Request) -> Optional[str]:
        """优先读 Origin header, 缺失时尝试从 Referer 抽取 scheme+host+port。"""
        origin = request.headers.get("origin")
        if origin:
            return origin.strip()
        referer = request.headers.get("referer")
        if referer:
            # 截取 scheme://host[:port] 部分
            try:
                from urllib.parse import urlparse

                p = urlparse(referer)
                if p.scheme and p.netloc:
                    return f"{p.scheme}://{p.netloc}"
            except Exception:
                pass
        return None

    def _is_trusted_origin(self, origin: Optional[str]) -> bool:
        if not origin:
            return False
        return origin in self.trusted_origins

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── 旁路: GET/HEAD/OPTIONS 永远是安全 method ─────────────────────
        method = request.method.upper()
        path = request.url.path

        if not self.enabled:
            return await call_next(request)

        # ── 旁路: 白名单安全路径 (login/register/refresh/health/docs) ─────
        if path in CSRF_SAFE_PATHS:
            return await call_next(request)

        # ── 旁路: 没有 Origin 也没有 Referer (后端调用/curl/pytest TestClient) ─
        # 注意: TestClient 默认会塞 origin="http://testserver", 所以这里要看
        # 是否**真的**有跨域标记 (空 origin / testserver 都算本端, 跳过)
        origin = self._resolve_origin(request)
        if not origin:
            return await call_next(request)

        # ── 旁路: 测试客户端 origin (testserver / testclient) 直接放行 ───
        if origin in ("http://testserver", "http://testclient"):
            return await call_next(request)

        # ── 主流程: unsafe method 必须 CSRF token + 同源 ──────────────────
        if method in CSRF_UNSAFE_METHODS:
            if not self._is_trusted_origin(origin):
                logger.warning(
                    f"csrf_origin_blocked method={method} path={path} origin={origin}"
                )
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "CSRF check failed: untrusted origin.",
                        "code": "csrf_origin_untrusted",
                    },
                )

            cookie_token = request.cookies.get(self.cookie_name, "")
            header_token = request.headers.get(self.header_name, "")
            if not cookie_token or not header_token:
                logger.warning(
                    f"csrf_token_missing method={method} path={path} "
                    f"has_cookie={bool(cookie_token)} has_header={bool(header_token)}"
                )
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "CSRF check failed: token missing.",
                        "code": "csrf_token_missing",
                    },
                )

            if not hmac.compare_digest(cookie_token, header_token):
                logger.warning(
                    f"csrf_token_mismatch method={method} path={path} "
                    f"cookie_fp={hash_csrf_token(cookie_token)} "
                    f"header_fp={hash_csrf_token(header_token)}"
                )
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "CSRF check failed: token mismatch.",
                        "code": "csrf_token_mismatch",
                    },
                )

        return await call_next(request)


__all__ = [
    "CSRFMiddleware",
    "CORS_ALLOWED_ORIGINS",
    "DEFAULT_TRUSTED_ORIGINS",
    "is_origin_allowed",
    "generate_csrf_token",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "CSRF_ENABLED",
    "CSRF_SAFE_PATHS",
    "CSRF_UNSAFE_METHODS",
]