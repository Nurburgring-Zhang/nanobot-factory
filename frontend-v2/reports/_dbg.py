import re
from pathlib import Path
ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2')
text = (ROOT / 'src' / 'locales' / 'zh-CN.ts').read_text(encoding='utf-8')
key_re = re.compile(r"(?:['\"]([a-zA-Z0-9_.\-]+)['\"]|([a-zA-Z_][a-zA-Z0-9_]*))\s*:")
matches = key_re.findall(text[:2000])
print('Sample matches (first 10):')
for m in matches[:10]:
    print(m)
print()
print('--- My flatten function test ---')
import sys
sys.path.insert(0, str(ROOT / 'reports'))
from _audit_i18n import flatten_ts_object
ks = flatten_ts_object(text[:5000])
print('keys found:', len(ks))
print('sample:', list(ks)[:20])