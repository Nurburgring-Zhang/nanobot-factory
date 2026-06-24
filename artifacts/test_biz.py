import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')
from services.workflow_service.business_templates import TEMPLATES
print('Count:', len(TEMPLATES))
for t in TEMPLATES:
    print('  ', t['id'], 'cat=', t['category'], 'name=', t['name'])