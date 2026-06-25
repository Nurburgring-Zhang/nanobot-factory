"""P6-Fix-P0-5: PluginRegistry — runtime agent plugin registry.

A process-wide registry that maps ``AgentType`` slugs (or arbitrary
plugin names) to :class:`BaseAgent` subclasses.  The registry is
intentionally tiny — the actual dispatch lives in
:mod:`services.agent_service.executor`.  What this module provides is
the *extension point*: callers can register a new agent at runtime
and it becomes immediately dispatchable.

Design notes:
  * Singleton via :meth:`get_registry`.  We use a class-level
    ``RLock`` so the registry is safe under threaded executors.
  * ``register(name, cls)`` is idempotent on name (the second call
    overwrites the first) and *strict* on class — passing a class
    that doesn't subclass :class:`BaseAgent` raises ``TypeError``.
  * ``unregister(name)`` is a no-op when the name is unknown, so
    plugin teardown is exception-free.
  * :meth:`reset` is provided for the test suite only; production
    code should never call it.
"""
from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Tuple, Type

from .base import BaseAgent


class PluginRegistry:
    """Process-wide registry of :class:`BaseAgent` subclasses.

    Usage::

        reg = PluginRegistry.get_registry()
        reg.register("my_plugin", MyPluginAgent)
        cls = reg.get("my_plugin")
        assert issubclass(cls, BaseAgent)
    """

    # ── Singleton plumbing ───────────────────────────────────────────
    _instance: "PluginRegistry | None" = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        # name -> BaseAgent subclass
        self._agents: Dict[str, Type[BaseAgent]] = {}
        self._lock = threading.RLock()
        # Optional back-link to AgentType enum for validation; we do
        # NOT import the enum at module load to avoid the circular
        # ``imdf.agents`` <-> ``services.agent_service.agents`` import.
        self._validator = None  # callable: name -> bool

    # ── Singleton accessor ───────────────────────────────────────────
    @classmethod
    def get_registry(cls) -> "PluginRegistry":
        """Return the process-wide registry, creating it on first call."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_singleton(cls) -> None:
        """Drop the singleton — for test setup only."""
        with cls._singleton_lock:
            if cls._instance is not None:
                cls._instance.reset()
            cls._instance = None

    # ── Core API ──────────────────────────────────────────────────────
    def register(
        self,
        name: str,
        agent_class: Type[BaseAgent],
        *,
        overwrite: bool = True,
    ) -> None:
        """Bind ``name`` -> ``agent_class``.

        Args:
            name: The plugin identifier (typically the AgentType slug,
                e.g. ``"cleaning"``).  Must be non-empty.
            agent_class: A concrete subclass of :class:`BaseAgent`.
            overwrite: When False, raise ``ValueError`` if the name is
                already registered.  Defaults to True (idempotent).

        Raises:
            TypeError: ``agent_class`` is not a subclass of
                :class:`BaseAgent`.
            ValueError: ``name`` is empty / not a string, or the
                name is already registered and ``overwrite=False``.
        """
        if not isinstance(name, str) or not name:
            raise ValueError(f"plugin name must be a non-empty string, got {name!r}")
        if not (isinstance(agent_class, type) and issubclass(agent_class, BaseAgent)):
            raise TypeError(
                f"agent_class must subclass BaseAgent, got {agent_class!r}"
            )
        # Optional validator hook (set by services.agent_service at
        # import time so we can reject names that collide with the
        # built-in AgentType catalogue).
        if self._validator is not None and not self._validator(name):
            raise ValueError(f"plugin name {name!r} rejected by validator")
        with self._lock:
            if not overwrite and name in self._agents:
                raise ValueError(f"plugin {name!r} already registered")
            self._agents[name] = agent_class

    def unregister(self, name: str) -> bool:
        """Remove ``name`` from the registry.  Returns True if a
        binding was removed, False if the name was unknown."""
        with self._lock:
            return self._agents.pop(name, None) is not None

    def get(self, name: str) -> Type[BaseAgent]:
        """Return the class registered under ``name``.

        Raises:
            KeyError: ``name`` is not registered.
        """
        with self._lock:
            try:
                return self._agents[name]
            except KeyError as e:
                raise KeyError(f"plugin {name!r} is not registered") from e

    def try_get(self, name: str) -> Type[BaseAgent] | None:
        """Return the class registered under ``name`` or None."""
        with self._lock:
            return self._agents.get(name)

    def list(self) -> List[str]:
        """Return a snapshot of the registered plugin names (sorted)."""
        with self._lock:
            return sorted(self._agents.keys())

    def items(self) -> List[Tuple[str, Type[BaseAgent]]]:
        """Return a snapshot of (name, class) pairs (sorted by name)."""
        with self._lock:
            return sorted(self._agents.items(), key=lambda kv: kv[0])

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._agents

    def __len__(self) -> int:
        with self._lock:
            return len(self._agents)

    # ── Test helpers ──────────────────────────────────────────────────
    def reset(self) -> None:
        """Remove every binding.  Test-only."""
        with self._lock:
            self._agents.clear()

    def set_validator(self, validator) -> None:
        """Install an optional ``name -> bool`` validator.

        Production wiring (in ``services.agent_service.agents``) uses
        this to reject plugin names that collide with the built-in
        AgentType catalogue.  Tests can install a passthrough.
        """
        with self._lock:
            self._validator = validator

    def bulk_register(
        self,
        mapping: Dict[str, Type[BaseAgent]],
        *,
        overwrite: bool = True,
    ) -> List[str]:
        """Register every entry in ``mapping``.  Returns the names
        actually registered (in registration order).  Rolls back
        partial registrations when one entry raises."""
        registered: List[str] = []
        snapshot: List[Tuple[str, Type[BaseAgent]]] = []
        try:
            for name, cls in mapping.items():
                self.register(name, cls, overwrite=overwrite)
                snapshot.append((name, cls))
                registered.append(name)
        except Exception:
            for name, cls in reversed(snapshot):
                self._agents.pop(name, None)
            raise
        return registered


__all__ = ["PluginRegistry"]
