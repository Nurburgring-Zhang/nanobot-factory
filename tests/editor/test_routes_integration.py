"""P4-6-W1 tests for editor HTTP routes (TestClient integration).

Verifies the FastAPI surface end-to-end: catalogues, cut batch, transition,
effect, montage, render, projects CRUD.
"""
from __future__ import annotations

import time


def test_catalogue_endpoints(client):
    """GET /transitions, /effects, /montages return their counts."""
    r = client.get("/api/v1/workflow/editor/transitions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 12
    assert len(body["easing_functions"]) == 6
    r = client.get("/api/v1/workflow/editor/effects")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 16
    r = client.get("/api/v1/workflow/editor/montages")
    assert r.status_code == 200
    body = r.json()
    assert body["total_montages"] == 5
    assert body["total_time_modes"] == 4
    r = client.get("/api/v1/workflow/editor/render/codecs")
    assert r.status_code == 200
    body = r.json()
    assert {c["id"] for c in body["codecs"]} == {"h264", "h265", "vp9",
                                                  "prores"}
    assert {rs["id"] for rs in body["resolutions"]} == {"480p", "720p",
                                                        "1080p", "4K"}


def test_cut_batch_http(client, sample_timeline):
    """POST /cut executes a 6-op batch via HTTP."""
    payload = {
        "timeline": sample_timeline,
        "operations": [
            {"op": "split", "params": {"offset": 1.5, "clip_id": "c2"}},
            {"op": "trim", "params": {"clip_id": "c1",
                                       "in_offset": 0.5, "out_offset": 0.5}},
            # After split, c2 was replaced by c2_a + c2_b
            {"op": "reorder",
             "params": {"order": ["c3", "c1", "c2_a", "c2_b"]}},
            {"op": "loop", "params": {"clip_id": "c1", "count": 2}},
        ],
    }
    r = client.post("/api/v1/workflow/editor/cut", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["operations"]) == 4
    assert body["summary"]["clips"] >= 4


def test_transition_effect_montage_http(client, sample_timeline):
    """POST /transition, /effect, /montage all accept a timeline + apply."""
    # Transition
    r = client.post("/api/v1/workflow/editor/transition", json={
        "timeline": sample_timeline,
        "from_clip": "c1", "to_clip": "c2",
        "type": "cross_dissolve", "duration": 0.7,
        "easing": "ease-in-out",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "cross_dissolve"
    assert body["ffmpeg_filter"]
    # Effect
    r = client.post("/api/v1/workflow/editor/effect", json={
        "timeline": sample_timeline,
        "clip_id": "c2", "type": "vignette", "intensity": 0.5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "vignette"
    # Montage with BPM
    r = client.post("/api/v1/workflow/editor/montage", json={
        "timeline": sample_timeline,
        "clips": ["c1", "c2", "c3"],
        "type": "parallel", "time_mode": "parallel_timeline",
        "layout": "picture_in_picture",
        "bpm": 128, "per_clip_sec": 1.0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "parallel"
    assert body["bpm"] == 128
    # BPM sync
    r = client.post("/api/v1/workflow/editor/bpm_sync", json={
        "bpm": 120, "clip_count": 4,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["beat_sec"] == 0.5
    assert len(body["cut_points"]) == 4
    # Invalid transition type
    r = client.post("/api/v1/workflow/editor/transition", json={
        "timeline": sample_timeline,
        "from_clip": "c1", "to_clip": "c2",
        "type": "bogus_transition", "duration": 0.5,
    })
    assert r.status_code == 422


def test_render_http_lifecycle(client, sample_timeline):
    """POST /render (sync) returns a completed job; /progress is queryable."""
    r = client.post("/api/v1/workflow/editor/render", json={
        "timeline": sample_timeline,
        "codec": "h264", "resolution": "480p",
        "bitrate_kbps": 1000,
        "sync": True, "use_ffmpeg": False,
        "output_name": "rj-http.mp4",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed"
    jid = body["id"]
    r = client.get(f"/api/v1/workflow/editor/render/{jid}/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["progress"] >= 0.99
    # Cancel endpoint on completed job → 404 because the cancel call
    # returns False (and we map that to 404).
    r = client.post(f"/api/v1/workflow/editor/render/{jid}/cancel")
    assert r.status_code == 404
    # 404 on unknown job
    r = client.get("/api/v1/workflow/editor/render/nope/progress")
    assert r.status_code == 404


def test_project_http_crud_lock_snapshot(client, sample_project):
    """Project CRUD + snapshot + lock + load_template over HTTP."""
    pid = sample_project["id"]
    # Update
    r = client.put(f"/api/v1/workflow/editor/projects/{pid}", json={
        "name": "Renamed Project",
        "status": "editing",
    })
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Project"
    # Snapshot
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/snapshot",
        json={"label": "v2-snap"})
    assert r.status_code == 200
    sid = r.json()["snapshots"][0]["id"]
    # Lock
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/lock",
        json={"user_id": "alice", "ttl_sec": 60.0})
    assert r.status_code == 200
    assert r.json()["lock"]["user_id"] == "alice"
    # Second user cannot lock
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/lock",
        json={"user_id": "bob", "ttl_sec": 60.0})
    assert r.status_code == 423
    # Heartbeat
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/heartbeat",
        json={"user_id": "alice"})
    assert r.status_code == 200
    # Unlock
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/unlock",
        json={"user_id": "alice"})
    assert r.status_code == 200
    assert r.json()["lock"] is None
    # Load template (synthetic id → fallback)
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/load_template",
        json={"template_id": "tpl-bogus-but-present-12345"})
    assert r.status_code == 200
    assert r.json()["template_id"] == "tpl-bogus-but-present-12345"
    # Undo
    r = client.post(
        f"/api/v1/workflow/editor/projects/{pid}/undo")
    assert r.status_code == 200
    # List
    r = client.get("/api/v1/workflow/editor/projects")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    # Delete
    r = client.delete(f"/api/v1/workflow/editor/projects/{pid}")
    assert r.status_code == 200
    r = client.get(f"/api/v1/workflow/editor/projects/{pid}")
    assert r.status_code == 404
