import re
text = open(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\ProjectCenter.vue', encoding='utf-8').read()
for m in re.finditer(r"\bt\(['\"],['\"]", text):
    i = m.start()
    print('--- context ---')
    print(repr(text[max(0,i-100):i+100]))