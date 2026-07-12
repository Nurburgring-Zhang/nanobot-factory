"""Post-process audit JSON — filter test artifacts, classify properly."""
import json
from collections import Counter
from pathlib import Path

data = json.load(open(r'D:\Hermes\生产平台\nanobot-factory\reports\p21_r1_audit_crawler.json', encoding='utf-8'))
print(f'Total entries in JSON: {len(data)}')
print()

subdirs = Counter(r['subdir'] for r in data)
print(f'By subdir: {dict(subdirs)}')
print()

# Filter out test files
test_files = [r for r in data if r['name'].startswith('test_')]
print(f'Test files detected: {len(test_files)}')
for r in test_files[:20]:
    print(f'  {r["subdir"]:15} / {r["name"]:30}')
print()

# Test* classes (likely test fixtures inside real source files)
test_classes = [r for r in data if r.get('class','').startswith('Test')]
print(f'Test* classes detected: {len(test_classes)}')
for r in test_classes:
    print(f'  {r["subdir"]:15} / {r["name"]:30} class={r["class"]}')
print()

# Real channels
real = []
for r in data:
    name = r['name']
    cls = r.get('class', '?')
    if name.startswith('test_') or cls.startswith('Test') or cls == '?':
        continue
    real.append(r)
print(f'Real channels after filter: {len(real)}')

# By subdir
real_subdirs = Counter(r['subdir'] for r in real)
print(f'Real channels by subdir: {dict(real_subdirs)}')
print()

# Count issue levels
print('--- Issue distribution (REAL channels only) ---')
p0_count = sum(1 for r in real if any(i.get('level') == 'P0' for i in r.get('issues', [])))
p1_count = sum(1 for r in real if any(i.get('level') == 'P1' for i in r.get('issues', [])))
p2_count = sum(1 for r in real if any(i.get('level') == 'P2' for i in r.get('issues', [])))
ok_count = len(real) - len([r for r in real if r.get('issues')])
print(f'  OK (no issues):    {ok_count}')
print(f'  Has P0 issues:     {p0_count}')
print(f'  Has P1 issues:     {p1_count}')
print(f'  Has P2 issues:     {p2_count}')
print()

# List all issues
print('--- All issues by kind ---')
all_issues = Counter()
for r in real:
    for i in r.get('issues', []):
        all_issues[(i.get('level'), i.get('kind'))] += 1
for (lvl, kind), cnt in sorted(all_issues.items()):
    print(f'  {lvl} {kind:30} {cnt}')

# Now show channels with P0 issues
print()
print('--- Real channels with P0 issues ---')
for r in real:
    p0_issues = [i for i in r.get('issues', []) if i.get('level') == 'P0']
    if p0_issues:
        print(f'  {r["subdir"]:15} / {r["name"]:30} class={r["class"]:30}')
        for i in p0_issues:
            print(f'    P0 [{i.get("kind")}]: {i.get("msg")[:200]}')