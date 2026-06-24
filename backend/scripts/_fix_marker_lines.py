"""Fix the broken P4-1-W1 refactor marker inserted by the previous script.

Two issues to fix in each main.py:
  1. ``P4-1-W1: refactored — see backend/common/ for the shared library.``
     is a bare statement (no `#` prefix). Python parses ``—`` as an
     identifier and explodes with ``SyntaxError: invalid character '—'``.
     Fix: prefix with ``#``.

  2. Some em-dashes may have been written as ``��`` (mojibake). Fix:
     replace any ``��`` inside those marker lines with ``—``.

Idempotent: re-running is a no-op.
"""
from __future__ import annotations

import re
from pathlib import Path

SERVICES_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory\backend\services")
BROKEN_LINE_RE = re.compile(
    r"^P4-1-W1: refactored .*?see backend/common/ for the shared library\.\s*$",
    re.MULTILINE,
)


def fix_file(main_py: Path) -> bool:
    text = main_py.read_text(encoding="utf-8")

    if not BROKEN_LINE_RE.search(text):
        return False

    # Replace the broken line with a properly commented one.
    # Use ASCII 'see' to avoid any further encoding surprises; we can
    # also use the literal em-dash by writing it as a chr() escape.
    em = "\u2014"  # —
    new_line = f"# P4-1-W1: refactored {em} see backend/common/ for the shared library."
    text2 = BROKEN_LINE_RE.sub(new_line, text)

    if text2 == text:
        return False

    main_py.write_text(text2, encoding="utf-8")
    return True


def main() -> int:
    n_fixed = 0
    for service_dir in sorted(SERVICES_ROOT.iterdir()):
        if not service_dir.is_dir():
            continue
        main_py = service_dir / "main.py"
        if not main_py.exists():
            continue
        try:
            changed = fix_file(main_py)
            if changed:
                n_fixed += 1
                print(f"  + {service_dir.name}: fixed")
            else:
                print(f"  - {service_dir.name}: already ok or no marker")
        except Exception as exc:
            print(f"  ! {service_dir.name}: ERROR {exc!r}")
    print(f"\nFixed: {n_fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())