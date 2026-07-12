#!/usr/bin/env python3
"""Validate generated locale files."""
import re
import os

LOCALE_DIR = 'frontend-v2/src/locales'

# Reference structure
with open(os.path.join(LOCALE_DIR, 'en-US.ts'), 'r', encoding='utf-8') as f:
    en_content = f.read()

# Get the namespaces in en-US
en_ns_pattern = re.findall(r'^\s{2}(\w+):\s*\{', en_content, re.MULTILINE)
print(f"en-US.ts namespaces: {len(en_ns_pattern)}")

# Compare each new locale
for code in ['zh-CN', 'en-US', 'ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA']:
    path = os.path.join(LOCALE_DIR, f'{code}.ts')
    if not os.path.exists(path):
        print(f"{code}: FILE NOT FOUND")
        continue
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Count namespaces
    nss = re.findall(r'^\s{2}(\w+):\s*\{', content, re.MULTILINE)

    # Count leaf strings (count '...\:' patterns at depth 4)
    leaf_pattern = re.compile(r"^\s{4}(\w+):\s*'([^']*(?:\\'[^']*)*)'", re.MULTILINE)
    leaves = leaf_pattern.findall(content)
    leaf_keys = [k for k, v in leaves]

    # Verify namespace parity with en-US (should be >=)
    en_set = set(en_ns_pattern)
    code_set = set(nss)
    missing = en_set - code_set
    extra = code_set - en_set

    print(f"{code}: {len(nss)} namespaces, {len(leaves)} leaf keys")
    if missing:
        print(f"  MISSING namespaces vs en-US: {missing}")
    if extra:
        print(f"  EXTRA namespaces: {extra}")