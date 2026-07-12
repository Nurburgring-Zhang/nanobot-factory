"""
Independent auditor: measure t() coverage and hardcoded Chinese across views.
- Counts views that have ANY t() usage (call/useT/t('...'))
- Counts views with hardcoded Chinese strings
- Counts total hardcoded Chinese strings
"""
import os
import re
import sys

VIEWS_DIR = r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views'

# Chinese character regex (CJK Unified Ideographs + common punctuation)
CHINESE_RE = re.compile(r'[\u4e00-\u9fff]')
# t() usage patterns
T_USAGE_RE = re.compile(r'\b(?:t|useI18n|te|tc|ti|d|n)\s*\(|useI18n\s*\(|i18n\.global\.t\s*\(')

def find_views(root):
    views = []
    for r, d, files in os.walk(root):
        for f in files:
            if f.endswith('.vue'):
                views.append(os.path.join(r, f))
    return sorted(views)

def analyze_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    # Strip <template> v-bind/quoted literals are tricky. Just count any t( occurrences.
    # Strip script tags content - vue i18n uses $t or t() in template via auto-injected helpers
    # With globalInjection: true, plain `t(...)` works in template
    # We look for: t(..., useI18n, $t, i18n.global.t, tc, te, tm, ti, d, n
    t_count = len(re.findall(r'\b(?:t|useI18n|te|tc|ti|d|n|\$t|i18n\.global\.t)\s*\(', content))
    # Also look for $t (template literal)
    t_count_dollar = len(re.findall(r'\$\s*t\s*\(', content))
    t_count = max(t_count, t_count_dollar)
    # Hardcoded Chinese: count chinese chars NOT inside {{ }}, not inside $t(), not inside t()
    # Simpler: count chinese characters in template/script excluding strings inside t()
    # Strip out content inside t(...) calls
    stripped = re.sub(r"\b(?:t|te|tc|ti|d|n|\$t|i18n\.global\.t)\s*\([^)]*\)", '', content, flags=re.DOTALL)
    # Also strip content inside <script> import statements
    chinese_chars = CHINESE_RE.findall(stripped)
    return t_count, len(chinese_chars)

views = find_views(VIEWS_DIR)
print(f'Total vue files in views: {len(views)}')
print()

views_with_t = 0
views_with_zh = 0
total_t = 0
total_zh = 0
no_t_list = []
print(f'{"View":50s} | {"t() count":>9s} | {"zh chars":>9s}')
print('-' * 75)
for v in views:
    name = os.path.basename(v)
    tc, zc = analyze_file(v)
    total_t += tc
    total_zh += zc
    if tc > 0:
        views_with_t += 1
    else:
        no_t_list.append(name)
    if zc > 0:
        views_with_zh += 1
    marker = ' ✓' if tc > 0 else ' ✗'
    zh_marker = ' [zh]' if zc > 0 else ''
    print(f'{name:50s} | {tc:>9d} | {zc:>9d}{marker}{zh_marker}')

print()
print(f'Views with t(): {views_with_t}/{len(views)} = {views_with_t*100//len(views)}%')
print(f'Views with hardcoded zh: {views_with_zh}/{len(views)}')
print(f'Total t() calls: {total_t}')
print(f'Total hardcoded zh chars: {total_zh}')
print()
print(f'Views WITHOUT t() ({len(no_t_list)}):')
for v in no_t_list:
    print(f'  - {v}')