"""
test_theme_toggle.py
P0-8 verification — theme store (Pinia) source-level checks.

The theme store is implemented in src/stores/theme.ts and the toggle
button is in src/layouts/DefaultLayout.vue. We verify the contracts
that make the UI work without launching a real browser:

  - localStorage key is 'vdp-theme' (NOT imdf.* like the rest of the
    project, per the P0-8 task spec)
  - The store exposes a cycle() function
  - The store applies data-theme to <html>
  - DefaultLayout.vue binds a button to cycle() with class 'theme-toggle'
"""
import re
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parents[2]
THEME_TS = FRONTEND_ROOT / "src" / "stores" / "theme.ts"
LAYOUT_VUE = FRONTEND_ROOT / "src" / "layouts" / "DefaultLayout.vue"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_theme_store_uses_vdp_theme_storage_key():
    src = _read(THEME_TS)
    assert "vdp-theme" in src, "STORAGE_KEY must be 'vdp-theme'"
    # Must NOT use imdf.* like the rest of the project.
    assert "imdf.theme" not in src, "Theme store leaked imdf.* namespace"


def test_theme_store_exposes_cycle():
    src = _read(THEME_TS)
    assert "function cycle" in src or "cycle:" in src or "cycle()" in src, \
        "store must expose cycle() function"
    # light → dark → auto → light rotation
    assert "'light'" in src and "'dark'" in src and "'auto'" in src, \
        "store must know all three modes"


def test_theme_store_applies_data_theme_attribute():
    src = _read(THEME_TS)
    assert "data-theme" in src, "store must set data-theme on <html>"


def test_default_layout_has_theme_toggle_button():
    src = _read(LAYOUT_VUE)
    # Look for either .theme-toggle class or a NButton that calls cycle()
    assert ".theme-toggle" in src or "theme-toggle" in src or "themeStore.cycle" in src, \
        "DefaultLayout must render a theme toggle button bound to cycle()"


def test_default_layout_imports_theme_store():
    src = _read(LAYOUT_VUE)
    assert "useThemeStore" in src or "stores/theme" in src, \
        "DefaultLayout must import useThemeStore"


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
