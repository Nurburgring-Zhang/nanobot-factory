import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')
from services.workflow_service.basic_templates import TEMPLATES, list_categories, categories_with_count
print('Total templates:', len(TEMPLATES))
print('Categories:', list_categories())
print('Counts:', categories_with_count())
for t in TEMPLATES:
    print(f"  {t['id']:14s} [{t['category']:10s}] {t['name']}")
print('STEP_COUNT test:')
for t in TEMPLATES[:3]:
    print(f"  {t['id']}: {len(t['steps'])} steps")