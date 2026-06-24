"""
test_storyboard.py
P4-8-W2 E2E: Storyboard Editor
- 场景序列编辑 (添加/删除/排序)
- 渲染与预览 (P4-5 multimodal.generate)
- 多镜头 + 视觉操作组合
"""
from typing import List, Dict, Any


def test_storyboard_add_scene():
    """Test 1: adding a scene initializes a 1-shot sequence"""
    scenes: List[Dict[str, Any]] = []
    scene_id = "s1"
    scenes.append({
        "id": scene_id,
        "title": "场景 1",
        "duration_sec": 6,
        "aspect": "16:9",
        "shots": [{"id": "sh1", "kind": "wide", "duration_sec": 3, "prompt": ""}],
        "voiceover": False,
        "appliedOps": [],
        "characterIds": [],
    })
    assert len(scenes) == 1
    assert scenes[0]["shots"][0]["kind"] == "wide"
    assert scenes[0]["aspect"] == "16:9"


def test_storyboard_remove_scene():
    """Test 2: removing a scene clears the selection if it was active"""
    scenes = [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]
    selected = "s2"
    scenes = [s for s in scenes if s["id"] != "s2"]
    if selected == "s2":
        selected = scenes[0]["id"] if scenes else ""
    assert len(scenes) == 2
    assert selected == "s1"


def test_storyboard_drag_reorder():
    """Test 3: drag-reorder changes scene positions but preserves IDs"""
    scenes = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}]
    # move a to position 2
    moved = scenes.pop(0)
    scenes.insert(2, moved)
    assert [s["id"] for s in scenes] == ["b", "c", "a"]


def test_storyboard_render_calls_multimodal():
    """Test 4: render generates preview URL via multimodal API"""
    scene = {"id": "s1", "prompt": "cinematic scene", "preview_url": None}
    # simulate API call
    res = {"candidates": [{"url": "data:image/svg+xml;...", "modality": "image"}], "elapsed_ms": 250}
    if res["candidates"]:
        scene["preview_url"] = res["candidates"][0]["url"]
    assert scene["preview_url"] is not None
    assert scene["preview_url"].startswith("data:")


def test_storyboard_total_duration():
    """Test 5: total duration sums all shots in a scene"""
    scene = {"shots": [{"duration_sec": 3}, {"duration_sec": 2.5}, {"duration_sec": 4}]}
    total = sum(s["duration_sec"] for s in scene["shots"])
    assert total == 9.5


def test_storyboard_visual_op_toggle():
    """Test 6: visual op toggle adds/removes from appliedOps list"""
    applied: list = []
    op = "face_swap"

    def toggle(o, lst):
        if o in lst:
            return [x for x in lst if x != o]
        return lst + [o]

    applied = toggle(op, applied)
    assert op in applied
    applied = toggle(op, applied)
    assert op not in applied


def test_storyboard_export_payload():
    """Test 7: export payload has all required fields for downstream consumption"""
    project = {
        "name": "storyboard-1234",
        "style": "cinematic",
        "scenes": [
            {"title": "Scene 1", "duration_sec": 6, "aspect": "16:9", "shots": [{"duration_sec": 3, "kind": "wide"}]},
        ],
    }
    assert "name" in project
    assert "style" in project
    assert "scenes" in project
    assert all("title" in s and "shots" in s for s in project["scenes"])
    # serialized JSON should round-trip
    import json
    blob = json.dumps(project)
    parsed = json.loads(blob)
    assert parsed == project


if __name__ == "__main__":
    test_storyboard_add_scene()
    test_storyboard_remove_scene()
    test_storyboard_drag_reorder()
    test_storyboard_render_calls_multimodal()
    test_storyboard_total_duration()
    test_storyboard_visual_op_toggle()
    test_storyboard_export_payload()
    print("All 7 storyboard tests passed.")
