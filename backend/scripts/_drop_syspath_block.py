"""Drop the redundant sys.path bootstrap block in refactored services.

After P4-1-W1 the ``create_app(...)`` factory already inserts
``backend/`` into ``sys.path``. The leftover block

    import os, sys
    from contextlib import asynccontextmanager
    from pathlib import Path

    _BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))

is now dead code. Removing it shrinks each service ``main.py`` by ~8
lines and ~200 bytes. We keep the ``from contextlib import
asynccontextmanager`` import because the lifespan decorator still needs
it.

We also collapse runs of 3+ blank lines into a single blank line.
"""
from __future__ import annotations

import re
from pathlib import Path

SERVICES_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory\backend\services")
MARKER = "# P4-1-W1: migrated to backend.common"

# Match:
#   import os
#   import sys
#   from contextlib import asynccontextmanager
#   from pathlib import Path
#
#   _BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
#   if str(_BACKEND_ROOT) not in sys.path:
#       sys.path.insert(0, str(_BACKEND_ROOT))
#   <blank>
SYSPATH_BLOCK_RE = re.compile(
    r"import os\n"
    r"import sys\n"
    r"from contextlib import asynccontextmanager\n"
    r"from pathlib import Path\n\n"
    r"_BACKEND_ROOT = Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent\n"
    r"if str\(_BACKEND_ROOT\) not in sys\.path:\n"
    r"    sys\.path\.insert\(0, str\(_BACKEND_ROOT\)\)\n"
    r"\n",
)


def fix_file(main_py: Path) -> tuple[bool, int]:
    text = main_py.read_text(encoding="utf-8")

    if MARKER not in text:
        return False, 0

    new_text, n = SYSPATH_BLOCK_RE.subn("", text)

    # Collapse 3+ blank lines to a single blank line
    new_text2 = re.sub(r"\n{3,}", "\n\n", new_text)

    if new_text2 == text:
        return False, 0

    main_py.write_text(new_text2, encoding="utf-8")
    return True, len(text) - len(new_text2)


def main() -> int:
    n_changed = 0
    total_saved = 0
    for service_dir in sorted(SERVICES_ROOT.iterdir()):
        if not service_dir.is_dir():
            continue
        main_py = service_dir / "main.py"
        if not main_py.exists():
            continue
        try:
            changed, saved = fix_file(main_py)
            if changed:
                n_changed += 1
                total_saved += saved
                print(f"  + {service_dir.name}: saved {saved} bytes")
        except Exception as exc:
            print(f"  ! {service_dir.name}: ERROR {exc!r}")
    print(f"\nCleaned {n_changed} files, total saved {total_saved} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())