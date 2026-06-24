import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')
from services.workflow_service.templates import WORKFLOW_TEMPLATES, business_templates
print('Total merged:', len(WORKFLOW_TEMPLATES))
print('Business templates:', len(business_templates()))
from collections import Counter
cats = Counter(t['category'] for t in WORKFLOW_TEMPLATES)
for c, n in cats.most_common():
    print(f'  {c}: {n}')