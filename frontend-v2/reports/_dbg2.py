import re
from pathlib import Path
ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2')
text = (ROOT / 'src' / 'locales' / 'zh-CN.ts').read_text(encoding='utf-8')

def flatten_ts_object(text, prefix=''):
    out = set()
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    key_re = re.compile(r"(?:['\"]([a-zA-Z0-9_.\-]+)['\"]|([a-zA-Z_][a-zA-Z0-9_]*))\s*:")
    i = 0
    n = len(text)
    while i < n:
        m = key_re.search(text, i)
        if not m:
            break
        key = m.group(1) or m.group(2)
        colon = m.end()
        print(f"i={i} key={key!r} colon={colon}")
        if i > 100:
            break
        j = colon
        while j < n and text[j] in ' \t\r\n':
            j += 1
        if j < n and text[j] == '{':
            depth = 0
            start = j
            while j < n:
                c = text[j]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        break
                elif c in '"\'':
                    quote = c
                    j += 1
                    while j < n and text[j] != quote:
                        if text[j] == '\\':
                            j += 2
                            continue
                        j += 1
                j += 1
            inner = text[start+1:j]
            sub = flatten_ts_object(inner, key if not prefix else f"{prefix}.{key}")
            out.update(sub)
            i = j + 1
        else:
            i = colon
    return out

ks = flatten_ts_object(text)
print('keys found:', len(ks))
print('sample:', list(ks)[:30])