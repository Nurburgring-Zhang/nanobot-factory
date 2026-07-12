import json
with open(r'D:\Hermes\生产平台\nanobot-factory\reports\p13_b2_i18n_audit.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
# Print all top-level keys
print('Top-level keys:', list(data.keys()))
print()
print('Summary:', data.get('summary', {}))
print()
# Per-file data
print('Views with t() calls:')
for path, st in sorted(data.get('perFile', {}).items()):
    if '/views/' in path and st.get('tCalls', 0) > 0:
        print(f'  {st["tCalls"]:3d} - {path}')