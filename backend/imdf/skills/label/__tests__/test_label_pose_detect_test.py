"""Tests for label_pose_detect."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_pose_detect
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_coco_17():
    out = _run(label_pose_detect(SkillInput(params={
        "image": "https://example.com/x.jpg",
    })))
    assert out.success is True
    res = out.result
    assert res["format"] == "coco_17"
    assert 1 <= res["count"] <= 3
    for p in res["poses"]:
        assert len(p["keypoints"]) == 17
        names = {kp["name"] for kp in p["keypoints"]}
        assert "nose" in names
        assert "left_ankle" in names


def test_edge_case_body_18():
    out = _run(label_pose_detect(SkillInput(params={
        "image": "/tmp/x.png",
        "format": "body_18",
    })))
    assert out.success is True
    assert out.result["format"] == "body_18"
    for p in out.result["poses"]:
        assert len(p["keypoints"]) == 18


def test_edge_case_body_25():
    out = _run(label_pose_detect(SkillInput(params={
        "image": "/tmp/x.png",
        "format": "body_25",
    })))
    assert out.success is True
    for p in out.result["poses"]:
        assert len(p["keypoints"]) == 25


def test_edge_case_max_people_caps():
    out = _run(label_pose_detect(SkillInput(params={
        "image": "/tmp/x.png",
        "max_people": 1,
    })))
    assert out.success is True
    assert out.result["count"] <= 1


def test_error_handling_invalid_format():
    out = _run(label_pose_detect(SkillInput(params={
        "image": "x.png",
        "format": "magic",
    })))
    assert out.success is False


def test_error_handling_missing_image():
    out = _run(label_pose_detect(SkillInput(params={})))
    assert out.success is False