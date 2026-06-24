import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory')
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')
from backend.gateway.main import app
print('Gateway app loaded:', app.title, app.version)
print('Routes count:', len(app.state.routes))
for r in app.state.routes[:3]:
    print(f'  {r["name"]}: {r["prefix"]} -> {r["upstream"]} (auth={r["require_auth"]})')
print('Breakers:', app.state.breakers.snapshot())
