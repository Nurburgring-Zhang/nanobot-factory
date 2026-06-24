"""Verify workflow_service API returns templates correctly."""
import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')

import os
os.environ.setdefault('JWT_SECRET', 'test-secret-32chars-pad-pad-pad!!')
os.environ.setdefault('IMDF_TEST_MODE', '1')

from fastapi.testclient import TestClient

# Import the workflow_service app
import importlib
wf_main = importlib.import_module('services.workflow_service.main')
client = TestClient(wf_main.app)

# Test the templates endpoint
print('=== GET /api/v1/workflows/templates ===')
r = client.get('/api/v1/workflows/templates')
print('status:', r.status_code)
body = r.json()
print('total:', body.get('total'))
print('categories count:', len(body.get('categories', [])))
items = body.get('items', [])
print('items count:', len(items))

# Test the business-specific endpoint
print('\n=== GET /api/v1/workflows/templates/business ===')
r = client.get('/api/v1/workflows/templates/business')
print('status:', r.status_code)
body = r.json()
print('total:', body.get('total'))
items = body.get('items', [])
print('items count:', len(items))
if items:
    print('first 3 ids:')
    for t in items[:3]:
        print(' ', t.get('id'), t.get('name'))

# Test categories summary
print('\n=== GET /api/v1/workflows/templates/categories/summary ===')
r = client.get('/api/v1/workflows/templates/categories/summary')
print('status:', r.status_code)
body = r.json()
print('total:', body.get('total'))
print('business_total:', body.get('business_total'))
print('legacy_total:', body.get('legacy_total'))
print('p3_6_w2_new_total:', body.get('p3_6_w2_new_total'))
print('per_category:', body.get('per_category'))