"""P4-3-W1: SOUL.md / AGENTS.md loader.

Reads project-level rule files at startup, caches their content, and
hot-reloads when any of them change on disk.

* Default project file: ``./SOUL.md`` (project root, configurable).
* Per-agent rule file: ``./.agents/<agent_type>.md``.
* Generic rules:       ``./rules.txt``, ``./AGENTS.md``.

The loader hands the parsed text to :class:`AgentInstructions` as
``PROJECT``-scoped fragments.  When a file is updated, the previous
fragment (matched by ``source_path``) is replaced.

Watcher
-------
We use a lightweight polling watcher (default 2s) when ``watchdog`` is
NOT installed, and a proper :class:`watchdog.events.FileSystemEventHandler`
when it is.  Both paths record a ``mtime`` cache so we don't re-emit
fragments on every poll.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import watchdog; degrade gracefully when missing
try:  # pragma: no cover — optional dep
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer  # type: ignore
    _HAVE_WATCHDOG = True
except Exception:  # noqa: BLE001
    FileSystemEventHandler = None  # type: ignore
    Observer = None  # type: ignore
    _HAVE_WATCHDOG = False


# ── File scanner ────────────────────────────────────────────────────────────
DEFAULT_FILE_NAMES = [
    "SOUL.md",
    "AGENTS.md",
    "rules.txt",
    "CLAUDE.md",
]


def _default_project_root() -> str:
    """Best-effort project root discovery.

    Order:
      1. ``$IMDF_PROJECT_ROOT`` env var
      2. ``$IMDF_DATA_DIR/..``  (the data dir's parent)
      3. The current working directory
    """
    env = os.environ.get("IMDF_PROJECT_ROOT")
    if env:
        return env
    data = os.environ.get("IMDF_DATA_DIR")
    if data:
        return os.path.abspath(os.path.join(data, "..", ".."))
    return os.getcwd()


def _candidate_files(project_root: str) -> List[str]:
    """Return all SOUL/AGENTS/rules files we should watch."""
    files: List[str] = []
    # Top-level files
    for name in DEFAULT_FILE_NAMES:
        p = os.path.join(project_root, name)
        if os.path.isfile(p):
            files.append(p)
    # .agents/*.md
    agents_dir = os.path.join(project_root, ".agents")
    if os.path.isdir(agents_dir):
        for entry in sorted(os.listdir(agents_dir)):
            if entry.endswith((".md", ".txt")):
                files.append(os.path.join(agents_dir, entry))
    return files


# ── Loader ──────────────────────────────────────────────────────────────────
class Loader:
    """Project-level rule file loader with hot-reload.

    Construction is non-blocking: the *initial* load happens in
    :meth:`refresh`, which the caller is expected to invoke once at
    startup (e.g. in the FastAPI ``lifespan`` hook).  After that,
    :meth:`start_watcher` spins up a background thread that calls
    :meth:`refresh` whenever a watched file's mtime changes.
    """

    def __init__(
        self,
        instructions: Any,  # services.agent_service.instructions.AgentInstructions
        project_root: Optional[str] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self._instructions = instructions
        self._project_root = project_root or _default_project_root()
        self._poll_interval = float(poll_interval)
        self._lock = threading.RLock()
        self._mtime_cache: Dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._observer = None  # type: ignore
        self._last_refresh: Dict[str, Any] = {"ts": 0.0, "loaded": [], "errors": []}

    # ── Properties ────────────────────────────────────────────────────────
    @property
    def project_root(self) -> str:
        return self._project_root

    @property
    def last_refresh(self) -> Dict[str, Any]:
        return dict(self._last_refresh)

    # ── File access ───────────────────────────────────────────────────────
    def _safe_read(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning("read %s failed: %s", path, exc)
            return None

    def _fragment_name(self, path: str) -> str:
        rel = os.path.relpath(path, self._project_root).replace(os.sep, "/")
        return f"project:{rel}"

    def _apply_file(self, path: str) -> Optional[str]:
        content = self._safe_read(path)
        if content is None:
            return None
        from .instructions import InstructionFragment, InstructionScope

        fragment_id = f"prj-{hash(path) & 0xffffffff:08x}"
        new_frag = InstructionFragment(
            fragment_id=fragment_id,
            name=self._fragment_name(path),
            content=content,
            scope=InstructionScope.PROJECT,
            description=f"Project-level rule file ({os.path.basename(path)})",
            source_path=path,
            priority=50,
            enabled=True,
        )
        # Replace any prior fragment with the same fragment_id
        existing = self._instructions.get(fragment_id)
        if existing is None:
            self._instructions.add(new_frag)
        else:
            # Mutate in-place to preserve fragment_id
            existing.content = new_frag.content
            existing.name = new_frag.name
            existing.description = new_frag.description
            existing.priority = new_frag.priority
            existing.enabled = new_frag.enabled
            existing.source_path = new_frag.source_path
            existing.updated_at = time.time()
            self._instructions.update(
                fragment_id,
                content=existing.content,
                name=existing.name,
                description=existing.description,
                priority=existing.priority,
                enabled=existing.enabled,
                source_path=existing.source_path,
            )
        return fragment_id

    # ── Refresh ───────────────────────────────────────────────────────────
    def refresh(self) -> Dict[str, Any]:
        """Re-scan all known files and apply any changes."""
        loaded: List[str] = []
        errors: List[Dict[str, Any]] = []
        with self._lock:
            files = _candidate_files(self._project_root)
            for path in files:
                try:
                    mtime = os.path.getmtime(path)
                except OSError as exc:
                    errors.append({"path": path, "error": str(exc)})
                    continue
                if self._mtime_cache.get(path) == mtime:
                    continue
                fid = self._apply_file(path)
                if fid is not None:
                    loaded.append(path)
                    self._mtime_cache[path] = mtime
            self._last_refresh = {
                "ts": time.time(),
                "loaded": loaded,
                "errors": errors,
                "project_root": self._project_root,
            }
        if loaded:
            logger.info("loader: refreshed %d file(s)", len(loaded))
        return self._last_refresh

    # ── Background watcher ───────────────────────────────────────────────
    def start_watcher(self) -> bool:
        """Start the background hot-reload thread.

        Returns True if the watcher started, False if it was already
        running or no project root was found.
        """
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        if _HAVE_WATCHDOG:
            try:
                return self._start_observer()
            except Exception as exc:  # noqa: BLE001
                logger.warning("watchdog observer failed (%s); using poller", exc)
        return self._start_poller()

    def _start_poller(self) -> bool:
        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.refresh()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("poller refresh failed: %s", exc)
                self._stop.wait(self._poll_interval)

        self._thread = threading.Thread(
            target=loop,
            name="soul-loader-poller",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "loader: poller started root=%s interval=%.1fs",
            self._project_root,
            self._poll_interval,
        )
        return True

    def _start_observer(self) -> bool:  # pragma: no cover — optional path
        if FileSystemEventHandler is None or Observer is None:
            return False

        class _Handler(FileSystemEventHandler):  # type: ignore[misc]
            def __init__(self, outer: "Loader") -> None:
                super().__init__()
                self.outer = outer

            def on_modified(self, event):  # noqa: ANN001
                if event.is_directory:
                    return
                self.outer.refresh()

            def on_created(self, event):  # noqa: ANN001
                if event.is_directory:
                    return
                self.outer.refresh()

        self._observer = Observer()
        self._observer.schedule(
            _Handler(self),
            self._project_root,
            recursive=True,
        )
        self._observer.start()
        logger.info("loader: watchdog observer started root=%s", self._project_root)
        return True

    def stop_watcher(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def current_soul(self) -> str:
        """Return the concatenated SOUL/AGENTS content (no template substitution)."""
        from .instructions import InstructionScope

        fragments = self._instructions.list(scope=InstructionScope.PROJECT, enabled_only=True)
        fragments.sort(key=lambda f: (f.priority, f.name))
        return "\n\n".join(
            f"# === {f.name} ===\n{f.content}" for f in fragments
        )


# ── Singleton + convenience ─────────────────────────────────────────────────
_loader: Optional[Loader] = None
_loader_lock = threading.Lock()


def get_loader(instructions: Any = None) -> Loader:
    global _loader
    with _loader_lock:
        if _loader is None:
            # Local import to avoid circulars
            from .instructions import get_instructions

            inst = instructions or get_instructions()
            _loader = Loader(instructions=inst)
            _loader.refresh()
            try:
                _loader.start_watcher()
            except Exception as exc:  # noqa: BLE001
                logger.warning("loader.start_watcher failed: %s", exc)
        return _loader


def reset_loader_for_test() -> None:
    global _loader
    with _loader_lock:
        if _loader is not None:
            _loader.stop_watcher()
        _loader = None


__all__ = [
    "Loader",
    "get_loader",
    "reset_loader_for_test",
    "DEFAULT_FILE_NAMES",
]
