"""Webhook URL 校验器 — 合法性 + SSRF 防护
================================

两阶段校验:
  1. **格式合法性** : 必须是 http:// 或 https://, 长度 ≤ 2048, 主机名合法
  2. **SSRF 防护**  : 拒绝内网 / 私网 / 链路本地 / 保留 IP, 拒绝 localhost / 0.0.0.0

错误信息中文化 + 含字段名 (G4)。
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = {"http", "https"}

# 拒绝的 hostname 字面值 (无 DNS 解析)
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",            # AWS / GCP / Azure metadata IP
})


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断 IP 是否私网 / 回环 / 链路本地 / 保留 / 多播。"""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_safely(hostname: str) -> Optional[ipaddress.ip_address]:
    """解析 hostname → IP, 失败返回 None。"""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return None
    if not infos:
        return None
    try:
        return ipaddress.ip_address(infos[0][4][0])
    except (ValueError, IndexError):
        return None


def validate_webhook_url(url: str, name: str = "url") -> str:
    """校验 Webhook URL — 合法格式 + 阻断 SSRF。

    参数:
        url:  待校验的 URL 字符串
        name: 字段名, 用于错误信息

    返回:
        校验通过时原样返回

    异常:
        HTTPException 400: 非法格式
        HTTPException 400: SSRF (私网/内网/保留 IP)
    """
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(400, f"{name} 不能为空")
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise HTTPException(400, f"{name} 长度 {len(url)} 超过 {MAX_URL_LENGTH}")

    try:
        parsed = urlparse(url)
    except ValueError as e:
        raise HTTPException(400, f"{name} 解析失败: {e}") from e

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(
            400,
            f"{name} scheme 非法: {parsed.scheme!r}, 应为 http/https",
        )
    if not parsed.hostname:
        raise HTTPException(400, f"{name} 缺少主机名: {url!r}")

    host = parsed.hostname.lower()

    # 1) 字面 hostname 黑名单
    if host in _BLOCKED_HOSTNAMES:
        raise HTTPException(400, f"{name} 主机 {host!r} 被禁用 (SSRF 防护)")

    # 2) IP 字面量 → 校验私网
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_private_ip(ip):
            raise HTTPException(400, f"{name} IP {host} 属于私网/回环/保留段 (SSRF 防护)")
        return url

    # 3) DNS 解析 → 解析到私网则拒
    resolved = _resolve_safely(host)
    if resolved is None:
        # DNS 解析失败, 但允许 (webhook 可能在创建时网络尚未通)
        # 严格模式下可改 raise
        return url
    if _is_private_ip(resolved):
        raise HTTPException(
            400,
            f"{name} 主机 {host!r} 解析到私网/回环 IP {resolved} (SSRF 防护)",
        )
    return url
