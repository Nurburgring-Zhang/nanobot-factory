"""Smoke test for the FastAPI app — confirms TestClient works and basic endpoints respond."""
import sys, os
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
os.environ['JWT_SECRET'] = 'e2e-realpath-jwt-secret-32chars-pad!!'
os.environ['IMDF_TEST_MODE'] = '1'
os.environ['AUDIT_CHAIN_SECRET'] = 'audit-chain-secret-32chars-pad-pad!!'

from fastapi.testclient import TestClient
from api.canvas_web import app

with TestClient(app) as c:
    # 1. Health
    r = c.get('/api/queue/health')
    print(f'[health] {r.status_code} body={r.text[:120]}')

    # 2. Register
    import time
    nonce = str(int(time.time() * 1000))[-9:]
    uname = f'smoke_{nonce}'
    r = c.post('/auth/register', json={'username': uname, 'password': 'SmokeP@ss1', 'role': 'admin'})
    print(f'[register] {r.status_code} body={r.text[:120]}')

    # 3. Login
    r = c.post('/auth/login', json={'username': uname, 'password': 'SmokeP@ss1'})
    print(f'[login] {r.status_code} body={r.text[:120]}')
    token = None
    if r.status_code in (200, 201):
        body = r.json()
        token = body.get('access_token') or body.get('data', {}).get('access_token')
        print(f'[token] len={len(token) if token else 0}')

    if token:
        h = {'Authorization': f'Bearer {token}'}
        # 4. assets list
        r = c.get('/api/assets', headers=h)
        print(f'[assets list] {r.status_code} body={r.text[:120]}')
        # 5. workflow contract list
        r = c.get('/api/v1/workflow/contract/list', headers=h)
        print(f'[workflow list] {r.status_code} body={r.text[:120]}')
        # 6. drama list
        r = c.get('/api/drama/list', headers=h)
        print(f'[drama list] {r.status_code} body={r.text[:120]}')
        # 7. dam files
        r = c.get('/api/dam/files', headers=h)
        print(f'[dam files] {r.status_code} body={r.text[:120]}')
        # 8. tenant list
        r = c.get('/api/v1/business/tenant', headers=h)
        print(f'[tenant list] {r.status_code} body={r.text[:120]}')
        # 9. billing formats
        r = c.get('/api/v1/business/export/formats', headers=h)
        print(f'[export formats] {r.status_code} body={r.text[:120]}')
