"""Conftest for the crawl skill tests.

Boots the path so ``from backend.imdf.skills.crawl.X import Y`` works
without dragging in the (currently broken in this sandbox)
``backend.imdf.skills.registry`` module.  Strategy:

  1. Put the backend root and the imdf root on sys.path.
  2. Patch ``sys.modules['backend.imdf.skills'].__path__`` so it
     remains a real package — Python therefore happily resolves
     ``backend.imdf.skills.crawl`` and runs our ``crawl/__init__.py``
     (which only imports ``backend.skills.legacy``, a working module).
"""

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent.parent.parent
_IMDF = _BACKEND / "imdf"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_IMDF) not in sys.path:
    sys.path.insert(0, str(_IMDF))


def pytest_configure(config):
    # Force offline mode so no live HTTP is attempted.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("NANOBOT_FORCE_OFFLINE", "1")

    # Pre-load backend.imdf.skills once and force ``__path__`` so Python
    # treats it as a package even though its own ``__init__.py`` imports
    # a broken-in-this-sandbox registry chain.
    import importlib

    backend_pkg = "backend.imdf.skills"

    if backend_pkg in sys.modules and getattr(
        sys.modules[backend_pkg], "__path__", None
    ):
        return  # already a real package

    import types
    pkg = types.ModuleType(backend_pkg)
    pkg.__path__ = [str(_IMDF / "skills")]  # type: ignore[attr-defined]
    pkg.__package__ = backend_pkg
    sys.modules[backend_pkg] = pkg