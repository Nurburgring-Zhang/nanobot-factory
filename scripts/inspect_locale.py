#!/usr/bin/env python3
"""Inspect en-US.ts structure."""
import re

with open('frontend-v2/src/locales/en-US.ts', 'r', encoding='utf-8') as f:
    content = f.read()

# Find sample lines with placeholders
samples = re.findall(r"^\s{4}\w+:\s*'[^']*\{[^}]+\}[^']*'", content, re.MULTILINE)
print(f"Placeholder samples: {len(samples)}")
for s in samples[:10]:
    print(s)

print('\n--- Template literal samples ---')
templates = re.findall(r'^\s{4}\w+:\s*`[^`]+`', content, re.MULTILINE)
print(f"Template literal samples: {len(templates)}")
for t in templates[:5]:
    print(t)

print('\n--- Special chars ---')
specials = re.findall(r"^\s{4}\w+:\s*'[^']*\\\\[^']*'", content, re.MULTILINE)
print(f"Escaped char samples: {len(specials)}")
for s in specials[:5]:
    print(s)

# Check for nested objects (one level deep)
nested = re.findall(r'^\s{4}\w+:\s*\{$', content, re.MULTILINE)
print(f"\nNested objects at depth 2: {len(nested)}")

# Check for arrays
arrays = re.findall(r'^\s{4}\w+:\s*\[', content, re.MULTILINE)
print(f"Arrays at depth 2: {len(arrays)}")

# Check closing braces of namespace (depth 1)
nss = re.findall(r'^\s{2}\w+:\s*\{$', content, re.MULTILINE)
print(f"Namespaces (depth 1): {len(nss)}")

# Total line count
print(f"\nTotal lines: {len(content.splitlines())}")