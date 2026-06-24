import yaml
import sys
from collections import Counter

with open(r'monitoring\prometheus-rules.yaml', 'r', encoding='utf-8') as f:
    doc = yaml.safe_load(f)

total = 0
groups = doc.get('groups', [])
print(f'Total groups: {len(groups)}')
for g in groups:
    n = len(g.get('rules', []))
    print(f'  - {g["name"]}: {n} rules')
    total += n
print(f'Total alerts: {total}')

sev = Counter()
cat = Counter()
for g in groups:
    for r in g.get('rules', []):
        sev[r.get('labels', {}).get('severity', '?')] += 1
        cat[r.get('labels', {}).get('category', '?')] += 1
print(f'Severity: {dict(sev)}')
print(f'Category: {dict(cat)}')

# basic structural validation
errors = []
for g in groups:
    if 'name' not in g:
        errors.append(f'group missing name: {g}')
    for r in g.get('rules', []):
        if 'alert' not in r:
            errors.append(f'rule missing alert: {r.get("alert", "?")}')
        if 'expr' not in r or not r['expr'].strip():
            errors.append(f'alert {r.get("alert", "?")} missing expr')
        if 'labels' not in r or 'severity' not in r.get('labels', {}):
            errors.append(f'alert {r.get("alert", "?")} missing severity label')
        if 'annotations' not in r or 'summary' not in r.get('annotations', {}):
            errors.append(f'alert {r.get("alert", "?")} missing summary annotation')
if errors:
    print('STRUCTURE ERRORS:')
    for e in errors:
        print(f'  - {e}')
    sys.exit(1)
else:
    print('Structure: OK')

# 20+ check
if total < 20:
    print(f'WARNING: only {total} alerts, expected 20+')
    sys.exit(2)

print('PASS')
