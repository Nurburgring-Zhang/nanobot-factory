"""Analyze corruption pattern in 5 vue files."""
import re

for fname in ['WorkflowBuilder.vue', 'CapabilityRegistry.vue', 'CollectionCenter.vue', 'Delivery.vue', 'PackManager.vue']:
    raw = open(f'src/views/{fname}', 'rb').read()
    text = raw.decode('utf-8', errors='replace')
    nl = text.count('\n')
    print(f'=== {fname}: {len(text)} chars, {nl} newlines ===')
    # Find <script setup>
    for m in re.finditer(r'<script setup[^>]*>', text):
        print(f'  <script setup> at offset {m.start()}')
    for m in re.finditer(r'</script>', text):
        print(f'  </script> at offset {m.start()}')
    # Find import ... const concatenation
    pattern = r"from ['\"]vue-i18n['\"]const \{ t \} = useI18n\(\)"
    for m in re.finditer(pattern, text):
        print(f'  import-concat at offset {m.start()}: ...{text[max(0,m.start()-30):m.start()+80]}...')
    # Count statements looking like "const X = useY()" or "function Z" without preceding semicolon
    imports_n = len(re.findall(r'\bimport\s+\{', text))
    consts_n = len(re.findall(r'\bconst\s+\{', text))
    print(f'  imports: {imports_n}, const-destruct: {consts_n}')
