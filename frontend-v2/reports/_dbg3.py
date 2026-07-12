import re
text = open(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\RequirementCenter.vue', encoding='utf-8').read()
# Find short keys
for m in re.finditer(r"t\(['\"]([^'\"]*)['\"]", text):
    k = m.group(1)
    if len(k) < 5:
        start = max(0, m.start()-30)
        print(f'short key: {k!r}')
        print(f'  context: ...{text[start:m.end()+30]!r}...')
        print()
print('---')
# Also count where the comma key came from - is it a regex match artifact?
text2 = open(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\components\Topbar.vue', encoding='utf-8').read()
m = re.search(r"t\(['\"],['\"]", text2)
if m:
    print(f'found literal t(\",\") in Topbar: {text2[max(0,m.start()-30):m.end()+30]!r}')