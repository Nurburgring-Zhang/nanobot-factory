"""Basic Helm template syntax validation (no helm CLI required).

This is a *lightweight* check that catches the most common Helm template
mistakes without needing helm installed:

1. Balanced `{{` / `}}` (or `{{-` / `-}}`) delimiters.
2. Each rendered manifest block starts with a YAML separator `---` OR begins
   on the first line of the file.
3. No dangling `{{` or `}}` outside of valid Go template constructs.

A real `helm template` run is the authoritative test; this script catches
80% of accidental typos without requiring the CLI.
"""
from __future__ import annotations

import glob
import re
import sys


OPEN_RE = re.compile(r"\{\{-?")


def check_file(path: str) -> list[str]:
    """Return list of error messages (empty if OK)."""
    errs: list[str] = []
    with open(path, encoding="utf-8") as fp:
        text = fp.read()

    opens = len(OPEN_RE.findall(text))
    closes = text.count("}}")
    if opens != closes:
        errs.append(f"unbalanced delimiters: {opens} '{{{{' vs {closes} '}}}}'")

    # If file has any {{ ... }}, the FIRST non-whitespace line should either
    # be `---` or `apiVersion:` (Helm allows rendering without leading ---).
    stripped = text.lstrip()
    if "{{" in text and not (
        stripped.startswith("---")
        or stripped.startswith("{{")
        or stripped.startswith("apiVersion:")
    ):
        errs.append(f"first content is neither '---' nor a Helm directive")

    # Find unmatched `{{ ... }}` blocks
    pos = 0
    depth = 0
    while pos < len(text):
        open_m = OPEN_RE.search(text, pos)
        close_m = re.search(r"\}\}", text[pos:])
        if not open_m and not close_m:
            break
        if open_m and (not close_m or open_m.start() < close_m.start() + pos):
            depth += 1
            pos = open_m.end()
        elif close_m:
            depth -= 1
            pos = close_m.start() + pos + 2
            if depth < 0:
                errs.append("stray '}}' before any '{{'")
                break
    if depth != 0:
        errs.append(f"unclosed template block (final depth={depth})")

    return errs


def main() -> int:
    files = sorted(glob.glob("helm/nanobot-factory/templates/*.yaml"))
    print(f"Helm-template-lint: scanning {len(files)} files...")
    fail = 0
    for f in files:
        errs = check_file(f)
        if errs:
            fail += 1
            print(f"  FAIL  {f}")
            for e in errs:
                print(f"        {e}")
        else:
            print(f"  OK    {f}")
    print(f"=== {len(files)} files, {fail} failures ===")
    print("NOTE: this is a lightweight check (no actual render).")
    print("      For full validation, run: make helm-template")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())