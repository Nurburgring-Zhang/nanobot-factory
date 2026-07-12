"""P21 R1 crawler audit v2 — instantiate each of 48 channels and call .search() / .list_datasets() / .crawl()
with mocked httpx / urllib transport. Categorize findings P0/P1/P2.

Read-only audit script — does NOT modify any source.
Outputs JSON findings to stdout for downstream categorization.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

BACKEND_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory\backend")
sys.path.insert(0, str(BACKEND_ROOT))

CHANNELS_ROOT = BACKEND_ROOT / "imdf" / "crawler" / "channels"


def discover_channels() -> List[Tuple[str, Path, str]]:
    out: List[Tuple[str, Path, str]] = []
    for py in sorted(CHANNELS_ROOT.rglob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        if "__pycache__" in str(py):
            continue
        # Skip test files inside test dirs
        rel = py.relative_to(CHANNELS_ROOT)
        parts = rel.parts
        # Skip if in __tests__ dir or named test_*
        if any("__tests__" in p or p.startswith("test_") for p in parts):
            continue
        subdir = parts[0] if len(parts) > 1 else "(root)"
        out.append((py.stem, py, subdir))
    return out


def find_crawler_class(mod: Any) -> List[type]:
    found = []
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if getattr(obj, "__module__", "") != mod.__name__:
            continue
        if name.endswith("Crawler") or name.endswith("Channel"):
            # Skip abstract base classes
            if getattr(obj, "__abstractmethods__", None):
                continue
            # Skip test classes
            if name.startswith("Test"):
                continue
            found.append(obj)
    return found


def make_async_transport(body: str, status: int = 200, ctype: str = "text/html"):
    """Build httpx.MockTransport with given response."""
    import httpx
    def handler(request):
        return httpx.Response(
            status_code=status,
            content=body.encode("utf-8"),
            headers={"content-type": ctype},
        )
    return httpx.MockTransport(handler)


def make_async_error_transport(exc):
    """Transport that raises the given exception."""
    import httpx
    def handler(request):
        raise exc
    return httpx.MockTransport(handler)


def make_sync_fetcher(body: bytes, status: int = 200):
    """Sync fetcher returning canned response."""
    def fetcher(url, headers, timeout):
        return body, status, None
    return fetcher


def make_sync_error_fetcher(err: str):
    def fetcher(url, headers, timeout):
        return b"", 0, err
    return fetcher


# ---------- Per-channel audit ----------
def audit_sync_channel(cls: type, name: str, subdir: str) -> Dict[str, Any]:
    """Sync ChannelCrawler pattern (top-level + code_oss)."""
    out = {"name": name, "subdir": subdir, "class": cls.__name__, "type": "sync", "issues": []}

    # Try mock=True first
    try:
        try:
            inst = cls(mock=True)
        except TypeError:
            try:
                inst = cls()
            except Exception as e:
                out["issues"].append({"level": "P0", "kind": "instantiation", "msg": f"cannot instantiate: {e}"})
                return out

        # Find entry method
        method_name = None
        for m in ("search", "search_request", "crawl"):
            if hasattr(inst, m) and callable(getattr(inst, m)):
                method_name = m
                break
        if not method_name:
            out["issues"].append({"level": "P0", "kind": "no_entry_method", "msg": "no search/search_request/crawl method"})
            return out
        out["entry"] = method_name

        target = {"query": "test_audit", "count": 3}
        try:
            method = getattr(inst, method_name)
            result = method(target)
            out["mock_call_ok"] = True
            out["mock_items_count"] = len(result.items) if hasattr(result, "items") else (len(result) if hasattr(result, "__len__") else -1)
        except Exception as e:
            out["issues"].append({"level": "P0", "kind": "mock_crash", "msg": f"mock call crashed: {type(e).__name__}: {e}"})

        # Inject fetcher (mock=False) with happy path
        try:
            happy_fetcher = make_sync_fetcher(b'{"items": [], "data": [], "results": []}', 200)
            try:
                inst2 = cls(mock=False, http_fetcher=happy_fetcher)
            except TypeError:
                try:
                    inst2 = cls(http_fetcher=happy_fetcher)
                except TypeError:
                    inst2 = cls()
            method2 = getattr(inst2, method_name)
            result2 = method2(target)
            if hasattr(result2, "items"):
                cnt = len(result2.items)
            else:
                cnt = len(result2) if hasattr(result2, "__len__") else -1
            out["injected_call_ok"] = True
            out["injected_items_count"] = cnt
        except Exception as e:
            out["issues"].append({"level": "P1", "kind": "injection_failure", "msg": f"http_fetcher injection failed: {type(e).__name__}: {e}"})

        # Empty response
        try:
            empty_fetcher = make_sync_fetcher(b"", 200)
            try:
                inst3 = cls(mock=False, http_fetcher=empty_fetcher)
            except TypeError:
                try:
                    inst3 = cls(http_fetcher=empty_fetcher)
                except TypeError:
                    inst3 = cls()
            method3 = getattr(inst3, method_name)
            result3 = method3(target)
        except Exception as e:
            out["issues"].append({"level": "P2", "kind": "empty_response", "msg": f"empty response crashed: {type(e).__name__}: {e}"})

        # Network error
        try:
            err_fetcher = make_sync_error_fetcher("simulated connection refused")
            try:
                inst4 = cls(mock=False, http_fetcher=err_fetcher)
            except TypeError:
                try:
                    inst4 = cls(http_fetcher=err_fetcher)
                except TypeError:
                    inst4 = cls()
            method4 = getattr(inst4, method_name)
            result4 = method4(target)
        except Exception as e:
            out["issues"].append({"level": "P1", "kind": "network_error_handling", "msg": f"network error crashed: {type(e).__name__}: {e}"})

        # Malformed response
        try:
            mal_fetcher = make_sync_fetcher(b"<not-valid>{{garbage[", 200)
            try:
                inst5 = cls(mock=False, http_fetcher=mal_fetcher)
            except TypeError:
                try:
                    inst5 = cls(http_fetcher=mal_fetcher)
                except TypeError:
                    inst5 = cls()
            method5 = getattr(inst5, method_name)
            result5 = method5(target)
        except Exception as e:
            out["issues"].append({"level": "P1", "kind": "malformed_response", "msg": f"malformed response crashed: {type(e).__name__}: {e}"})

        # Source-level checks
        try:
            src = inspect.getsource(cls)
            if "robots" not in src.lower() and "can_fetch" not in src.lower():
                out["issues"].append({"level": "P2", "kind": "no_robots_in_source", "msg": "no robots.txt mention in source"})
            if "license" not in src.lower() and "copyright" not in src.lower():
                out["issues"].append({"level": "P2", "kind": "no_copyright", "msg": "no license/copyright field"})
        except Exception:
            pass

    except Exception as e:
        out["issues"].append({"level": "P0", "kind": "unexpected", "msg": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[:300]})
    return out


def audit_async_channel(cls: type, name: str, subdir: str) -> Dict[str, Any]:
    """Async base channels (academic, china_social, datasets, jobs, social, storage)."""
    import httpx
    out = {"name": name, "subdir": subdir, "class": cls.__name__, "type": "async", "issues": []}

    # Find entry method name
    entry_method = None
    for m in ("search", "list_datasets"):
        if hasattr(cls, m) and callable(getattr(cls, m)):
            entry_method = m
            break
    if not entry_method:
        out["issues"].append({"level": "P0", "kind": "no_entry_method", "msg": "no async search/list_datasets method"})
        return out
    out["entry"] = entry_method

    # Happy path test
    async def _run_with_transport(body, status=200, ctype="text/html"):
        transport = make_async_transport(body, status=status, ctype=ctype)
        # Try (a) transport=, (b) client=
        try:
            inst = cls(transport=transport, timeout=5.0)
        except TypeError:
            try:
                client = httpx.AsyncClient(transport=transport, timeout=5.0)
                inst = cls(client=client, timeout=5.0)
            except TypeError:
                inst = cls(timeout=5.0)
        method = getattr(inst, entry_method)
        if asyncio.iscoroutinefunction(method):
            return await method("test", 3)
        else:
            # sync wrapper
            return method("test", 3)

    # Happy path
    happy_body = b'{"items": [], "data": [], "results": [], "datasets": []}'
    try:
        result = asyncio.run(_run_with_transport(happy_body, 200, "application/json"))
        out["mock_call_ok"] = True
        out["mock_items_count"] = len(result) if hasattr(result, "__len__") else -1
    except Exception as e:
        out["issues"].append({"level": "P0", "kind": "mock_crash", "msg": f"happy-path crashed: {type(e).__name__}: {e}"})

    # Empty body
    try:
        asyncio.run(_run_with_transport(b"", 200, "text/html"))
    except Exception as e:
        out["issues"].append({"level": "P2", "kind": "empty_response", "msg": f"empty body crashed: {type(e).__name__}: {e}"})

    # 5xx
    try:
        asyncio.run(_run_with_transport("server error", 500, "text/html"))
    except Exception as e:
        out["issues"].append({"level": "P1", "kind": "5xx_handling", "msg": f"5xx not handled gracefully: {type(e).__name__}: {e}"})

    # Network error
    try:
        async def _run_neterr():
            transport = make_async_error_transport(httpx.ConnectError("simulated connection refused"))
            try:
                inst = cls(transport=transport, timeout=5.0)
            except TypeError:
                try:
                    client = httpx.AsyncClient(transport=transport, timeout=5.0)
                    inst = cls(client=client, timeout=5.0)
                except TypeError:
                    inst = cls(timeout=5.0)
            method = getattr(inst, entry_method)
            if asyncio.iscoroutinefunction(method):
                return await method("test", 3)
            return method("test", 3)
        asyncio.run(_run_neterr())
    except Exception as e:
        out["issues"].append({"level": "P1", "kind": "network_error_handling", "msg": f"network error not handled gracefully: {type(e).__name__}: {e}"})

    # Malformed
    try:
        asyncio.run(_run_with_transport("<not-valid>{{garbage[", 200, "text/html"))
    except Exception as e:
        out["issues"].append({"level": "P1", "kind": "malformed_response", "msg": f"malformed response crashed: {type(e).__name__}: {e}"})

    # Source-level checks
    try:
        src = inspect.getsource(cls)
        if "robots" not in src.lower() and "can_fetch" not in src.lower() and "_robots" not in src.lower():
            out["issues"].append({"level": "P2", "kind": "no_robots_in_source", "msg": "no robots.txt mention in source"})
        if "license" not in src.lower() and "copyright" not in src.lower():
            out["issues"].append({"level": "P2", "kind": "no_copyright", "msg": "no license/copyright field"})
    except Exception:
        pass

    return out


def main():
    print("=" * 70, flush=True)
    print("P21 R1 crawler audit v2 — instantiating each channel", flush=True)
    print("=" * 70, flush=True)

    discovered = discover_channels()
    print(f"\nDiscovered {len(discovered)} channel files\n", flush=True)

    async_subdirs = {"academic", "china_social", "datasets", "jobs", "social", "storage"}
    results = []
    for name, path, subdir in discovered:
        rel = path.relative_to(BACKEND_ROOT)
        mod_path = ".".join(rel.with_suffix("").parts)
        try:
            mod = importlib.import_module(mod_path)
        except Exception as e:
            results.append({"name": name, "subdir": subdir, "class": "?", "type": "?", "issues": [
                {"level": "P0", "kind": "import", "msg": f"cannot import {mod_path}: {type(e).__name__}: {e}"}
            ]})
            print(f"  [IMPORT FAIL] {subdir}/{name}: {e}", flush=True)
            continue

        classes = find_crawler_class(mod)
        if not classes:
            results.append({"name": name, "subdir": subdir, "class": "?", "type": "?", "issues": [
                {"level": "P0", "kind": "no_class", "msg": f"no *Crawler / *Channel class in {mod_path}"}
            ]})
            print(f"  [NO CLASS] {subdir}/{name}", flush=True)
            continue

        for cls in classes:
            t0 = time.time()
            if subdir in async_subdirs:
                res = audit_async_channel(cls, name, subdir)
            else:
                res = audit_sync_channel(cls, name, subdir)
            res["elapsed_ms"] = int((time.time() - t0) * 1000)
            results.append(res)
            tag = "OK" if not res.get("issues") else f"{len(res['issues'])} issues"
            print(f"  [{subdir:12}] {cls.__name__:30} {tag:12} ({res['elapsed_ms']}ms)", flush=True)

    total = len(results)
    p0 = sum(1 for r in results if any(i["level"] == "P0" for i in r.get("issues", [])))
    p1 = sum(1 for r in results if any(i["level"] == "P1" for i in r.get("issues", [])))
    p2 = sum(1 for r in results if any(i["level"] == "P2" for i in r.get("issues", [])))
    ok = total - p0 - p1 - p2
    print(f"\n{'='*70}", flush=True)
    print(f"SUMMARY: {total} channels audited", flush=True)
    print(f"  OK (no issues):    {ok}", flush=True)
    print(f"  Has P0 issues:     {p0}", flush=True)
    print(f"  Has P1 issues:     {p1}", flush=True)
    print(f"  Has P2 issues:     {p2}", flush=True)
    print(f"{'='*70}", flush=True)

    out_path = BACKEND_ROOT.parent / "reports" / "p21_r1_audit_crawler.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}", flush=True)


if __name__ == "__main__":
    main()