"""APICrawler — REST / GraphQL API 拉取 (P19-B3 §4)

特性:
- REST: GET / POST / PUT / PATCH / DELETE, JSON / form / multipart
- GraphQL: query + variables
- 鉴权: Bearer / API Key / OAuth2 (client_credentials 自动刷新)
- 限速: 默认 1.0 RPS (token bucket)
- 自动分页: cursor / offset / page 参数
- 重试: 429 / 5xx 自动 backoff retry
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import BaseCrawler, CrawlResult, CrawlStatus
from .config import AuthConfig, AuthType, CrawlerConfig, RateLimitConfig

logger = logging.getLogger(__name__)


@dataclass
class PaginationConfig:
    """自动分页配置"""
    mode: str = "none"  # none / cursor / offset / page / link_header
    cursor_param: str = "cursor"
    cursor_response_path: str = "next_cursor"  # JSONPath 简化: 字典 key
    offset_param: str = "offset"
    page_param: str = "page"
    page_size_param: str = "limit"
    page_size: int = 50
    max_pages: int = 10
    link_header_rel: str = "next"


@dataclass
class APIResponse:
    """API 响应 — 标准化"""
    status_code: int
    body: Any  # dict / list / str
    headers: Dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


class APICrawler(BaseCrawler):
    """REST API 爬虫 — httpx (preferred) or urllib fallback

    支持:
    - Bearer / API Key / Basic / OAuth2 client_credentials
    - GET / POST / PUT / PATCH / DELETE
    - 自动分页 (cursor / offset / page)
    - 重试 (429 / 5xx backoff)
    """

    channel = "api"

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 http_client: Optional[Any] = None):
        super().__init__(config=config)
        # http_client: 测试用 mock, 生产用 httpx
        self._client = http_client
        self._owns_client = http_client is None
        self._oauth_token: Optional[str] = None
        self._oauth_token_expires_at: float = 0
        self._oauth_lock = threading.Lock()

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not _HTTPX_AVAILABLE:
            return None
        if self._owns_client and self._client is None:
            try:
                import httpx  # type: ignore
                self._client = httpx.Client(
                    timeout=self.config.timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": self.config.get_user_agent()},
                )
            except Exception as e:
                logger.warning("httpx init failed: %s", e)
                self._client = None
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    # ============== _prepare ==============

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """target 接受:
        - str URL (默认 GET)
        - dict: {url, method, params, body, json, headers, pagination}
        """
        if isinstance(target, str):
            target = {"url": target, "method": "GET"}
        if not isinstance(target, dict):
            return None
        url = target.get("url") or target.get("endpoint")
        if not url:
            return None

        return {
            "url": url,
            "method": target.get("method", "GET").upper(),
            "params": target.get("params", {}),
            "body": target.get("body"),
            "json_body": target.get("json"),
            "data": target.get("data"),
            "headers": target.get("headers", {}),
            "pagination": target.get("pagination", {"mode": "none"}),
            "graphql_query": target.get("graphql_query"),
            "graphql_variables": target.get("graphql_variables", {}),
            "max_pages": int(target.get("max_pages", 10)),
        }

    # ============== _do_fetch ==============

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        """Fetch — 含 OAuth2 自动刷新 / 分页 / 重试"""
        method = prep.get("method", "GET")
        params = dict(prep.get("params") or {})
        body = prep.get("body")
        json_body = prep.get("json_body")
        data = prep.get("data")
        pagination = prep.get("pagination") or {"mode": "none"}
        max_pages = int(prep.get("max_pages", 10))

        # OAuth2 自动刷新
        auth_headers = self._maybe_refresh_oauth()
        for k, v in auth_headers.items():
            headers.setdefault(k, v)

        all_items: List[Any] = []
        last_status = 0
        last_error: Optional[str] = None
        combined_meta: Dict[str, Any] = {
            "pages_fetched": 0,
            "method": method,
            "pagination_mode": pagination.get("mode", "none"),
        }

        cursor = None
        offset = 0
        page_num = 1

        for page_idx in range(max_pages):
            # 构造本轮 URL/params
            req_headers = dict(headers)
            req_params = dict(params)
            req_body = body
            req_json = json_body

            mode = pagination.get("mode", "none")
            if mode == "cursor" and cursor:
                req_params[pagination.get("cursor_param", "cursor")] = cursor
            elif mode == "offset" and offset > 0:
                req_params[pagination.get("offset_param", "offset")] = offset
            elif mode == "page" and page_num > 1:
                req_params[pagination.get("page_param", "page")] = page_num
                if pagination.get("page_size"):
                    req_params[pagination.get("page_size_param", "limit")] = pagination.get("page_size")

            # GraphQL 走 POST
            if prep.get("graphql_query"):
                method = "POST"
                req_json = {
                    "query": prep["graphql_query"],
                    "variables": prep.get("graphql_variables", {}),
                }
                req_headers.setdefault("Content-Type", "application/json")

            # 重试
            for attempt in range(self.config.rate_limit.max_retries + 1):
                try:
                    resp = self._execute(method, url, req_headers, req_params,
                                          req_body, req_json, data)
                    last_status = resp.status_code
                    if resp.status_code == 429 or 500 <= resp.status_code < 600:
                        # 重试
                        if attempt < self.config.rate_limit.max_retries:
                            backoff = self.config.rate_limit.retry_backoff_base * (2 ** attempt)
                            logger.debug("retry %d after %.1fs (status=%d)", attempt, backoff, resp.status_code)
                            time.sleep(backoff)
                            continue
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)
                    if attempt < self.config.rate_limit.max_retries:
                        backoff = self.config.rate_limit.retry_backoff_base * (2 ** attempt)
                        time.sleep(backoff)
                        continue
                    return None, last_status or 0, last_error

            if last_error:
                return None, last_status, last_error

            # 4xx/5xx 非 200 系列视为错误 (除非 pagination 模式下期待 envelope error)
            if not (200 <= last_status < 300):
                # 但仍然 try parse body 给 caller 用
                try:
                    body_obj = resp.json() if hasattr(resp, "json") else json.loads(resp.text)
                except Exception:
                    body_obj = getattr(resp, "text", "")
                return {"items": [], "meta": {"pages_fetched": 0, "last_status": last_status,
                                                "error_body": body_obj},
                        "last_status": last_status}, last_status, f"HTTP {last_status}"

            # 处理响应
            try:
                body_obj = resp.json() if hasattr(resp, "json") else json.loads(resp.text)
            except Exception:
                body_obj = getattr(resp, "text", "")

            # 提取 items
            items_this_page, next_cursor = self._extract_items(body_obj, pagination)
            all_items.extend(items_this_page)
            combined_meta["pages_fetched"] += 1

            # 决定是否继续翻页
            if mode == "none":
                break
            if mode == "cursor":
                if not next_cursor:
                    break
                cursor = next_cursor
            elif mode == "offset":
                if not items_this_page:
                    break
                # If we got fewer than expected, stop (last page)
                expected = pagination.get("page_size", 50)
                if len(items_this_page) < expected:
                    break
                offset += expected
            elif mode == "page":
                if not items_this_page or len(items_this_page) < pagination.get("page_size", 50):
                    break
                page_num += 1
            elif mode == "link_header":
                link = resp.headers.get("Link", "")
                next_url = self._parse_link_header(link, pagination.get("link_header_rel", "next"))
                if not next_url:
                    break
                url = next_url  # next iteration 改 URL
            else:
                break

        combined_meta["items_count"] = len(all_items)
        return {"items": all_items, "meta": combined_meta, "last_status": last_status}, last_status, None

    def _execute(self, method: str, url: str, headers: Dict[str, str],
                 params: Optional[Dict], body: Optional[Any],
                 json_body: Optional[Dict], data: Optional[Any]) -> Any:
        """实际 HTTP 执行 — httpx (preferred) or urllib"""
        client = self._get_client()
        if client is not None:
            kwargs = {"headers": headers, "params": params}
            if json_body is not None:
                kwargs["json"] = json_body
            elif data is not None:
                kwargs["data"] = data
            elif body is not None:
                kwargs["content"] = body if isinstance(body, (bytes, str)) else json.dumps(body)
            return client.request(method, url, **kwargs)

        # urllib fallback
        import urllib.request
        import urllib.parse
        if params:
            sep = "&" if "?" in url else "?"
            url = url + sep + urllib.parse.urlencode(params, doseq=True)
        data_bytes: Optional[bytes] = None
        if json_body is not None:
            data_bytes = json.dumps(json_body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            data_bytes = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif body is not None:
            data_bytes = body.encode("utf-8") if isinstance(body, str) else body

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                content = resp.read()
                class _R:
                    def __init__(self):
                        self.status_code = resp.status
                        self.headers = dict(resp.headers)
                        self.text = content.decode("utf-8", errors="replace")
                    def json(self):
                        return json.loads(self.text)
                return _R()
        except Exception as e:
            raise RuntimeError(f"urllib error: {e}")

    def _extract_items(self, body: Any, pagination: Dict[str, Any]) -> Tuple[List[Any], Optional[str]]:
        """从响应中提取 items 数组 + 下一 cursor"""
        if isinstance(body, list):
            return body, None
        if isinstance(body, dict):
            # data_path (如 "data.items")
            data_path = pagination.get("data_path") or pagination.get("response_path")
            if data_path:
                items = self._dig_path(body, data_path)
            else:
                # 常见字段名
                for key in ("items", "data", "results", "records", "rows"):
                    if key in body and isinstance(body[key], list):
                        items = body[key]
                        break
                else:
                    items = [body]
            # cursor
            cursor = None
            cursor_path = pagination.get("cursor_response_path")
            if cursor_path:
                cursor = self._dig_path(body, cursor_path)
            return items if isinstance(items, list) else [items], cursor
        return [body], None

    def _dig_path(self, obj: Any, path: str) -> Any:
        """简化 JSONPath — 'a.b.c' 字典嵌套."""
        for key in path.split("."):
            if isinstance(obj, dict):
                obj = obj.get(key)
            elif isinstance(obj, list) and key.isdigit():
                idx = int(key)
                obj = obj[idx] if 0 <= idx < len(obj) else None
            else:
                return None
        return obj

    def _parse_link_header(self, link: str, rel: str) -> Optional[str]:
        """Parse Link header (RFC 5988) — '<url>; rel="next"'"""
        if not link:
            return None
        import re
        for part in link.split(","):
            m = re.search(r'<([^>]+)>\s*;\s*rel="?([^",]+)"?', part.strip())
            if m and m.group(2) == rel:
                return m.group(1)
        return None

    # ============== _parse ==============

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """raw = {"items": [...], "meta": {...}, "last_status": N}"""
        if not isinstance(raw, dict):
            return [], {"error": "raw not dict"}
        items = raw.get("items") or []
        meta = raw.get("meta") or {}
        meta["last_status"] = raw.get("last_status", 0)
        # 标准化 items 为 dict
        normalized: List[Dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict):
                normalized.append(it)
            else:
                normalized.append({"value": it})
        return normalized, meta

    # ============== OAuth2 ==============

    def _maybe_refresh_oauth(self) -> Dict[str, str]:
        """OAuth2 client_credentials — token 快过期时刷新"""
        auth = self.config.auth
        if auth.auth_type != AuthType.OAUTH2:
            return {}
        if not auth.oauth_token_url or not auth.oauth_client_id:
            return {}
        with self._oauth_lock:
            now = time.time()
            if self._oauth_token and now < self._oauth_token_expires_at - 30:
                return {"Authorization": f"Bearer {self._oauth_token}"}
            # 刷新
            try:
                import urllib.request
                import urllib.parse
                data = urllib.parse.urlencode({
                    "grant_type": "client_credentials",
                    "client_id": auth.oauth_client_id,
                    "client_secret": auth.oauth_client_secret or "",
                    "scope": auth.oauth_scope or "",
                }).encode("utf-8")
                req = urllib.request.Request(
                    auth.oauth_token_url, data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                self._oauth_token = body.get("access_token")
                expires_in = int(body.get("expires_in", 3600))
                self._oauth_token_expires_at = now + expires_in
                if self._oauth_token:
                    return {"Authorization": f"Bearer {self._oauth_token}"}
            except Exception as e:
                logger.warning("OAuth2 refresh failed: %s", e)
        return {}


# GraphQL 专用子类 — 简化调用
class GraphQLCrawler(APICrawler):
    """GraphQL 专用 — 构造 query 包装为 POST 请求"""

    channel = "graphql"

    def crawl_query(self, endpoint: str, query: str,
                    variables: Optional[Dict[str, Any]] = None,
                    **kwargs: Any) -> CrawlResult:
        """直接调用 GraphQL query"""
        target = {
            "url": endpoint,
            "method": "POST",
            "graphql_query": query,
            "graphql_variables": variables or {},
            **kwargs,
        }
        return self.crawl(target)


# httpx optional availability
try:
    import httpx  # type: ignore
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False