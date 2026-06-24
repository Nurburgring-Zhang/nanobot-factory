"""P3-6-W2 smoke test - validates all template endpoints."""
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from services.workflow_service.main import app

client = TestClient(app)

# 1. healthz
r = client.get('/healthz')
print(f"1. healthz: {r.status_code} {r.json()}")

# 2. list templates
r = client.get('/api/v1/workflows/templates')
data = r.json()
print(f"2. /api/v1/workflows/templates: {r.status_code} total={data['total']} cats={len(data['categories'])}")

# 3. business templates
r = client.get('/api/v1/workflows/templates/business')
data = r.json()
print(f"3. /api/v1/workflows/templates/business: {r.status_code} total={data['total']}")
print(f"   business_categories: {data['business_categories']}")

# 4. business templates filtered by category
r = client.get('/api/v1/workflows/templates/business?category=export')
print(f"4. business?category=export: {r.status_code} total={len(r.json()['items'])}")

# 5. business templates filtered by invalid category
r = client.get('/api/v1/workflows/templates/business?category=bogus')
print(f"5. business?category=bogus: {r.status_code} detail={str(r.json().get('detail'))[:80]}")

# 6. categories summary
r = client.get('/api/v1/workflows/templates/categories/summary')
print(f"6. summary: {r.status_code}")
print(f"   {r.json()}")

# 7. clone a business template
biz = client.get('/api/v1/workflows/templates/business').json()
biz_id = biz['items'][0]['id']
print(f"7. Cloning: {biz_id}")
r = client.post(f'/api/v1/workflows/templates/{biz_id}/clone', json={'name': 'Smoke test wf'})
data = r.json()
print(f"   clone: {r.status_code} id={data.get('id')} nodes={len(data.get('nodes', []))}")

# 8. clone a missing template
r = client.post('/api/v1/workflows/templates/tpl-biz-exp-999/clone')
print(f"8. clone missing: {r.status_code} detail={r.json().get('detail')}")

# 9. list W1 basic templates (different endpoint)
r = client.get('/api/v1/workflow/templates')
data = r.json()
print(f"9. /api/v1/workflow/templates (W1): {r.status_code} total={data['total']}")
print(f"   categories: {data['categories']}")

# 10. clone 5 different business templates (W2 smoke)
biz_all = client.get('/api/v1/workflows/templates/business').json()
print(f"10. Cloning 5 business templates:")
for t in biz_all['items'][:5]:
    r = client.post(f"/api/v1/workflows/templates/{t['id']}/clone", json={'name': f"smoke-{t['id']}"})
    nodes_count = len(r.json().get('nodes', []))
    print(f"   {t['id']:25} -> {r.status_code} nodes={nodes_count}")

# 11. dry-run W1 template
r = client.post('/api/v1/workflow/templates/tpl-coll-001/run', json={'dry_run': True, 'inputs': {}})
print(f"11. W1 dry-run tpl-coll-001: {r.status_code} status={r.json().get('status')}")

# 12. filter by category=image
r = client.get('/api/v1/workflows/templates?category=image')
print(f"12. templates?category=image: {r.status_code} total={r.json()['total']}")

# 13. filter by category=pipeline (new in W2)
r = client.get('/api/v1/workflows/templates?category=pipeline')
print(f"13. templates?category=pipeline: {r.status_code} total={r.json()['total']}")

print("\n=== ALL SMOKE TESTS DONE ===")