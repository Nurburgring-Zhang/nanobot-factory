"""Comprehensive smoke test - check all 5 paths' endpoint accessibility."""
import sys, os
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
os.environ['JWT_SECRET'] = 'e2e-realpath-jwt-secret-32chars-pad!!'
os.environ['IMDF_TEST_MODE'] = '1'
os.environ['AUDIT_CHAIN_SECRET'] = 'audit-chain-secret-32chars-pad-pad!!'

from fastapi.testclient import TestClient
from api.canvas_web import app

with TestClient(app) as c:
    print('=== Path 1: assets ===')
    r = c.get('/api/assets')
    print(f'  [list] {r.status_code}')
    r = c.get('/api/annotations/history')
    print(f'  [annot hist] {r.status_code}')

    print('=== Path 2: workflow ===')
    r = c.get('/api/v1/workflow/contract/list')
    print(f'  [list] {r.status_code} body={r.text[:80]}')
    r = c.post('/api/v1/workflow/contract/nodes',
               json={'node_id': 'smoke_test_node', 'inputs': {'x': 'int'}, 'outputs': {'y': 'int'}, 'description': 'smoke', 'version': '1.0'})
    print(f'  [register] {r.status_code} body={r.text[:120]}')
    r = c.get('/api/v1/workflow/contract/presets')
    print(f'  [presets] {r.status_code} body={r.text[:80]}')
    r = c.post('/api/v1/workflow/contract/validate', json={'node_id': 'smoke_test_node'})
    print(f'  [validate] {r.status_code} body={r.text[:120]}')

    print('=== Path 3: dataset/lineage ===')
    r = c.get('/api/dam/files')
    print(f'  [dam files] {r.status_code} body={r.text[:80]}')
    r = c.get('/api/discovery/registered')
    print(f'  [discovery] {r.status_code} body={r.text[:80]}')
    r = c.get('/api/dam/lineage/test_id')
    print(f'  [lineage] {r.status_code} body={r.text[:80]}')
    r = c.get('/api/dam/formats')
    print(f'  [formats] {r.status_code} body={r.text[:80]}')

    print('=== Path 4: drama/storyboard ===')
    r = c.get('/api/drama/list')
    print(f'  [list] {r.status_code} body={r.text[:80]}')
    r = c.post('/api/drama/generate', json={'theme': 'smoke', 'episodes': 1})
    print(f'  [generate] {r.status_code} body={r.text[:120]}')

    print('=== Path 5: billing/tenant ===')
    r = c.get('/api/v1/business/tenant')
    print(f'  [tenant list] {r.status_code} body={r.text[:80]}')
    r = c.post('/api/v1/business/tenant', json={'tenant_id': f'smoke_t_{os.urandom(2).hex()}', 'name': 'Smoke T', 'tier': 'free'})
    print(f'  [tenant create] {r.status_code} body={r.text[:120]}')
    r = c.get('/api/v1/business/export/formats')
    print(f'  [export formats] {r.status_code} body={r.text[:80]}')
    r = c.post('/api/v1/business/export/data',
               json={'records': [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}], 'fmt': 'json'})
    print(f'  [export data] {r.status_code} body={r.text[:120]}')
    r = c.get('/api/v1/business/audit/verify')
    print(f'  [audit verify] {r.status_code} body={r.text[:80]}')
