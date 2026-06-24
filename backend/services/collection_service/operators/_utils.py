"""collection_service.operators._utils — shared helpers for collection operators.

Provides:
  - safe_get(url, params, timeout) — wraps httpx with try/except + offline detection
  - is_sandbox() — returns True if running in restricted env
  - mock_response(source, query, count, template) — deterministic mock builder
  - parse_url_host(url) — extract host
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def is_sandbox() -> bool:
    """Heuristic: sandbox if env flag set or no network test marker."""
    return os.environ.get("IMDF_SANDBOX_MODE", "1") == "1"


def safe_get(url: str, params: Optional[Dict[str, Any]] = None,
             timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Try httpx.get; return None on any failure (network, parse, etc.)."""
    try:
        import httpx
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, params=params or {})
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:  # noqa: BLE001
                return {"_raw": r.text[:8192], "_status": r.status_code}
        return {"_status": r.status_code, "_text": r.text[:1024]}
    except Exception:  # noqa: BLE001
        return None


def parse_url_host(url: str) -> str:
    try:
        return urlparse(url).netloc or ""
    except Exception:  # noqa: BLE001
        return ""


def deterministic_id(seed: str, prefix: str = "id") -> str:
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


def mock_response(source: str, query: str, count: int = 5,
                  kind: str = "item") -> List[Dict[str, Any]]:
    """Deterministic mock items: same query → same items."""
    seed_base = f"{source}:{query}"
    items: List[Dict[str, Any]] = []
    for i in range(count):
        sid = deterministic_id(f"{seed_base}:{i}", prefix=f"{source}.{kind}")
        items.append({
            "id": sid,
            "source": source,
            "title": f"[{source}] {query} #{i + 1}",
            "url": f"https://example.com/{source}/{sid}",
            "rank": i + 1,
            "score": round(1.0 - i * 0.1, 4),
        })
    return items


__all__ = ["is_sandbox", "safe_get", "parse_url_host", "deterministic_id", "mock_response"]
