"""Smoke test: start uvicorn in subprocess, hit /api/v1/clean/list, kill."""
import os
import sys
import time
import json
import subprocess

ROOT = r'D:\Hermes\生产平台\nanobot-factory'
os.chdir(os.path.join(ROOT, 'backend'))
os.environ['PYTHONPATH'] = os.path.join(ROOT, 'backend')

LOG_DIR = os.path.join(ROOT, 'backend', 'tests', 'load')
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, 'cleaning_live.log')
err_path = os.path.join(LOG_DIR, 'cleaning_live.err')

python_exe = r'D:\ComfyUI\.ext\python.exe'
proc = subprocess.Popen(
    [python_exe, '-u', '-m', 'uvicorn',
     'services.cleaning_service.main:app',
     '--host', '127.0.0.1', '--port', '18904',
     '--log-level', 'warning', '--no-access-log'],
    stdout=open(log_path, 'w'),
    stderr=open(err_path, 'w'),
    env={**os.environ, 'PYTHONPATH': os.path.join(ROOT, 'backend')},
    cwd=os.path.join(ROOT, 'backend'),
)
print(f'spawned pid={proc.pid}')
# Wait for boot
for i in range(20):
    time.sleep(0.5)
    if proc.poll() is not None:
        print(f'PROCESS DIED early! exit={proc.returncode}')
        with open(err_path) as f:
            print('STDERR:', f.read())
        sys.exit(1)
    try:
        import socket
        s = socket.create_connection(('127.0.0.1', 18904), timeout=0.5)
        s.close()
        print(f'LISTEN at {i*0.5:.1f}s')
        break
    except OSError:
        continue
else:
    print('NEVER LISTENED')
    proc.kill()
    sys.exit(2)

# Now hit endpoints
import httpx
with httpx.Client(timeout=10.0) as client:
    r = client.get('http://127.0.0.1:18904/healthz')
    print(f'healthz: {r.status_code} {r.json()}')
    r = client.get('http://127.0.0.1:18904/api/v1/clean/list')
    body = r.json()
    print(f'list: {r.status_code} count={body["count"]}')
    r = client.get('http://127.0.0.1:18904/api/v1/clean/list?modality=video')
    print(f'video only: {r.status_code} count={r.json()["count"]}')
    r = client.post('http://127.0.0.1:18904/api/v1/clean/clean.text.empty',
                    json={'data': ['hello', '', None, 'world'], 'params': {}})
    print(f'text.empty: {r.status_code} {r.json()["result"]}')

proc.kill()
proc.wait(timeout=5)
print('killed')