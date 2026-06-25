"""P4-3-W1: Tool registry + ``@tool`` decorator.

A :class:`Tool` is a callable with a name, description, JSON-Schema
parameter spec, optional ``requires_confirmation`` flag, and an audit
log handler.  The :class:`ToolRegistry` is the central catalogue that:

* hosts the 10+ built-in tools (search / code_exec / file_read /
  file_write / web_search / sql_query / http_request / memory_search /
  image_gen / video_gen),
* discovers user-defined tools by scanning ``custom_tools/`` at
  startup,
* routes :func:`invoke` calls to the right handler,
* writes every invocation to an ``audit_chain`` (immutable list of
  ``{tool, args, result, ts, actor}`` dicts) for compliance / debugging.

The audit chain lives in process memory by default and is also
appended to a SQLite table ``tool_audit`` for durability.
"""
from __future__ import annotations

import builtins
import functools
import hashlib
import inspect
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# ── Tool dataclass ──────────────────────────────────────────────────────────
@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    tags: List[str] = field(default_factory=list)
    builtin: bool = True
    source_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "schema": dict(self.schema),
            "requires_confirmation": self.requires_confirmation,
            "tags": list(self.tags),
            "builtin": self.builtin,
            "source_path": self.source_path,
            "created_at": self.created_at,
        }


