#!/usr/bin/env python3
"""Extract all $t() keys + cross-reference locale files for nanobot-factory frontend-v2."""
import re
import glob
import os
import json
import sys
from pathlib import Path

ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2')
OUT = ROOT / 'reports'

# 1. Extract t() / $t() keys from .vue files
vue_files = sorted(glob.glob(str(ROOT / 'src' / 'views' / '**' / '*.vue'), recursive=True) +
                   glob.glob(str(ROOT / 'src' / 'components' / '**' / '*.vue'), recursive=True))

keys_used = set()
key_files = {}
for f in vue_files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
    except Exception:
        continue
    # Match t('key') or t("key") or $t('key') or .t('key')
    for m in re.finditer(r"(?:^|[^\w\$])(?:\$|\.)?t\(['\"]([^'\"]+)['\"]", content):
        k = m.group(1)
        keys_used.add(k)
        key_files.setdefault(k, set()).add(os.path.relpath(f, ROOT))

# 2. Parse locale TS object files
def flatten_ts_object(text, prefix=''):
    """Walk the TS object literal and return set of dot-paths."""
    out = set()
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    i = 0
    n = len(text)
    # Match BOTH quoted and unquoted keys
    key_re = re.compile(r"(?:['\"]([a-zA-Z0-9_.\-]+)['\"]|([a-zA-Z_][a-zA-Z0-9_]*))\s*:")
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

locale_files = {
    'zh-CN': ROOT / 'src' / 'locales' / 'zh-CN.ts',
    'en-US': ROOT / 'src' / 'locales' / 'en-US.ts',
    'ja-JP': ROOT / 'src' / 'locales' / 'ja-JP.ts',
    'ar-SA': ROOT / 'src' / 'locales' / 'ar-SA.ts',
    'ru-RU': ROOT / 'src' / 'locales' / 'ru-RU.ts',
}

locale_data = {}
for name, path in locale_files.items():
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    locale_data[name] = flatten_ts_object(text)

zh = locale_data.get('zh-CN', set())
en = locale_data.get('en-US', set())
ja = locale_data.get('ja-JP', set())
ar = locale_data.get('ar-SA', set())
ru = locale_data.get('ru-RU', set())

# Compare: which $t() keys are MISSING from each locale?
missing_zh = sorted(keys_used - zh)
missing_en = sorted(keys_used - en)
missing_ja = sorted(keys_used - ja)
missing_ar = sorted(keys_used - ar)
missing_ru = sorted(keys_used - ru)

# Output
report_lines = []
report_lines.append(f"=== i18n Audit ===")
report_lines.append(f"Files scanned: {len(vue_files)}")
report_lines.append(f"Distinct t() keys: {len(keys_used)}")
report_lines.append(f"")
report_lines.append(f"Locale key counts: zh-CN={len(zh)} en-US={len(en)} ja-JP={len(ja)} ar-SA={len(ar)} ru-RU={len(ru)}")
report_lines.append(f"")
report_lines.append(f"=== Keys used but MISSING from zh-CN: {len(missing_zh)} ===")
for k in missing_zh[:200]:
    files = key_files.get(k, set())
    report_lines.append(f"  {k}  (in {len(files)} files)")
if len(missing_zh) > 200:
    report_lines.append(f"  ... and {len(missing_zh) - 200} more")
report_lines.append(f"")
report_lines.append(f"=== Keys used but MISSING from en-US: {len(missing_en)} ===")
for k in missing_en[:60]:
    report_lines.append(f"  {k}")
report_lines.append(f"")
report_lines.append(f"=== Keys used but MISSING from ar-SA (RTL): {len(missing_ar)} ===")
for k in missing_ar[:60]:
    report_lines.append(f"  {k}")
report_lines.append(f"")
report_lines.append(f"=== Keys used but MISSING from ja-JP: {len(missing_ja)} ===")
for k in missing_ja[:60]:
    report_lines.append(f"  {k}")

(OUT / '_i18n_audit.txt').write_text('\n'.join(report_lines), encoding='utf-8')

# Summary stats only on stdout
print(f"files={len(vue_files)} t_keys={len(keys_used)}")
print(f"locale counts: zh={len(zh)} en={len(en)} ja={len(ja)} ar={len(ar)} ru={len(ru)}")
print(f"missing_zh={len(missing_zh)} missing_en={len(missing_en)} missing_ar={len(missing_ar)} missing_ja={len(missing_ja)}")
print(f"first 5 missing in zh-CN:")
for k in missing_zh[:5]:
    print(f"  {k}")
print(f"report: {OUT / '_i18n_audit.txt'}")