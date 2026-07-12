import re, glob
from pathlib import Path

ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2')

# Files are 1-line corrupted? Check line count
corrupted_files = set()
for f in glob.glob(str(ROOT / 'src' / 'views' / '**' / '*.vue'), recursive=True) + glob.glob(str(ROOT / 'src' / 'components' / '**' / '*.vue'), recursive=True):
    text = open(f, encoding='utf-8').read()
    if text.count('\n') < 5:
        corrupted_files.add(f)

print(f'Corrupted files (≤5 lines): {len(corrupted_files)}')
for f in sorted(corrupted_files):
    print(f'  {f.split(chr(92))[-1]}  size={len(open(f,encoding="utf-8").read())}')

# Now extract t() keys per file and tally corrupted vs not
all_keys_corrupted = set()
all_keys_normal = set()
for f in glob.glob(str(ROOT / 'src' / 'views' / '**' / '*.vue'), recursive=True) + glob.glob(str(ROOT / 'src' / 'components' / '**' / '*.vue'), recursive=True):
    text = open(f, encoding='utf-8').read()
    keys = set()
    for m in re.finditer(r"\bt\(['\"]([^'\"]+)['\"]", text):
        keys.add(m.group(1))
    if f in corrupted_files:
        all_keys_corrupted.update(keys)
    else:
        all_keys_normal.update(keys)

print(f'\nKeys from corrupted files: {len(all_keys_corrupted)}')
print(f'Keys from normal files: {len(all_keys_normal)}')

# Now flatten zh-CN locale
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
        j = colon
        while j < n and text[j] in ' \t\r\n':
            j += 1
        full_key = f"{prefix}.{key}" if prefix else key
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
            sub = flatten_ts_object(inner, full_key)
            out.update(sub)
            i = j + 1
        else:
            out.add(full_key)
            i = colon
    return out

zh_text = (ROOT / 'src' / 'locales' / 'zh-CN.ts').read_text(encoding='utf-8')
zh_keys = flatten_ts_object(zh_text)
print(f'\nzh-CN keys total: {len(zh_keys)}')

# Now compute missing keys for each tier
missing_corrupted = sorted(all_keys_corrupted - zh_keys)
missing_normal = sorted(all_keys_normal - zh_keys)
print(f'\n=== Missing in zh-CN from corrupted files: {len(missing_corrupted)} ===')
for k in missing_corrupted[:30]:
    print(f'  {k}')
print(f'\n=== Missing in zh-CN from normal files: {len(missing_normal)} ===')
for k in missing_normal[:80]:
    print(f'  {k}')