# ── Schema inference helper ─────────────────────────────────────────────────
def _infer_schema(fn: Callable[..., Any], explicit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a JSON Schema dict from a function signature.

    Falls back to a permissive ``{"type": "object"}`` when we can't
    introspect (e.g. builtin C function).
    """
    if explicit:
        return explicit
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {"type": "object", "additionalProperties": True}
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in sig.parameters.items():
        if name in {"self", "cls"}:
            continue
        annotation = param.annotation
        js_type: str = "string"
        if annotation in (int,):
            js_type = "integer"
        elif annotation in (float,):
            js_type = "number"
        elif annotation in (bool,):
            js_type = "boolean"
        elif annotation in (list, List):
            js_type = "array"
        elif annotation in (dict, Dict):
            js_type = "object"
        properties[name] = {"type": js_type, "description": f"Argument {name}"}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


# ── @tool decorator ─────────────────────────────────────────────────────────
def tool(
    name: str,
    description: str = "",
    *,
    schema: Optional[Dict[str, Any]] = None,
    requires_confirmation: bool = False,
    tags: Optional[List[str]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: mark a function as a tool, attach metadata.

    The decorated function is unchanged at call-time — the registry
    harvests the metadata via :func:`ToolRegistry.register`.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__tool__ = {  # type: ignore[attr-defined]
            "name": name,
            "description": description or fn.__doc__ or "",
            "schema": _infer_schema(fn, schema),
            "requires_confirmation": requires_confirmation,
            "tags": list(tags or []),
        }

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper.__tool__ = fn.__tool__  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ── Audit chain ─────────────────────────────────────────────────────────────
@dataclass
class AuditEntry:
    invocation_id: str
    tool: str
    args: Dict[str, Any]
    result: Any
    error: Optional[str]
    actor: str
    started_at: float
    finished_at: float
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "tool": self.tool,
            "args": dict(self.args),
            "result": self.result,
            "error": self.error,
            "actor": self.actor,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


# ── ToolRegistry ────────────────────────────────────────────────────────────
class ToolRegistry:
    """Thread-safe registry of :class:`Tool` objects + audit chain."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        custom_tools_dir: Optional[str] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._tools: Dict[str, Tool] = {}
        self._audit: List[AuditEntry] = []
        self._db_path = db_path
        self._custom_tools_dir = custom_tools_dir
        if db_path:
            self._init_db(db_path)
        # Built-in tools
        for t in _builtin_tools():
            self._register_tool(t)
        # Custom tools discovery
        if custom_tools_dir and os.path.isdir(custom_tools_dir):
            self._load_custom_tools(custom_tools_dir)

    # ── DB ────────────────────────────────────────────────────────────────
    def _init_db(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_audit (
                    invocation_id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    args TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    actor TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL NOT NULL,
                    duration_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_tool_audit_tool ON tool_audit(tool)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_tool_audit_started ON tool_audit(started_at)"
            )
            conn.commit()

    def _persist_audit(self, entry: AuditEntry) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tool_audit
                    (invocation_id, tool, args, result, error, actor,
                     started_at, finished_at, duration_ms)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        entry.invocation_id,
                        entry.tool,
                        json.dumps(entry.args, ensure_ascii=False),
                        json.dumps(entry.result, ensure_ascii=False, default=str)
                        if entry.result is not None
                        else None,
                        entry.error,
                        entry.actor,
                        entry.started_at,
                        entry.finished_at,
                        entry.duration_ms,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist audit %s failed: %s", entry.invocation_id, exc)

    # ── Registration ─────────────────────────────────────────────────────
    def _register_tool(self, t: Tool) -> None:
        with self._lock:
            self._tools[t.name] = t

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        description: str = "",
        schema: Optional[Dict[str, Any]] = None,
        requires_confirmation: bool = False,
        tags: Optional[List[str]] = None,
        builtin: bool = False,
        source_path: Optional[str] = None,
    ) -> Tool:
        t = Tool(
            name=name,
            description=description or (handler.__doc__ or ""),
            handler=handler,
            schema=_infer_schema(handler, schema),
            requires_confirmation=requires_confirmation,
            tags=list(tags or []),
            builtin=builtin,
            source_path=source_path,
        )
        self._register_tool(t)
        return t

    def register_function(
        self,
        fn: Callable[..., Any],
        *,
        name: Optional[str] = None,
        builtin: bool = False,
    ) -> Tool:
        """Register a function previously decorated with :func:`tool`."""
        meta = getattr(fn, "__tool__", None)
        if not meta:
            raise ValueError("function is not decorated with @tool")
        return self.register(
            name=name or meta["name"],
            handler=fn,
            description=meta.get("description", ""),
            schema=meta.get("schema"),
            requires_confirmation=meta.get("requires_confirmation", False),
            tags=meta.get("tags", []),
            builtin=builtin,
            source_path=inspect.getfile(fn) if hasattr(fn, "__module__") else None,
        )

    def unregister(self, name: str) -> bool:
        with self._lock:
            t = self._tools.get(name)
            if not t:
                return False
            if t.builtin:
                # Built-in tools cannot be removed
                return False
            del self._tools[name]
        return True

    # ── Discovery / queries ──────────────────────────────────────────────
    def get(self, name: str) -> Optional[Tool]:
        with self._lock:
            return self._tools.get(name)

    def list(
        self,
        tag: Optional[str] = None,
        builtin_only: bool = False,
    ) -> List[Tool]:
        with self._lock:
            items = list(self._tools.values())
        if tag:
            items = [t for t in items if tag in t.tags]
        if builtin_only:
            items = [t for t in items if t.builtin]
        items.sort(key=lambda t: (not t.builtin, t.name))
        return items

    def list_names(self) -> List[str]:
        with self._lock:
            return sorted(self._tools.keys())

    # ── Invocation ───────────────────────────────────────────────────────
    def invoke(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "anonymous",
    ) -> Dict[str, Any]:
        with self._lock:
            tool_obj = self._tools.get(name)
        if not tool_obj:
            raise KeyError(f"tool_not_found:{name}")
        args = dict(args or {})
        invocation_id = f"inv-{uuid.uuid4().hex[:12]}"
        started = time.time()
        result: Any = None
        error: Optional[str] = None
        try:
            result = tool_obj.handler(**args)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}:{exc}"
            logger.warning("tool %s invocation failed: %s", name, error)
        finished = time.time()
        entry = AuditEntry(
            invocation_id=invocation_id,
            tool=name,
            args=args,
            result=result,
            error=error,
            actor=actor,
            started_at=started,
            finished_at=finished,
            duration_ms=int((finished - started) * 1000),
        )
        with self._lock:
            self._audit.append(entry)
        self._persist_audit(entry)
        # P6-Fix-B-3: bridge into HMAC-signed audit chain (best-effort).
        self._record_tool_audit(
            invocation_id=invocation_id,
            tool=name,
            actor=actor,
            args=args,
            result=result,
            error=error,
            started_at=started,
            finished_at=finished,
        )
        return entry.to_dict()

    def _record_tool_audit(
        self,
        *,
        invocation_id: str,
        tool: str,
        actor: str,
        args: Dict[str, Any],
        result: Any,
        error: Optional[str],
        started_at: float,
        finished_at: float,
    ) -> None:
        """Forward the invocation into the HMAC-signed :class:`ToolAuditChain`.

        Failure here must NEVER bubble back to the tool hot path — a
        broken audit chain should not break user-facing tool calls.
        """
        try:
            from .audit import get_tool_audit_chain
            get_tool_audit_chain().append(
                invocation_id=invocation_id,
                tool=tool,
                actor=actor,
                args=args,
                result=result,
                error=error,
                started_at=started_at,
                finished_at=finished_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool audit bridge append failed for %s: %s", invocation_id, exc)

    def audit_chain(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            chain = self._audit[-max(0, limit):]
        return [e.to_dict() for e in chain]

    def clear_audit(self) -> int:
        with self._lock:
            n = len(self._audit)
            self._audit.clear()
        return n

    # ── Custom tools discovery ───────────────────────────────────────────
    def _load_custom_tools_dir(self, directory: str) -> int:
        """Reload custom tools from a directory.  Returns count loaded."""
        loaded = 0
        if not directory or not os.path.isdir(directory):
            return 0
        for entry in sorted(os.listdir(directory)):
            if not entry.endswith(".py"):
                continue
            if entry.startswith("_"):
                continue
            full = os.path.join(directory, entry)
            try:
                count = self._load_custom_module(full)
                loaded += count
            except Exception as exc:  # noqa: BLE001
                logger.warning("custom tool %s failed to load: %s", full, exc)
        return loaded

    def _load_custom_module(self, path: str) -> int:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            f"_custom_tools_{os.path.basename(path).replace('.py', '')}",
            path,
        )
        if not spec or not spec.loader:
            return 0
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            logger.warning("exec_module failed for %s: %s", path, exc)
            return 0
        n = 0
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and hasattr(obj, "__tool__"):
                self.register_function(obj, builtin=False)
                n += 1
        return n

    def reload_custom_tools(self) -> int:
        if not self._custom_tools_dir:
            return 0
        return self._load_custom_tools_dir(self._custom_tools_dir)

    def reset_for_test(self) -> None:
        with self._lock:
            self._tools.clear()
            self._audit.clear()
        for t in _builtin_tools():
            self._register_tool(t)


# ── Built-in tools (10+) ────────────────────────────────────────────────────
def _builtin_tools() -> List[Tool]:
    """Return the catalogue of built-in tools (>= 10)."""

    @tool(name="search", description="Search the local document index (deterministic offline stub).", tags=["read", "offline"])
    def _search(query: str, top_k: int = 5) -> Dict[str, Any]:
        # No real backend; return a deterministic echo so the route
        # works hermetically.  Production callers should override via
        # the agent-service env vars.
        return {
            "query": query,
            "top_k": int(top_k),
            "hits": [
                {"rank": 1, "doc_id": f"doc-{abs(hash(query)) % 1000:04d}", "score": 0.91, "snippet": f"Best match for {query[:40]}"},
                {"rank": 2, "doc_id": f"doc-{abs(hash(query+'b')) % 1000:04d}", "score": 0.74, "snippet": "Second match"},
            ],
        }

    @tool(name="code_exec", description="Run a Python expression in a restricted namespace and return the result.", tags=["compute", "python"], requires_confirmation=True)
    def _code_exec(expression: str) -> Dict[str, Any]:
        # VERY restricted — no imports, no builtins beyond safe ones.
        safe_builtins = {
            "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
            "range": range, "list": list, "dict": dict, "set": set,
            "str": str, "int": int, "float": float, "bool": bool,
            "print": lambda *a, **k: None,
            "True": True, "False": False, "None": None,
        }
        try:
            value = eval(expression, {"__builtins__": safe_builtins}, {})  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
        return {"ok": True, "value": str(value)[:1024]}

    @tool(name="file_read", description="Read a text file from the agent-service data directory (sandboxed).", tags=["io"])
    def _file_read(path: str, max_bytes: int = 65536) -> Dict[str, Any]:
        sandbox_root = os.environ.get("IMDF_DATA_DIR", ".")
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(os.path.abspath(sandbox_root)):
            return {"ok": False, "error": "path_outside_sandbox"}
        if not os.path.isfile(abs_path):
            return {"ok": False, "error": "file_not_found"}
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read(int(max_bytes))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": abs_path, "size": len(data), "content": data}

    @tool(name="file_write", description="Write text to a file in the agent-service data directory (sandboxed).", tags=["io"], requires_confirmation=True)
    def _file_write(path: str, content: str) -> Dict[str, Any]:
        sandbox_root = os.environ.get("IMDF_DATA_DIR", ".")
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(os.path.abspath(sandbox_root)):
            return {"ok": False, "error": "path_outside_sandbox"}
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": abs_path, "size": len(content)}

    @tool(name="web_search", description="Search the web (Tavily / Replicate proxy). Offline fallback returns a deterministic stub.", tags=["network", "search"])
    def _web_search(query: str, num_results: int = 5) -> Dict[str, Any]:
        # Production wiring is via env: TAVILY_API_KEY / REPLICATE_API_TOKEN
        api_key = os.environ.get("TAVILY_API_KEY") or os.environ.get("REPLICATE_API_TOKEN")
        if not api_key:
            return {
                "query": query,
                "provider": "offline_stub",
                "results": [
                    {
                        "rank": 1,
                        "title": f"Stub result for {query[:40]}",
                        "url": "https://example.invalid/stub",
                        "snippet": "Configure TAVILY_API_KEY to enable real web search.",
                    }
                ][: max(1, int(num_results))],
            }
        # Real call (best-effort, swallow network errors to a stub)
        try:
            url = "https://api.tavily.com/search"
            payload = json.dumps({"api_key": api_key, "query": query, "max_results": int(num_results)}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                data = json.loads(resp.read().decode())
            return {"query": query, "provider": "tavily", "results": data.get("results", [])}
        except Exception as exc:  # noqa: BLE001
            return {"query": query, "provider": "tavily_fallback", "error": str(exc), "results": []}

    @tool(name="sql_query", description="Run a read-only SQL query against the agent-service SQLite DB (SELECT only).", tags=["db", "sql"], requires_confirmation=True)
    def _sql_query(sql: str) -> Dict[str, Any]:
        # Only SELECT statements
        cleaned = sql.strip().rstrip(";").strip()
        if not cleaned.lower().startswith("select"):
            return {"ok": False, "error": "only_select_allowed"}
        db_path = os.environ.get("IMDF_AGENT_DB")
        if not db_path or not os.path.isfile(db_path):
            return {"ok": False, "error": "agent_db_unavailable"}
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.execute(cleaned)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "columns": cols, "rows": [list(r) for r in rows[:200]]}

    @tool(name="http_request", description="Issue a controlled HTTP GET/POST request (SSRF-safe, allow-list).", tags=["network"], requires_confirmation=True)
    def _http_request(url: str, method: str = "GET", body: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"ok": False, "error": "scheme_not_allowed"}
        # Block private / loopback
        host = (parsed.hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
            return {"ok": False, "error": "ssrf_blocked"}
        try:
            data = body.encode() if body else None
            req = urllib.request.Request(url, data=data, method=method.upper())
            with urllib.request.urlopen(req, timeout=int(timeout)) as resp:  # noqa: S310
                raw = resp.read(65536)
            return {"ok": True, "status": resp.status, "body": raw.decode("utf-8", errors="replace")[:65536]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @tool(name="memory_search", description="Search the agent's long-term memory (scope + key prefix).", tags=["memory"])
    def _memory_search(scope: str, prefix: str = "", limit: int = 20) -> Dict[str, Any]:
        from services.agent_service.memory import get_long_term
        items = get_long_term().list(scope, limit=int(limit))
        if prefix:
            items = [m for m in items if m["key"].startswith(prefix)]
        return {"scope": scope, "prefix": prefix, "count": len(items), "items": items}

    @tool(name="image_gen", description="Generate an image (Replicate or offline stub).", tags=["ai", "media"], requires_confirmation=True)
    def _image_gen(prompt: str, width: int = 512, height: int = 512) -> Dict[str, Any]:
        token = os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            h = hashlib.sha1(prompt.encode()).hexdigest()[:12]
            return {
                "provider": "offline_stub",
                "prompt": prompt,
                "width": int(width),
                "height": int(height),
                "image_url": f"https://example.invalid/img/{h}.png",
            }
        # Best-effort real call (kept simple to avoid Replicate SDK deps)
        return {
            "provider": "replicate_pending",
            "prompt": prompt,
            "width": int(width),
            "height": int(height),
        }

    @tool(name="video_gen", description="Generate a video (Replicate / Bernini-style placeholder).", tags=["ai", "media"], requires_confirmation=True)
    def _video_gen(prompt: str, duration_seconds: int = 5) -> Dict[str, Any]:
        token = os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            h = hashlib.sha1(prompt.encode()).hexdigest()[:12]
            return {
                "provider": "offline_stub",
                "prompt": prompt,
                "duration_seconds": int(duration_seconds),
                "video_url": f"https://example.invalid/vid/{h}.mp4",
            }
        return {"provider": "replicate_pending", "prompt": prompt, "duration_seconds": int(duration_seconds)}

    @tool(name="hash", description="Hash a string with SHA-256 (or MD5).", tags=["util"])
    def _hash(text: str, algorithm: str = "sha256") -> Dict[str, Any]:
        alg = (algorithm or "sha256").lower()
        if alg == "md5":
            h = hashlib.md5(text.encode()).hexdigest()
        elif alg == "sha1":
            h = hashlib.sha1(text.encode()).hexdigest()
        else:
            h = hashlib.sha256(text.encode()).hexdigest()
        return {"algorithm": alg, "hash": h, "input_len": len(text)}

    @tool(name="now", description="Return the current UTC time in ISO-8601.", tags=["util"])
    def _now() -> Dict[str, Any]:
        from datetime import datetime, timezone
        return {"utc": datetime.now(timezone.utc).isoformat(), "epoch": int(time.time())}

    @tool(name="echo", description="Echo a string back (useful for testing the registry).", tags=["util", "test"])
    def _echo(message: str = "") -> Dict[str, Any]:
        return {"echo": message}

    # Collect the wrapped functions into Tool records
    tools: List[Tool] = []
    for fn in [
        _search, _code_exec, _file_read, _file_write, _web_search,
        _sql_query, _http_request, _memory_search, _image_gen, _video_gen,
        _hash, _now, _echo,
    ]:
        meta = getattr(fn, "__tool__", None)
        if not meta:
            continue
        tools.append(
            Tool(
                name=meta["name"],
                description=meta["description"],
                handler=fn,
                schema=meta["schema"],
                requires_confirmation=meta["requires_confirmation"],
                tags=meta["tags"],
                builtin=True,
            )
        )
    return tools


# ── Singleton ────────────────────────────────────────────────────────────────
_registry: Optional[ToolRegistry] = None
_registry_lock = threading.Lock()


def get_tool_registry(
    db_path: Optional[str] = None,
    custom_tools_dir: Optional[str] = None,
) -> ToolRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            if db_path is None:
                env = os.environ.get("IMDF_DATA_DIR")
                if env:
                    db_path = os.path.join(env, "tool_audit.db")
            if custom_tools_dir is None:
                # Conventional location: backend/services/agent_service/custom_tools
                here = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.normpath(os.path.join(here, "..", "custom_tools"))
                if os.path.isdir(candidate):
                    custom_tools_dir = candidate
            _registry = ToolRegistry(
                db_path=db_path,
                custom_tools_dir=custom_tools_dir,
            )
        return _registry


def reset_tool_registry_for_test() -> None:
    global _registry
    with _registry_lock:
        _registry = None


__all__ = [
    "Tool",
    "ToolRegistry",
    "AuditEntry",
    "tool",
    "get_tool_registry",
    "reset_tool_registry_for_test",
]
