"""Smoke test for new engines."""
import sys
sys.path.insert(0, 'backend')

mods = [
    'imdf.engines.vida_engine',
    'imdf.engines.image_engine',
    'imdf.engines.data_video',
    'imdf.engines.data_t2i',
    'imdf.engines.data_3d',
    'imdf.engines.data_edit',
    'imdf.engines.engine_router',
]
import inspect
for m in mods:
    try:
        mod = __import__(m, fromlist=['*'])
        cls = next((c for n, c in inspect.getmembers(mod, inspect.isclass) if c.__module__ == m and not n.startswith('_')), None)
        name = cls.__name__ if cls else '(data-only)'
        print(f'OK   {m:35s} {name}')
    except Exception as e:
        print(f'FAIL {m:35s} {type(e).__name__}: {str(e)[:80]}')
