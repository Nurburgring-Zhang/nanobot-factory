import re
with open(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\multimodal\EmbedStudio.vue', 'r', encoding='utf-8') as f:
    content = f.read()
# Look for any 't(' pattern
matches = re.findall(r'\bt\s*\(', content)
print('\\bt( matches:', len(matches))
for line in content.split('\n'):
    if 't(' in line or '$t(' in line or 'useI18n' in line:
        print(' ', line.strip()[:100])
# What did my audit script count?
# My regex was \b(?:t|useI18n|te|tc|ti|d|n|\$t|i18n\.global\.t)\s*\(
# Maybe the 'd' matched a date function
print('\nLooking for d( pattern:')
for line in content.split('\n'):
    m = re.search(r'\bd\s*\(', line)
    if m:
        print(' ', line.strip()[:100])
print('\nLooking for n( pattern:')
for line in content.split('\n'):
    m = re.search(r'\bn\s*\(', line)
    if m:
        print(' ', line.strip()[:100])