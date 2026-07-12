#!/usr/bin/env python3
"""Count namespaces and leaf keys in en-US.ts."""
import re

with open('frontend-v2/src/locales/en-US.ts', 'r', encoding='utf-8') as f:
    content = f.read()

ns_pattern = re.compile(r'^  (\w+):\s*\{', re.MULTILINE)
ns_matches = list(ns_pattern.finditer(content))
print(f'Total namespaces (en-US): {len(ns_matches)}')

total_leaves = 0
for m in ns_matches:
    ns_name = m.group(1)
    start = m.end()
    depth = 1
    pos = start
    while pos < len(content) and depth > 0:
        ch = content[pos]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        pos += 1
    ns_content = content[start:pos-1]
    # Count ALL string values (leaf nodes)
    leaf_pattern = re.compile(r":\s*'([^']*(?:\\'[^']*)*)'", re.MULTILINE)
    leaves = leaf_pattern.findall(ns_content)
    total_leaves += len(leaves)
    print(f'{ns_name}: {len(leaves)} leaf keys')

print(f'\nTotal leaf string values: {total_leaves}')