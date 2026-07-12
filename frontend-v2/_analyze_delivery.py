"""Find all top-level keywords in Delivery.vue to understand the corruption."""
import re

text = open('src/views/Delivery.vue', 'rb').read().decode('utf-8', errors='replace')
m = re.search(r'<script setup[^>]*>', text)
start = m.end()
m2 = re.search(r'</script>', text)
end = m2.start()
script = text[start:end]
print(f'Script body: {len(script)} chars')

# Look for const/function/type/interface (declarations) and what comes before them
for kw in ['const ', 'function ', 'type ', 'interface ', 'export ', 'onMounted', 'computed', 'ref']:
    for m3 in re.finditer(r'\b' + re.escape(kw.rstrip()) + r'\b', script):
        pos = m3.start()
        # Get 30 chars before
        print(f'{kw}@{pos}: ...{script[max(0,pos-50):pos+50]}...')
    print()
