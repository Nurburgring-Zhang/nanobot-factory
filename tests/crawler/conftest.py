"""pytest conftest for tests/crawler/ (P21 R3 extreme boundary).

- Inject backend/ into sys.path (mirrors tests/conftest.py).
- Reset default crawler engine between tests for isolation.
- Provide a session-scoped mock for environment isolation.

Hard rules: do NOT mutate any source files. The conftest only configures
sys.path, env vars, and module-level singletons.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# --- 1) Path injection (matches root tests/conftest.py) -------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
_IMDF_DIR = _BACKEND_DIR / "imdf"

_backend_path = str(_BACKEND_DIR)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

for sub in ("common", "engines", "api"):
    p = _IMDF_DIR / sub
    if p.exists() and (p / "__init__.py").exists():
        sp = str(p)
        if sp in sys.path:
            sys.path.remove(sp)
        sys.path.insert(0, sp)


# --- 2) Crawler engine reset between tests --------------------------------
@pytest.fixture(autouse=True)
def _reset_crawler_singletons(monkeypatch):
    """Reset the default CrawlerEngine singleton before/after each test.

    Some modules (registry, channels) hold a process-level default engine.
    Without reset, tests would share state and race conditions.
    """
    # Default: force-mock for safety, no production network
    monkeypatch.setenv("CRAWLER_FORCE_MOCK", "1")
    monkeypatch.setenv("CRAWLER_DEFAULT_MOCK", "1")
    monkeypatch.setenv("CRAWLER_PRODUCTION_REAL_NETWORK", "0")

    # Lazy import to avoid premature init during conftest load
    from imdf.crawler import registry

    registry.reset_default_engine()
    yield
    registry.reset_default_engine()


# --- 3) No-network / sandbox env ------------------------------------------
@pytest.fixture
def no_network(monkeypatch):
    """Block any real network access in the test process.

    We override socket.socket to refuse non-loopback connections. This is a
    defense-in-depth: if a test accidentally bypasses mocks, the connection
    will fail loudly instead of leaking to the real internet.
    """
    import socket as _socket

    _original_socket = _socket.socket

    def _guarded(*args, **kwargs):
        s = _original_socket(*args, **kwargs)
        _orig_connect = s.connect

        def _guarded_connect(addr):
            host = addr[0] if isinstance(addr, tuple) else addr
            # Allow localhost (some tests rely on local sockets for utils)
            if host in ("127.0.0.1", "::1", "localhost"):
                return _orig_connect(addr)
            raise OSError(f"no_network fixture: blocked connection to {host}")

        s.connect = _guarded_connect
        return s

    monkeypatch.setattr(_socket, "socket", _guarded)
    return _guarded
