"""Analyze P0 issues from audit JSON."""
import json
data = json.load(open(r'D:\Hermes\生产平台\nanobot-factory\reports\p21_r1_audit_crawler.json', encoding='utf-8'))

print(f'Total entries: {len(data)}')
print()

# Filter
real = [r for r in data if not r['name'].startswith('test_') and not r.get('class', '').startswith('Test') and r.get('class', '?') != '?']
print(f'Real channels: {len(real)}')

print('\n--- P0 channels ---')
for r in real:
    p0 = [i for i in r.get('issues', []) if i.get('level') == 'P0']
    if p0:
        print(f'  {r["subdir"]:15} / {r["name"]:25} class={r["class"]}')
        for i in p0:
            print(f'    {i["kind"]:25}: {i["msg"][:300]}')

print('\n--- ALL CHANNELS status ---')
for r in real:
    n_p0 = sum(1 for i in r.get('issues', []) if i.get('level')=='P0')
    n_p1 = sum(1 for i in r.get('issues', []) if i.get('level')=='P1')
    n_p2 = sum(1 for i in r.get('issues', []) if i.get('level')=='P2')
    print(f'  {r["subdir"]:15} / {r["name"]:25} class={r["class"]:30} P0={n_p0} P1={n_p1} P2={n_p2} entry={r.get("entry","-")}')

print('\n--- P2 kinds ---')
from collections import Counter
p2_kinds = Counter()
for r in real:
    for i in r.get('issues', []):
        if i.get('level') == 'P2':
            p2_kinds[i.get('kind')] += 1
for k, c in p2_kinds.most_common():
    print(f'  {k:30} {c}')

print('\n--- Sources WITHOUT robots mention (channels with no robots at all) ---')
for r in real:
    no_robots = [i for i in r.get('issues', []) if i.get('kind') == 'no_robots_in_source']
    if no_robots:
        print(f'  {r["subdir"]:15} / {r["name"]:25}')

print('\n--- Sources WITHOUT copyright mention ---')
for r in real:
    no_copyright = [i for i in r.get('issues', []) if i.get('kind') == 'no_copyright']
    if no_copyright:
        print(f'  {r["subdir"]:15} / {r["name"]:25}')