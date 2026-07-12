"""Spot check translation quality: compare zh-CN vs en-US for new namespaces"""
import re

def load_keys(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Find namespace blocks
    ns_blocks = {}
    for m in re.finditer(r'^  (\w+): \{', content, re.MULTILINE):
        ns = m.group(1)
        pos = m.end() - 1
        depth = 1
        j = pos + 1
        while j < len(content) and depth > 0:
            if content[j] == '{':
                depth += 1
            elif content[j] == '}':
                depth -= 1
            j += 1
        block = content[pos+1:j-1]
        keys = {}
        for line in block.split('\n'):
            clean = re.sub(r'//.*$', '', line)
            m = re.match(r'^    (\w+)\s*:\s*(.*)$', clean)
            if m:
                k, v = m.group(1), m.group(2).strip().rstrip(',').strip()
                keys[k] = v
        ns_blocks[ns] = keys
    return ns_blocks

zh = load_keys(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales\zh-CN.ts')
en = load_keys(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales\en-US.ts')

# Spot check 10 random keys from each new namespace
import random
random.seed(42)
for ns in ['menu', 'button', 'form', 'table']:
    if ns not in zh or ns not in en:
        print(f'{ns}: missing')
        continue
    keys = sorted(zh[ns].keys())
    sample = random.sample(keys, min(15, len(keys)))
    print(f'\n=== {ns} spot check ===')
    for k in sample:
        print(f'  {k:35s}: zh={zh[ns][k][:40]:40s}  en={en[ns][k][:40]}')

# Check for IDENTICAL values (placeholder translations)
print('\n=== Identical zh-CN/en-US strings (likely untranslated placeholders) ===')
for ns in zh:
    if ns not in en:
        continue
    identical = []
    for k in zh[ns]:
        if zh[ns][k] == en[ns][k]:
            identical.append((k, zh[ns][k]))
    if identical:
        print(f'\n{ns}: {len(identical)} identical strings')
        for k, v in identical[:5]:
            print(f'  {k:30s}: {v[:60]}')