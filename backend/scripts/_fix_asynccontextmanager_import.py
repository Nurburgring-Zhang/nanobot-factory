"""Fix missing ``asynccontextmanager`` import in refactored services.

The P4-1-W1 refactor script dropped the entire ``import os, sys,
asynccontextmanager, pathlib`` block; but some services still use the
``@asynccontextmanager`` decorator on their custom lifespan. Add the
missing import if a lifespan function uses it but the import isn't there.
"""
from __future__ import annotations

import re
from pathlib import Path

SERVICES_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory\backend\services")


def needs_import(text: str) -> bool:
    has_lifespan_decorator = bool(re.search(r"^@asynccontextmanager\s*$", text, re.MULTILINE))
    has_import = "from contextlib import asynccontextmanager" in text or "import asynccontextmanager" in text
    return has_lifespan_decorator and not has_import


def fix_file(main_py: Path) -> bool:
    text = main_py.read_text(encoding="utf-8")

    if not needs_import(text):
        return False

    # Insert the import right after the ``from common import ...`` line.
    new_import = "from contextlib import asynccontextmanager\n"
    text2 = re.sub(
        r"(from common import [^\n]+\n)",
        r"\1\n" + new_import,
        text,
        count=1,
    )

    if text2 == text:
        # fallback: insert right after the fastapi import if present
        text2 = re.sub(
            r"(from fastapi import FastAPI[^\n]*\n)",
            r"\1\n" + new_import,
            text,
            count=1,
        )

    if text2 == text:
        # last-ditch: insert at top after future-imports
        text2 = re.sub(
            r"(from __future__ import annotations\n)",
            r"\1\n" + new_import,
            text,
            count=1,
        )

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
                print(f"  + {service_dir.name}: added asynccontextmanager import")
        except Exception as exc:
            print(f"  ! {service_dir.name}: ERROR {exc!r}")
    print(f"\nFixed: {n_fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())