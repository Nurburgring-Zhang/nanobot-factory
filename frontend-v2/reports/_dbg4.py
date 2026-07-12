import re, glob
keys_with_comma = []
for f in glob.glob(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\**\*.vue', recursive=True) + glob.glob(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\components\**\*.vue', recursive=True):
    text = open(f, encoding='utf-8').read()
    for m in re.finditer(r"\bt\(['\"]([^'\"]+)['\"]", text):
        k = m.group(1)
        if ',' in k or k in ('', ' ', ','):
            keys_with_comma.append((f, k))
            break
print('first 5:')
for f, k in keys_with_comma[:5]:
    print(' ', f.split('\\')[-1], '->', repr(k))
print('total files with bad key:', len(keys_with_comma))