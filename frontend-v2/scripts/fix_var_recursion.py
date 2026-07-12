"""Fix any recursive var(--app-*, var(--app-*, ...)) nesting across all
Vue files. Such nesting is broken CSS (and triggers Naive UI warnings)
so we collapse it to the deepest literal value.
"""
from pathlib import Path
import re

ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src')

# Match var(--app-<name>, var(--app-<name>, ... var(--app-<name>, #XXXXXX) ... ))
pattern = re.compile(
    r'var\(--app-(?P<name>[a-z]+),\s*var\(--app-(?P=name),\s*(?:var\(--app-(?P=name),\s*)*'
    r'#(?P<hex>[0-9a-fA-F]{3,8})\)+\s*\)'
)


def collapse(text: str) -> tuple[str, int]:
    def repl(m: re.Match) -> str:
        return f'#%s' % m.group('hex')
    new, n = pattern.subn(repl, text)
    return new, n


def main() -> None:
    total = 0
    files = list(ROOT.rglob('*.vue')) + list(ROOT.rglob('*.css'))
    for f in files:
        text = f.read_text(encoding='utf-8-sig')
        new, n = collapse(text)
        if n:
            print(f'  fixed {n} in {f.name}')
            total += n
            f.write_text('\ufeff' + new, encoding='utf-8')
    print(f'\nTotal: {total} recursive var nests collapsed')


if __name__ == '__main__':
    main()