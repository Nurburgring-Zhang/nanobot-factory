"""Standalone runner — executes the multimodal test functions directly.

Avoids pytest's collection phase which can take 60-120s on the nanobot-factory
repo (lots of unrelated conftest.py / heavy imports in testpaths).

For each test function, we look at its signature: if it takes ``client`` (the
standard pytest fixture in these test files), we wire a TestClient manually.

A hard 8-second timeout protects against agents/tests that block on memory
DB I/O.  Tests that exceed the budget are marked TIMEOUT.
"""
from __future__ import annotations

import importlib
import inspect
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
TESTS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(TESTS_ROOT))

MODULES = [
    "tests.multimodal.test_understanding",
    "tests.multimodal.test_12service",
    "tests.multimodal.test_generation",
    "tests.multimodal.test_agent",
]

PER_TEST_TIMEOUT = 8  # seconds


def _make_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from imdf.multimodal.routes import build_router, build_agent_router
    app = FastAPI()
    app.include_router(build_router())
    app.include_router(build_agent_router())
    return TestClient(app)


def _run_with_timeout(fn: Callable[..., Any], kwargs: Dict[str, Any], timeout: float) -> Tuple[str, str]:
    """Run fn(**kwargs) on a thread with a hard timeout.  Returns (status, msg)."""
    result: Dict[str, Any] = {"done": False, "exc": None, "tb": ""}

    def _target():
        try:
            fn(**kwargs)
            result["done"] = True
        except BaseException as exc:
            result["exc"] = exc
            result["tb"] = traceback.format_exc()

    th = threading.Thread(target=_target, daemon=True)
    th.start()
    th.join(timeout=timeout)
    if th.is_alive():
        return "TIMEOUT", f"exceeded {timeout}s"
    if result["exc"] is not None:
        return "FAIL", result["tb"]
    return "PASS", ""


def main() -> int:
    total = 0
    passed = 0
    failed: List[str] = []
    for modname in MODULES:
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:
            print(f"[collect FAIL] {modname}: {exc}")
            traceback.print_exc()
            failed.append(modname)
            continue
        tests = [
            (name, fn) for name, fn in vars(mod).items()
            if name.startswith("test_") and callable(fn)
        ]
        for name, fn in tests:
            total += 1
            sig = inspect.signature(fn)
            kwargs: Dict[str, Any] = {}
            if "client" in sig.parameters:
                kwargs["client"] = _make_client()
            status, msg = _run_with_timeout(fn, kwargs, PER_TEST_TIMEOUT)
            if status == "PASS":
                print(f"  PASS {modname}.{name}")
                passed += 1
            elif status == "TIMEOUT":
                print(f"  TIMEOUT {modname}.{name}: {msg}")
                failed.append(f"{modname}.{name}")
            else:
                print(f"  FAIL {modname}.{name}\n{msg}")
                failed.append(f"{modname}.{name}")
    print(f"\n=== {passed}/{total} passed, {len(failed)} failed ===")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  - {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())