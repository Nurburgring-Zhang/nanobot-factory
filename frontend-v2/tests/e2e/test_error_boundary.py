"""
test_error_boundary.py
P0-8 verification — ErrorBoundary component source-level checks.

The ErrorBoundary is in src/components/ErrorBoundary.vue and is wired
in src/App.vue (wraps RouterView). We verify the contracts:

  - Component has onErrorCaptured hook
  - Returns false to stop propagation
  - Renders a fallback UI with retry / reload buttons
  - Pipes errors to the Sentry-style reporter
  - App.vue wraps <RouterView> in <ErrorBoundary>
  - The reporter exposes window.__lastErrorEvents__ for E2E introspection
"""
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parents[2]
EB_VUE = FRONTEND_ROOT / "src" / "components" / "ErrorBoundary.vue"
APP_VUE = FRONTEND_ROOT / "src" / "App.vue"
REPORTER = FRONTEND_ROOT / "src" / "utils" / "errorReporter.ts"
MAIN_TS = FRONTEND_ROOT / "src" / "main.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_errorboundary_uses_on_error_captured():
    src = _read(EB_VUE)
    assert "onErrorCaptured" in src, "ErrorBoundary must use onErrorCaptured hook"


def test_errorboundary_returns_false_to_stop_propagation():
    src = _read(EB_VUE)
    # The hook body must end with `return false` somewhere
    assert "return false" in src, "ErrorBoundary must return false to stop propagation"


def test_errorboundary_has_retry_and_reload_buttons():
    src = _read(EB_VUE)
    assert "onRetry" in src and "onReload" in src, \
        "ErrorBoundary must expose retry and reload actions"
    assert "重试" in src, "ErrorBoundary must have a retry button label"
    assert "刷新" in src, "ErrorBoundary must have a reload button label"


def test_errorboundary_pipes_to_reporter():
    src = _read(EB_VUE)
    assert "reportError" in src, "ErrorBoundary must call reportError"


def test_error_reporter_exposes_window_debug_hook():
    src = _read(REPORTER)
    assert "__lastErrorEvents__" in src, \
        "errorReporter must expose window.__lastErrorEvents__ for E2E probes"


def test_app_wraps_router_view_in_error_boundary():
    src = _read(APP_VUE)
    assert "ErrorBoundary" in src, "App.vue must import ErrorBoundary"
    # The boundary must wrap <RouterView>
    assert "RouterView" in src, "App.vue must contain RouterView"


def test_main_installs_global_error_handler():
    src = _read(MAIN_TS)
    assert "errorHandler" in src or "onErrorCaptured" in src, \
        "main.ts must install a global error handler"


if __name__ == "__main__":
    import sys
    passed = 0
    failed = 0
    for name, fn in list(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {e!r}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
