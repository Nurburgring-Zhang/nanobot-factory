"""Shared fixtures for editor operator tests."""
import sys
from pathlib import Path

# Ensure backend root is on sys.path so `from services.workflow_service.editor.X import Y` works
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def make_timeline(*clip_specs):
    """Build a minimal timeline dict from (id, start, duration) tuples."""
    clips = []
    cursor = 0.0
    for spec in clip_specs:
        cid, start, dur = spec
        clips.append({
            "id": cid,
            "start": start if start is not None else round(cursor, 3),
            "duration": dur,
            "end": round((start if start is not None else cursor) + dur, 3),
            "src": f"clips/{cid}.mp4",
        })
        cursor = (start if start is not None else cursor) + dur
    return {"clips": clips, "cuts": [], "transitions": [], "effects": []}