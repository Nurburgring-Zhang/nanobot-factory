"""Show detail of real channel issues."""
import json
from pathlib import Path

data = json.load(open(r'D:\Hermes\生产平台\nanobot-factory\reports\p21_r1_audit_crawler.json', encoding='utf-8'))
# Real channels
real = [r for r in data if not r['name'].startswith('test_') and not r.get('class', '').startswith('Test') and r.get('class', '?') != '?']

# Show all storage issues
print('=== STORAGE channels ===')
for r in real:
    if r['subdir'] != 'storage':
        continue
    name = r['name']
    cls = r['class']
    print(f'  {name:25} class={cls:25}')
    print(f'    entry={r.get("entry", "-")}, instantiated={r.get("instantiated", r.get("inst_method", "-"))}')
    print(f'    async_call_ok={r.get("async_call_ok", "-")}, items={r.get("async_items_count", "-")}')
    for i in r.get('issues', []):
        print(f'    {i["level"]} {i["kind"]:30}: {i["msg"][:200]}')
    print()

print('=== REAL P0 issues (all) ===')
for r in real:
    p0 = [i for i in r.get('issues', []) if i.get('level') == 'P0']
    if p0:
        print(f'  {r["subdir"]:15} / {r["name"]:25} class={r["class"]}')
        for i in p0:
            print(f'    {i["kind"]:30}: {i["msg"][:200]}')

print()
print('=== REAL P1 issues summary ===')
from collections import Counter
p1_kinds = Counter()
for r in real:
    for i in r.get('issues', []):
        if i.get('level') == 'P1':
            p1_kinds[i.get('kind')] += 1
for k, c in p1_kinds.most_common():
    print(f'  {k:30} {c}')

print()
print('=== REAL P2 issues summary ===')
p2_kinds = Counter()
for r in real:
    for i in r.get('issues', []):
        if i.get('level') == 'P2':
            p2_kinds[i.get('kind')] += 1
for k, c in p2_kinds.most_common():
    print(f'  {k:30} {c}')

print()
print('=== Detailed P1 issues by channel ===')
for r in real:
    p1 = [i for i in r.get('issues', []) if i.get('level') == 'P1']
    if p1:
        print(f'  {r["subdir"]:15} / {r["name"]:25}')
        for i in p1:
            print(f'    {i["kind"]:30}: {i["msg"][:200]}')