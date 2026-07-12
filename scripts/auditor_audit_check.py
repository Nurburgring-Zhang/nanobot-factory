import json
with open(r'D:\Hermes\生产平台\nanobot-factory\reports\p13_b2_i18n_audit.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Total unused keys:', len(data.get('unusedInCode', [])))
print('First 30 unused keys:')
for k in data.get('unusedInCode', [])[:30]:
    print(f'  {k}')
print()
print('Missing in locale:', len(data.get('missingInLocale', [])))
for k in data.get('missingInLocale', []):
    print(f'  {k}')
print()
print('Top 20 hardcoded CN files:')
for h in data.get('topHardcodedCN', [])[:20]:
    print(f'  {h["runs"]:5d} - {h["file"]}')
print()
print('Per-namespace T usage (sorted):')
usage = data.get('perNamespaceTUsage', {})
for ns in sorted(usage.keys(), key=lambda x: -usage[x]):
    print(f'  {ns:25s}: {usage[ns]:4d} usage')