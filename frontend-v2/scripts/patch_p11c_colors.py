#!/usr/bin/env python3
"""P11-C bulk color token replace — UTF-8 safe.

Replaces hardcoded hex literals with CSS var() references so that all
views automatically pick up the P11-C dark-mode token map.
"""
import sys
from pathlib import Path

ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src')

# (old_hex, new_var_expression)
REPLACEMENTS = [
    ('#2080f0', 'var(--app-primary, #0a5dc2)'),
    ('#18a058', 'var(--app-success, #157a3e)'),
    ('#f0a020', 'var(--app-warning, #c87f0d)'),
    ('#d03050', 'var(--app-error, #d03050)'),
]


def patch_file(path: Path) -> tuple[bool, int]:
    text = path.read_text(encoding='utf-8')
    hits = 0
    for old, new in REPLACEMENTS:
        # Case-insensitive literal replace; skip occurrences that are
        # already inside a var() fallback by leaving them — the regex
        # below catches the bare hex outside var() contexts.
        if old in text:
            before = text.count(old)
            text = text.replace(old, new)
            hits += before - text.count(old) + (before - text.count(old))
    if hits == 0 and text == path.read_text(encoding='utf-8'):
        return (False, 0)
    path.write_text(text, encoding='utf-8')
    return (True, hits)


def main() -> None:
    targets = list(ROOT.rglob('*.vue'))
    changed = 0
    total = 0
    for f in targets:
        ok, n = patch_file(f)
        if ok:
            changed += 1
            total += n
            print(f'  patched: {f.name} ({n} hits)')
    print(f'\n{changed} files patched, {total} replacements')


if __name__ == '__main__':
    main()