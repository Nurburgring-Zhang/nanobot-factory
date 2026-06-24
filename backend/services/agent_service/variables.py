"""P4-3-W1: Variable store + template renderer.

Inspired by prompt-optimizer's "variables" feature and Hermes' SOUL.md
``{{user_name}}``-style substitution.  A variable is a ``(name, value)``
pair with a *namespace* (one of ``system / project / user / session /
turn``).  Namespaces are merged in priority order to form a single
flat dict that drives :func:`render_template`.

Namespaces
----------
* ``system``  — read-only, baked in (date, platform, language, ...).
* ``project`` — populated from SOUL.md / AGENTS.md front-matter
                 (project name, repo, branch, ...).
* ``user``    — the operator's per-user preferences.
* ``session`` — bound to a :class:`memory.SessionContext`.
* ``turn``    — per-message ephemeral (cleared every turn).

Template syntax
---------------
* ``{{ name }}``            — simple substitution.
* ``{{ name | default }}``  — fallback when missing.
* ``{{ name | upper }}``    — pipe filter (``upper``, ``lower``,
                              ``title``, ``trim``, ``default``).

Anything not matching the ``{{...}}`` pattern is passed through
verbatim, so a template can also contain JSON / code blocks.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Namespace enum ──────────────────────────────────────────────────────────
class VariableNamespace(str, Enum):
    SYSTEM = "system"      # 1 — lowest priority (only overridden by being absent)
    PROJECT = "project"    # 2
    USER = "user"          # 3
    SESSION = "session"    # 4
    TURN = "turn"          # 5 — highest (per-message ephemeral)


# We resolve in this order so later (higher-priority) namespaces can
# shadow earlier ones.
RESOLUTION_ORDER: List[VariableNamespace] = [
    VariableNamespace.SYSTEM,
    VariableNamespace.PROJECT,
    VariableNamespace.USER,
    VariableNamespace.SESSION,
    VariableNamespace.TURN,
]


# ── Template engine ─────────────────────────────────────────────────────────
_TEMPLATE_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_FILTERS = {
    "upper": lambda v: str(v).upper(),
    "lower": lambda v: str(v).lower(),
    "title": lambda v: str(v).title(),
    "trim": lambda v: str(v).strip(),
    "default": lambda v, fb="": fb if v in (None, "") else v,
}


def _apply_filter(name: str, value: Any, fallback: str = "") -> Any:
    fn = _FILTERS.get(name)
    if fn is None:
        return value
    try:
        if name == "default":
            return fn(value, fallback)
        return fn(value)
    except Exception:  # noqa: BLE001
        return value


def _resolve_token(token: str, variables: Dict[str, Any]) -> str:
    """Resolve one ``{{ name | filter | default:foo }}`` token."""
    parts = [p.strip() for p in token.split("|")]
    name = parts[0]
    filters = parts[1:]
    has_default = any(p.startswith("default") for p in filters)
    value = variables.get(name)
    if value is None and not has_default:
        # Keep the placeholder so the LLM sees a missing var
        return f"{{{{ {token.strip()} }}}}"
    for f in filters:
        if ":" in f:
            fname, fb = f.split(":", 1)
            value = _apply_filter(fname.strip(), value, fb.strip())
        else:
            value = _apply_filter(f, value)
    if value is None:
        return ""
    return str(value)


def render_template(template: str, variables: Dict[str, Any]) -> str:
    """Substitute ``{{ name | filter }}`` tokens in *template*.

    Unknown tokens without a ``default`` filter are left intact so the
    downstream LLM can see the gap.  Non-string values are serialised
    via ``json.dumps`` for fidelity.
    """

    def _sub(match: "re.Match[str]") -> str:
        return _resolve_token(match.group(1), variables)

    return _TEMPLATE_RE.sub(_sub, str(template))


# ── Variable record ──────────────────────────────────────────────────────────
@dataclass
class Variable:
    name: str
    value: Any
    namespace: VariableNamespace = VariableNamespace.USER
    var_id: str = field(default_factory=lambda: f"var-{uuid.uuid4().hex[:12]}")
    owner: Optional[str] = None  # user_id / session_id / project id
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "var_id": self.var_id,
            "name": self.name,
            "value": self.value,
            "namespace": self.namespace.value
            if isinstance(self.namespace, VariableNamespace)
            else str(self.namespace),
            "owner": self.owner,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Variable":
        ns = d.get("namespace")
        if isinstance(ns, str) and ns in [s.value for s in VariableNamespace]:
            ns = VariableNamespace(ns)
        else:
            ns = VariableNamespace.USER
        return cls(
            name=str(d.get("name", "")),
            value=d.get("value"),
            namespace=ns,
            var_id=str(d.get("var_id", f"var-{uuid.uuid4().hex[:12]}")),
            owner=d.get("owner"),
            description=str(d.get("description", "")),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


# ── Built-in system variables ───────────────────────────────────────────────
def _builtin_system_variables() -> List[Variable]:
    """Read-only, always-present.  Computed at call time so the date
    never goes stale."""
    now = _dt.datetime.now()
    return [
        Variable(name="date", value=now.strftime("%Y-%m-%d"), namespace=VariableNamespace.SYSTEM),
        Variable(name="time", value=now.strftime("%H:%M:%S"), namespace=VariableNamespace.SYSTEM),
        Variable(name="year", value=str(now.year), namespace=VariableNamespace.SYSTEM),
        Variable(name="month", value=str(now.month), namespace=VariableNamespace.SYSTEM),
        Variable(name="day", value=str(now.day), namespace=VariableNamespace.SYSTEM),
        Variable(name="platform", value="Nanobot Factory (ZhiYing)", namespace=VariableNamespace.SYSTEM),
        Variable(name="service", value="agent-service", namespace=VariableNamespace.SYSTEM),
        Variable(name="language", value=os.environ.get("IMDF_DEFAULT_LANG", "zh-CN"), namespace=VariableNamespace.SYSTEM),
        Variable(name="user_name", value=os.environ.get("IMDF_DEFAULT_USER", "anonymous"), namespace=VariableNamespace.SYSTEM),
        Variable(name="project_name", value=os.environ.get("IMDF_PROJECT_NAME", "nanobot-factory"), namespace=VariableNamespace.SYSTEM),
    ]


# ── Variable store ──────────────────────────────────────────────────────────
class VariableStore:
    """Thread-safe store of :class:`Variable` records.

    * System variables are read-only (set on init; setters reject them).
    * Other namespaces are mutable.
    * SQLite persistence is best-effort.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._variables: Dict[str, Variable] = {}
        self._db_path = db_path
        # Seed system variables
        for v in _builtin_system_variables():
            self._variables[v.var_id] = v
        if db_path:
            self._init_db(db_path)
            self._reload_from_db()

    # ── DB ────────────────────────────────────────────────────────────────
    def _init_db(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_variables (
                    var_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    owner TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_variables_ns_name_owner "
                "ON agent_variables(namespace, name, owner)"
            )
            conn.commit()

    def _reload_from_db(self) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT var_id, name, value, namespace, owner, description, "
                    "created_at, updated_at FROM agent_variables"
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("variables reload failed: %s", exc)
            return
        for r in rows:
            try:
                raw_value = r[2]
                try:
                    parsed = json.loads(raw_value)
                except Exception:  # noqa: BLE001
                    parsed = raw_value
                v = Variable(
                    name=str(r[1]),
                    value=parsed,
                    namespace=VariableNamespace(r[3])
                    if r[3] in [s.value for s in VariableNamespace]
                    else VariableNamespace.USER,
                    var_id=str(r[0]),
                    owner=r[4],
                    description=str(r[5] or ""),
                    created_at=float(r[6]),
                    updated_at=float(r[7]),
                )
            except Exception:  # noqa: BLE001
                continue
            with self._lock:
                # System variables are always re-seeded at init, so DB
                # rows for namespace=system are ignored.
                if v.namespace == VariableNamespace.SYSTEM:
                    continue
                self._variables[v.var_id] = v

    def _persist(self, v: Variable) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_variables
                    (var_id, name, value, namespace, owner, description,
                     created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        v.var_id,
                        v.name,
                        json.dumps(v.value, ensure_ascii=False) if not isinstance(v.value, str)
                        else v.value,
                        v.namespace.value
                        if isinstance(v.namespace, VariableNamespace)
                        else str(v.namespace),
                        v.owner,
                        v.description,
                        v.created_at,
                        v.updated_at,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist variable %s failed: %s", v.var_id, exc)

    def _delete_persist(self, var_id: str) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "DELETE FROM agent_variables WHERE var_id=?",
                    (var_id,),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete variable %s failed: %s", var_id, exc)

    # ── CRUD ──────────────────────────────────────────────────────────────
    def set(
        self,
        name: str,
        value: Any,
        namespace: VariableNamespace = VariableNamespace.USER,
        *,
        owner: Optional[str] = None,
        description: str = "",
    ) -> Variable:
        if namespace == VariableNamespace.SYSTEM:
            raise PermissionError("system variables are read-only")
        with self._lock:
            # Check for an existing var with the same (namespace, name, owner)
            existing = None
            for v in self._variables.values():
                if v.namespace == namespace and v.name == name and (v.owner or None) == (owner or None):
                    existing = v
                    break
            if existing:
                existing.value = value
                existing.description = description or existing.description
                existing.updated_at = time.time()
                self._persist(existing)
                return existing
            new_v = Variable(
                name=str(name),
                value=value,
                namespace=namespace,
                owner=owner,
                description=description,
            )
            self._variables[new_v.var_id] = new_v
            self._persist(new_v)
        return new_v

    def get(
        self,
        name: str,
        *,
        owner: Optional[str] = None,
    ) -> Optional[Variable]:
        with self._lock:
            for v in self._variables.values():
                if v.name == name and (v.owner or None) == (owner or None):
                    return v
        return None

    def delete(self, var_id: str) -> bool:
        with self._lock:
            v = self._variables.get(var_id)
            if not v:
                return False
            if v.namespace == VariableNamespace.SYSTEM:
                return False
            del self._variables[var_id]
        self._delete_persist(var_id)
        return True

    def list(
        self,
        namespace: Optional[VariableNamespace] = None,
        owner: Optional[str] = None,
    ) -> List[Variable]:
        with self._lock:
            items = list(self._variables.values())
        if namespace is not None:
            items = [v for v in items if v.namespace == namespace]
        if owner is not None:
            items = [v for v in items if (v.owner or None) == (owner or None)]
        items.sort(key=lambda v: (RESOLUTION_ORDER.index(v.namespace), v.name))
        return items

    def reset_user_fragments_for_test(self) -> int:
        with self._lock:
            ids = [
                vid for vid, v in self._variables.items()
                if v.namespace != VariableNamespace.SYSTEM
            ]
            for vid in ids:
                self._variables.pop(vid, None)
        for vid in ids:
            self._delete_persist(vid)
        return len(ids)

    # ── Resolution ────────────────────────────────────────────────────────
    def resolve(
        self,
        *,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        turn: Optional[Dict[str, Any]] = None,
        project: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a flat dict after merging all namespaces.

        ``session_id`` and ``user_id`` let you pull per-session /
        per-user overrides.  ``turn`` is an ephemeral dict that
        shadows everything (cleared after the request).
        """
        flat: Dict[str, Any] = {}
        with self._lock:
            items = list(self._variables.values())
        # Walk the namespaces in priority order — later writes win.
        for ns in RESOLUTION_ORDER:
            if ns == VariableNamespace.SYSTEM:
                # Always re-emit system variables fresh
                for v in _builtin_system_variables():
                    flat[v.name] = v.value
                continue
            if ns == VariableNamespace.PROJECT:
                if project:
                    for k, val in project.items():
                        flat[k] = val
                # Also pick up project-namespace variables
                for v in items:
                    if v.namespace == ns:
                        flat[v.name] = v.value
                continue
            if ns == VariableNamespace.USER:
                for v in items:
                    if v.namespace == ns and (v.owner is None or v.owner == user_id):
                        flat[v.name] = v.value
                continue
            if ns == VariableNamespace.SESSION:
                for v in items:
                    if v.namespace == ns and v.owner == session_id:
                        flat[v.name] = v.value
                continue
            if ns == VariableNamespace.TURN:
                if turn:
                    for k, val in turn.items():
                        flat[k] = val
        return flat

    def summary(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {s.value: 0 for s in VariableNamespace}
            for v in self._variables.values():
                counts[v.namespace.value] = counts.get(v.namespace.value, 0) + 1
        return counts


# ── Singleton ────────────────────────────────────────────────────────────────
_var: Optional[VariableStore] = None
_var_lock = threading.Lock()


def get_variable_store(db_path: Optional[str] = None) -> VariableStore:
    global _var
    with _var_lock:
        if _var is None:
            if db_path is None:
                env = os.environ.get("IMDF_DATA_DIR")
                if env:
                    db_path = os.path.join(env, "agent_variables.db")
            _var = VariableStore(db_path=db_path)
        return _var


def reset_variable_store_for_test() -> None:
    global _var
    with _var_lock:
        _var = None


__all__ = [
    "Variable",
    "VariableStore",
    "VariableNamespace",
    "RESOLUTION_ORDER",
    "render_template",
    "get_variable_store",
    "reset_variable_store_for_test",
]
