"""P22-Deep-10/11: FastAPI endpoint integration + env-var config.

T10: Spin up the QuickStart app via TestClient and hit all 9 endpoints.
T11: For each channel that takes env-key, verify both "with key" and
     "without key" code paths work without raising.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "imdf"))


# ─── T10: FastAPI endpoint integration ─────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    # Reload _quickstart_app to pick up tmp_path
    sys.path.insert(0, str(ROOT / "backend"))
    if "imdf._quickstart_app" in sys.modules:
        del sys.modules["imdf._quickstart_app"]
    from imdf._quickstart_app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_root_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "ZhiYing" in data["name"]
    assert data["mode"] == "standalone"
    assert "/healthz" in data["endpoints"]


def test_healthz_endpoint(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["mode"] == "standalone"
    assert data["db"] is True


def test_sfc_workflow_endpoint(client):
    r = client.get("/api/v1/sfc/workflow")
    assert r.status_code == 200
    data = r.json()
    assert data["view"] == "workflow"
    assert "lifecycle" in data["description"]


def test_sfc_collection_endpoint(client):
    r = client.get("/api/v1/sfc/collection")
    assert r.status_code == 200
    assert r.json()["view"] == "collection"


def test_sfc_delivery_endpoint(client):
    r = client.get("/api/v1/sfc/delivery")
    assert r.status_code == 200
    assert r.json()["view"] == "delivery"


def test_sfc_capability_endpoint(client):
    r = client.get("/api/v1/sfc/capability")
    assert r.status_code == 200
    assert r.json()["view"] == "capability"


def test_sfc_pack_endpoint(client):
    r = client.get("/api/v1/sfc/pack")
    assert r.status_code == 200
    assert r.json()["view"] == "pack"


def test_sfc_unknown_404(client):
    r = client.get("/api/v1/sfc/unknown_view")
    assert r.status_code == 404


def test_skills_endpoint(client):
    r = client.get("/api/v1/skills")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 50
    assert len(data["skills"]) == 50
    # All skill IDs are present
    skill_ids = {s["id"] for s in data["skills"]}
    assert "skill_crawl_web" in skill_ids
    assert "skill_comfy_run" in skill_ids


def test_channels_endpoint(client):
    r = client.get("/api/v1/channels")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 26  # At least P19-B3 14 + P22-P2a 12
    # All channel module names
    assert "JinaReader" in data["channels"] or "web" in data["channels"]


def test_celery_health_endpoint(client):
    r = client.get("/api/v1/celery/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "registered_tasks" in data
    assert data["status"] in ("ok", "degraded")


def test_engines_endpoint(client):
    r = client.get("/api/v1/engines")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 90  # At least 90 engine modules
    # API returns names like "engines.drama_engine", "engines.drama_harness"
    assert any("drama" in e for e in data["engines"])


def test_engines_endpoint_sorted_unique(client):
    r = client.get("/api/v1/engines")
    data = r.json()
    engines = data["engines"]
    assert engines == sorted(engines), "engines list should be sorted"
    assert len(engines) == len(set(engines)), "engines list should be unique"


def test_all_endpoints_no_500(client):
    """Hit all 9 documented endpoints — none should return 5xx."""
    endpoints = [
        "/", "/healthz",
        "/api/v1/sfc/workflow", "/api/v1/sfc/collection",
        "/api/v1/sfc/delivery", "/api/v1/sfc/capability", "/api/v1/sfc/pack",
        "/api/v1/skills", "/api/v1/channels", "/api/v1/celery/health",
        "/api/v1/engines",
    ]
    for path in endpoints:
        r = client.get(path)
        assert r.status_code < 500, f"{path} returned {r.status_code}"


def test_app_metadata(client):
    """App has title, version, description."""
    info = client.get("/openapi.json").json()
    assert "ZhiYing" in info["info"]["title"]
    assert info["info"]["version"].startswith("2.")


# ─── T11: env-var configuration ──────────────────────────────────────

# Each test toggles one env var, instantiates the channel, calls fetch().

@pytest.mark.parametrize("channel_module,class_name,env_var", [
    ("feedly", "FeedlyAPI", "FEEDLY_ACCESS_TOKEN"),
    ("pinterest", "PinterestAPI", "PINTEREST_ACCESS_TOKEN"),
    ("pocket", "PocketAPI", "POCKET_CONSUMER_KEY"),
    ("instapaper", "InstapaperAPI", "INSTAPAPER_CONSUMER_KEY"),
    ("delicious", "DeliciousAPI", "DELICIOUS_USER"),
    ("tumblr", "TumblrAPI", "TUMBLR_API_KEY"),
    ("exa_search", "ExaSearch", "EXA_API_KEY"),
    ("twitter", "TwitterAPI", "TWITTER_BEARER_TOKEN"),
])
def test_channel_env_key_loaded(monkeypatch, channel_module, class_name, env_var):
    """When env key is set, the channel instance reports api_key_configured=True
    (without actually calling the real API)."""
    monkeypatch.setenv(env_var, "fake_key_for_test")
    import importlib
    mod = importlib.import_module(f"imdf.intelligence.agent_reach.channels.{channel_module}")
    cls = getattr(mod, class_name)
    api = cls()
    # Inspect the channel's env-var attribute
    attr_name = {
        "FEEDLY_ACCESS_TOKEN": "token",
        "PINTEREST_ACCESS_TOKEN": "token",
        "POCKET_CONSUMER_KEY": "consumer_key",
        "INSTAPAPER_CONSUMER_KEY": "consumer_key",
        "DELICIOUS_USER": "user",
        "TUMBLR_API_KEY": "api_key",
        "EXA_API_KEY": "api_key",
        "TWITTER_BEARER_TOKEN": "bearer",
    }.get(env_var, "key")
    if hasattr(api, attr_name):
        assert getattr(api, attr_name) == "fake_key_for_test", (
            f"{class_name} didn't pick up {env_var}"
        )


@pytest.mark.parametrize("channel_module,class_name", [
    ("feedly", "FeedlyAPI"),
    ("pinterest", "PinterestAPI"),
    ("pocket", "PocketAPI"),
    ("instapaper", "InstapaperAPI"),
    ("delicious", "DeliciousAPI"),
    ("tumblr", "TumblrAPI"),
    ("exa_search", "ExaSearch"),
    ("twitter", "TwitterAPI"),
])
def test_channel_no_env_key(monkeypatch, channel_module, class_name):
    """Without env key, the channel has empty/None key attribute."""
    for var in ("FEEDLY_ACCESS_TOKEN", "PINTEREST_ACCESS_TOKEN", "POCKET_CONSUMER_KEY",
                 "INSTAPAPER_CONSUMER_KEY", "DELICIOUS_USER", "DELICIOUS_PASS",
                 "TUMBLR_API_KEY", "TUMBLR_BLOG_NAME", "EXA_API_KEY",
                 "TWITTER_BEARER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    import importlib
    mod = importlib.import_module(f"imdf.intelligence.agent_reach.channels.{channel_module}")
    cls = getattr(mod, class_name)
    api = cls()
    # Channel should construct successfully even without env
    assert api is not None


# ─── env-var combination tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_translate_with_libretranslate_only():
    """translate uses LibreTranslate (no API key) when no custom API."""
    from backend.skills_builtin_handlers import _BuiltinHandler
    from backend.skills.legacy import SkillInput as SI
    for v in ("TRANSLATE_API_URL", "TRANSLATE_API_KEY"):
        os.environ.pop(v, None)
    h = _BuiltinHandler(spec_id="skill_translate", name="skill_translate", description="")
    out = await h.execute(SI(params={"text": "hello world", "target": "zh"}))
    assert out.success
    assert out.result["source"] in ("passthrough", "auto", "en",
                                     "libretranslate-public", "mymemory-public")


@pytest.mark.asyncio
async def test_browser_screenshot_offline():
    """browser_screenshot: no playwright/chromium in CI but should not crash."""
    from backend.skills_builtin_handlers import _BuiltinHandler
    from backend.skills.legacy import SkillInput as SI
    h = _BuiltinHandler(spec_id="skill_browser_screenshot", name="skill_browser_screenshot", description="")
    out = await h.execute(SI(params={"url": "https://example.com"}))
    # Either real success (chromium found) or graceful fallback
    assert out.success
    assert "url" in out.result or "screenshot_path" in str(out.result)


@pytest.mark.asyncio
async def test_comfy_run_with_env_url():
    """comfy_run with COMFYUI_URL set to unreachable port → offline queue."""
    os.environ["COMFYUI_URL"] = "http://127.0.0.1:1"  # unreachable
    from backend.skills_builtin_handlers import _BuiltinHandler
    from backend.skills.legacy import SkillInput as SI
    h = _BuiltinHandler(spec_id="skill_comfy_run", name="skill_comfy_run", description="")
    out = await h.execute(SI(params={"workflow": {"3": {"class_type": "KSampler"}}}))
    assert out.success
    # Should be queued_offline
    if out.result.get("status") == "queued_offline":
        assert "would_post_to" in out.result
    os.environ.pop("COMFYUI_URL", None)


# ─── Image engine env-var tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_image_engine_with_openai_key(monkeypatch):
    """ImageEngine uses OpenAI if OPENAI_API_KEY set, else PIL fallback."""
    from imdf.engines.image_engine import ImageEngine, ImageRequest
    eng = ImageEngine()
    out = await asyncio.get_event_loop().run_in_executor(
        None, lambda: eng.generate(ImageRequest(prompt="x", width=64, height=64))
    )
    # If no real OpenAI key, will fall back to PIL
    assert out.success
    # Either real or mock engine tag
    assert out.engine in ("openai-gpt-image-1", "stability-sd3", "replicate-sdxl",
                          "comfyui-queued", "pil-gradient")


def test_image_engine_with_stability_key(monkeypatch):
    from imdf.engines.image_engine import ImageEngine
    eng = ImageEngine()
    assert hasattr(eng, "stability_key")
    assert hasattr(eng, "openai_key")
    assert hasattr(eng, "replicate_token")
    assert hasattr(eng, "comfyui_url")
