"""Check for duplicate values, very short values, placeholder values"""
import re
from collections import Counter

with open(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales\zh-CN.ts', 'r', encoding='utf-8') as f:
    content = f.read()

# Find namespace blocks
ns_blocks = []
for m in re.finditer(r'^  (\w+): \{', content, re.MULTILINE):
    ns_name = m.group(1)
    pos = m.end() - 1  # position of '{'
    depth = 1
    j = pos + 1
    while j < len(content) and depth > 0:
        if content[j] == '{':
            depth += 1
        elif content[j] == '}':
            depth -= 1
        j += 1
    block = content[pos+1:j-1]
    ns_blocks.append((ns_name, block))

# For each namespace, collect (key, value) pairs
print('=== Per-namespace value analysis ===')
total_issues = 0
for ns, block in ns_blocks:
    keys = []
    values = []
    for line in block.split('\n'):
        # Strip comments
        clean = re.sub(r'//.*$', '', line)
        # Match: '    keyName: value' or '    keyName: "value"' or '    keyName: \`...\`
        m = re.match(r'^    (\w+)\s*:\s*(.*)$', clean)
        if m:
            k, v = m.group(1), m.group(2).strip().rstrip(',').strip()
            keys.append(k)
            values.append(v)
    # Find duplicate values (only within same namespace)
    vc = Counter(values)
    duplicates = {v: c for v, c in vc.items() if c > 1}
    # Find empty / placeholder values
    empty = [k for k, v in zip(keys, values) if not v or v in ("''", '""', '``', 'TODO', 'FIXME', '?')]
    # Find very short (1 char) values - likely typos
    very_short = [k for k, v in zip(keys, values) if len(v.strip("'\"`")) <= 1 and v.strip("'\"`")]
    print(f'\n{ns}: {len(keys)} keys, {len(duplicates)} duplicate values, {len(empty)} empty, {len(very_short)} very_short')
    if duplicates:
        for v, c in list(duplicates.items())[:5]:
            print(f'  dup val ({c}x): {v!r}')
    if empty:
        for k in empty[:5]:
            print(f'  EMPTY: {k}')
    if very_short:
        for k in very_short[:5]:
            print(f'  VERY SHORT: {k}')
    total_issues += len(duplicates) + len(empty) + len(very_short)

print(f'\n=== TOTAL ISSUES: {total_issues} ===')