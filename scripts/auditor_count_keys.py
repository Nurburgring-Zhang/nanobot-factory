"""Count keys per namespace in zh-CN.ts and en-US.ts"""
import re
import sys

def parse_locale(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Find each top-level namespace block
    ns_blocks = []
    # Match "  nsName: {" at the start of a line
    i = 0
    while i < len(content):
        m = re.search(r'^  (\w+):\s*\{', content[i:], re.MULTILINE)
        if not m:
            break
        ns_name = m.group(1)
        # Skip if it's already inside a nested block (shouldn't happen for top-level)
        start_pos = i + m.start()
        brace_pos = i + m.end() - 1
        depth = 1
        j = brace_pos + 1
        while j < len(content) and depth > 0:
            if content[j] == '{':
                depth += 1
            elif content[j] == '}':
                depth -= 1
            j += 1
        block = content[brace_pos+1:j-1]
        ns_blocks.append((ns_name, block))
        i = j
    return ns_blocks

def count_top_level_keys(block):
    """Count keys at 4-space indent level only (top-level within a namespace)"""
    keys = []
    depth = 0
    for line in block.split('\n'):
        stripped = line.split('//')[0]  # strip line comments
        # Count braces
        opens = stripped.count('{')
        closes = stripped.count('}')
        # Match a top-level key (4-space indent + word + colon)
        m = re.match(r'^    (\w+)\s*:', stripped)
        if m and depth == 0:
            keys.append(m.group(1))
        depth += opens - closes
        if depth < 0:
            depth = 0
    return keys

def analyze(filepath, label):
    print(f'=== {label}: {filepath} ===')
    ns_blocks = parse_locale(filepath)
    print(f'Namespaces: {len(ns_blocks)}')
    print()
    total = 0
    for ns, block in ns_blocks:
        keys = count_top_level_keys(block)
        total += len(keys)
        print(f'  {ns:25s}: {len(keys):4d} keys')
    print(f'  {"TOTAL":25s}: {total:4d} keys')
    return [(ns, count_top_level_keys(block)) for ns, block in ns_blocks]

zh = analyze(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales\zh-CN.ts', 'zh-CN')
en = analyze(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales\en-US.ts', 'en-US')

# Compare parity
print()
print('=== Key Parity Check ===')
zh_map = {ns: set(keys) for ns, keys in zh}
en_map = {ns: set(keys) for ns, keys in en}
all_ns = set(zh_map) | set(en_map)
issues = 0
for ns in sorted(all_ns):
    zh_keys = zh_map.get(ns, set())
    en_keys = en_map.get(ns, set())
    only_zh = zh_keys - en_keys
    only_en = en_keys - zh_keys
    if only_zh:
        print(f'  {ns}: ONLY IN zh-CN ({len(only_zh)}): {sorted(only_zh)[:10]}')
        issues += len(only_zh)
    if only_en:
        print(f'  {ns}: ONLY IN en-US ({len(only_en)}): {sorted(only_en)[:10]}')
        issues += len(only_en)
if issues == 0:
    print('  PARITY OK: 0 missing keys either side')
else:
    print(f'  PARITY ISSUES: {issues}')