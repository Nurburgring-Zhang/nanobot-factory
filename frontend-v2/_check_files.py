"""Check current state of 5 corrupted files."""
for f in ['WorkflowBuilder.vue', 'CapabilityRegistry.vue', 'CollectionCenter.vue', 'Delivery.vue', 'PackManager.vue']:
    raw = open(f'src/views/{f}', 'rb').read()
    text = raw.decode('utf-8', errors='replace')
    starts_template = text.startswith('<template>')
    has_nocheck = '@ts-nocheck' in text[:500]
    print(f'{f}:')
    print(f'  size: {len(text)}, newlines: {text.count(chr(10))}, starts with <template>: {starts_template}')
    print(f'  has @ts-nocheck: {has_nocheck}')
    print(f'  first 100: {repr(text[:100])}')
    print()
