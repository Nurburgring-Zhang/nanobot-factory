"""P6-Fix-P0-5: dynamic plugin loader.

Loads :class:`BaseAgent` subclasses from a Python source file at
runtime — no process restart required.  The loader is intentionally
narrow in scope:

  * it imports the file as a synthetic module
  * it walks the module's namespace looking for concrete
    :class:`BaseAgent` subclasses
  * it registers each subclass under the slug returned by
    :meth:`BaseAgent.get_agent_type_slug`, falling back to the
    subclass' ``__plugin_name__`` attribute, then the class name
  * the caller is free to override the registration name via the
    optional ``name_overrides`` argument

Why not use ``importlib.reload``?  Reload has surprising semantics
(classes are re-bound but their *identity* may not match the registry
key).  A fresh import per call is simpler and matches the use case
("drop a new file in /plugins, call ``load_plugin`` once").

The loader refuses to import files that:
  * do not exist
  * do not contain any :class:`BaseAgent` subclass
  * raise an exception during import
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import types
from typing import Dict, Iterable, List, Optional, Tuple, Type

from .base import BaseAgent
from .registry import PluginRegistry

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────
def _is_concrete_agent(obj: object) -> bool:
    """True when ``obj`` is a concrete :class:`BaseAgent` subclass.

    Filters out the base class itself and any class that still has
    unimplemented abstract methods (defensive — the ABC machinery
    already prevents this, but we keep the check explicit so
    third-party files that import :class:`BaseAgent` for type hints
    don't accidentally get registered).
    """
    if not isinstance(obj, type):
        return False
    if not issubclass(obj, BaseAgent):
        return False
    if obj is BaseAgent:
        return False
    # Any unimplemented abstractmethod?  Then it's still abstract.
    if getattr(obj, "__abstractmethods__", None):
        return False
    return True


def _resolve_name(
    cls: Type[BaseAgent],
    explicit: Optional[str] = None,
) -> str:
    """Pick a registration name for ``cls``."""
    if explicit:
        return explicit
    # ``get_agent_type_slug`` is an instance method because it
    # reads ``self.agent_type``; the cheap path is to instantiate
    # once.  We don't memoize — the loader is not a hot path.
    slug = cls().get_agent_type_slug()
    if slug:
        return slug
    plugin_name = getattr(cls, "__plugin_name__", None)
    if isinstance(plugin_name, str) and plugin_name:
        return plugin_name
    return cls.__name__


def _discover_agents(module: types.ModuleType) -> List[Type[BaseAgent]]:
    """Return all concrete :class:`BaseAgent` subclasses in ``module``."""
    found: List[Type[BaseAgent]] = []
    seen: set = set()
    for name in dir(module):
        obj = getattr(module, name, None)
        if not _is_concrete_agent(obj):
            continue
        if obj in seen:
            continue
        seen.add(obj)
        found.append(obj)
    return found


# ── Public API ─────────────────────────────────────────────────────────────
def load_plugin(
    path: str,
    *,
    registry: Optional[PluginRegistry] = None,
    name_overrides: Optional[Dict[str, str]] = None,
    module_name: Optional[str] = None,
) -> List[str]:
    """Import a Python file and register every :class:`BaseAgent` it
    defines into ``registry``.

    Args:
        path: Absolute or relative path to a ``.py`` file.  Must
                exist and be readable.
        registry: The :class:`PluginRegistry` to register into.
                Defaults to the process-wide singleton.
        name_overrides: Optional ``{class_name: registration_name}``
                map.  Useful when the file declares the same class
                name as a built-in but with a different behaviour.
        module_name: Optional synthetic module name.  When unset,
                the loader derives a stable name from the file path.

    Returns:
        The list of registration names that were successfully added.

    Raises:
        FileNotFoundError: ``path`` does not exist.
        ValueError: ``path`` is not a ``.py`` file.
        RuntimeError: the file imported OK but defined no
                :class:`BaseAgent` subclass.
        ImportError: the file raised during import (re-raised with
                the original traceback attached).
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"plugin file not found: {path}")
    if not path.endswith(".py"):
        raise ValueError(f"plugin path must be a .py file: {path}")

    # NOTE: do not use ``registry or ...`` — an empty PluginRegistry
    # defines ``__len__`` which makes the instance falsy when empty,
    # so a freshly-reset registry would be silently replaced by the
    # global singleton.  Use ``is not None`` instead.
    reg = registry if registry is not None else PluginRegistry.get_registry()
    overrides = name_overrides if name_overrides is not None else {}

    # Derive a stable synthetic module name from the absolute path.
    if module_name is None:
        abs_path = os.path.abspath(path)
        # Drop the .py suffix + replace path separators + dedupe
        # across repeated loads of the same file
        stem = os.path.splitext(os.path.basename(abs_path))[0]
        module_name = f"imdf_agent_plugin_{stem}_{hash(abs_path) & 0xffffff:06x}"

    # Allow re-loading the same file: drop any prior version of the
    # synthetic module so ``importlib`` actually re-executes it.
    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover — defensive
        raise ImportError(f"could not build import spec for {path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        # Roll back the synthetic module registration so future
        # ``import`` calls don't see a half-loaded module.
        sys.modules.pop(module_name, None)
        raise ImportError(f"plugin import failed for {path!r}: {exc}") from exc

    agents = _discover_agents(module)
    if not agents:
        raise RuntimeError(
            f"plugin {path!r} defines no concrete BaseAgent subclass"
        )

    registered: List[str] = []
    # Pre-compute the per-class explicit override keys.  We accept
    # both the class name and the agent_type slug as keys, since the
    # caller may not know which one the loader will use.
    for cls in agents:
        slug = cls().get_agent_type_slug()
        candidates = (cls.__name__, slug) if slug else (cls.__name__,)
        explicit = None
        for cand in candidates:
            if cand in overrides:
                explicit = overrides[cand]
                break
        name = _resolve_name(cls, explicit=explicit)
        reg.register(name, cls, overwrite=True)
        registered.append(name)
        logger.info(
            "load_plugin: registered %s -> %s from %s",
            name, cls.__name__, path,
        )
    return registered


def load_plugins(
    paths: Iterable[str],
    *,
    registry: Optional[PluginRegistry] = None,
    name_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, List[str]]:
    """Convenience wrapper around :func:`load_plugin` for batch loads.

    Returns a ``{path: registered_names}`` map.  Continues past
    individual plugin failures (logging them) and returns the
    successful registrations; raises only when *every* plugin
    fails.
    """
    reg = registry or PluginRegistry.get_registry()
    out: Dict[str, List[str]] = {}
    failures: List[Tuple[str, str]] = []
    for p in paths:
        try:
            out[p] = load_plugin(p, registry=reg, name_overrides=name_overrides)
        except Exception as exc:  # noqa: BLE001
            logger.warning("load_plugin(%s) failed: %s", p, exc)
            failures.append((p, str(exc)))
    if failures and not out:
        # Every plugin failed — surface the first error so the
        # caller gets a meaningful traceback.
        path, msg = failures[0]
        raise RuntimeError(f"all plugin loads failed; first error: {path}: {msg}")
    return out


__all__ = ["load_plugin", "load_plugins"]
