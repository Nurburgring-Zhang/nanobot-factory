"""Tests for storyboard_cache_redis (P6-2 P1-2)."""
import time
from unittest.mock import MagicMock, patch

import pytest

from engines.storyboard_cache_redis import (
    StoryboardCache,
    MemoryLRU,
    RedisBackend,
    make_key,
    cache_storyboard,
    lookup_storyboard,
    invalidate_workflow,
    get_storyboard_cache,
    reset_cache_for_tests,
    self_check,
    KEY_PREFIX,
    DEFAULT_TTL,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the process-global cache between tests."""
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


# ---- make_key ----

def test_make_key_format():
    k = make_key("wf_001", "scene_42")
    assert k == f"{KEY_PREFIX}:wf_001:scene_42"


# ---- MemoryLRU ----

def test_memory_lru_set_get():
    cache = MemoryLRU(max_entries=10)
    cache.set("k", {"x": 1})
    assert cache.get("k") == {"x": 1}


def test_memory_lru_delete():
    cache = MemoryLRU()
    cache.set("k", "v")
    assert cache.delete("k") is True
    assert cache.get("k") is None
    assert cache.delete("k") is False


def test_memory_lru_ttl_expiry():
    cache = MemoryLRU()
    cache.set("k", "v", ttl_seconds=1)
    assert cache.get("k") == "v"
    # Force expiry by passing the key with past timestamp via direct manipulation
    cache._data["k"] = (time.time() - 5, "v")  # type: ignore[index]
    assert cache.get("k") is None


def test_memory_lru_eviction():
    cache = MemoryLRU(max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # should evict "a"
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_memory_lru_clear_prefix():
    cache = MemoryLRU()
    cache.set(f"{KEY_PREFIX}:wf1:s1", "x")
    cache.set(f"{KEY_PREFIX}:wf1:s2", "y")
    cache.set(f"{KEY_PREFIX}:wf2:s1", "z")
    n = cache.clear_prefix(f"{KEY_PREFIX}:wf1:")
    assert n == 2
    assert cache.get(f"{KEY_PREFIX}:wf1:s1") is None
    assert cache.get(f"{KEY_PREFIX}:wf2:s1") == "z"


# ---- RedisBackend (mocked redis-py) ----

class FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.pinged = False

    def ping(self):
        self.pinged = True

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, payload):
        self.store[key] = payload

    def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n

    def scan_iter(self, match):
        import re
        pattern = match.replace("*", ".*")
        for k in list(self.store.keys()):
            if re.fullmatch(pattern, k):
                yield k


def test_redis_backend_set_get():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        backend = RedisBackend("redis://test:6379/0")
        assert backend.set("k1", {"x": 1}) is True
        assert backend.get("k1") == {"x": 1}
        assert fake.pinged is True


def test_redis_backend_get_miss():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        backend = RedisBackend("redis://test:6379/0")
        assert backend.get("nonexistent") is None


def test_redis_backend_delete():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        backend = RedisBackend("redis://test:6379/0")
        backend.set("k", "v")
        assert backend.delete("k") is True
        assert backend.get("k") is None


def test_redis_backend_init_failure_falls_back_silently():
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.side_effect = RuntimeError("no redis")
        backend = RedisBackend("redis://does-not-exist:1234/0")
        # All ops return None/False safely
        assert backend.get("k") is None
        assert backend.set("k", "v") is False
        assert backend.delete("k") is False


def test_redis_backend_corrupt_json_dropped():
    fake = FakeRedis()
    fake.store["k"] = b"not valid json {"
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        backend = RedisBackend("redis://test:6379/0")
        assert backend.get("k") is None
        # Should have been deleted
        assert "k" not in fake.store


# ---- StoryboardCache composite ----

def test_cache_writes_through_to_redis():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        cache = StoryboardCache("redis://test:6379/0")
        cache.set("k", {"panels": 4})
        # Verify JSON encoded
        assert b'"panels"' in fake.store["k"]


def test_cache_falls_back_to_memory_when_redis_offline():
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.side_effect = RuntimeError("offline")
        cache = StoryboardCache("redis://nowhere:1234/0")
        cache.set("k", {"x": 1})
        # Memory fallback should have it
        assert cache.memory.get("k") == {"x": 1}


def test_cache_invalidate_workflow_clears_prefix():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        cache = StoryboardCache("redis://test:6379/0")
        cache.set(f"{KEY_PREFIX}:wf1:s1", "a")
        cache.set(f"{KEY_PREFIX}:wf1:s2", "b")
        cache.set(f"{KEY_PREFIX}:wf2:s1", "c")
        n = cache.invalidate_workflow("wf1")
        assert n >= 2
        assert cache.get(f"{KEY_PREFIX}:wf2:s1") == "c"


# ---- High-level helpers ----

def test_cache_and_lookup_helpers():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        cache_storyboard("wf_001", "scene_42", {"panels": [1, 2, 3]})
        board = lookup_storyboard("wf_001", "scene_42")
        assert board == {"panels": [1, 2, 3]}


def test_lookup_miss_returns_none():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        assert lookup_storyboard("nonexistent", "scene") is None


def test_invalidate_workflow_helper():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        cache_storyboard("wf_x", "s1", "a")
        cache_storyboard("wf_x", "s2", "b")
        cache_storyboard("wf_y", "s1", "c")
        n = invalidate_workflow("wf_x")
        assert n >= 2
        assert lookup_storyboard("wf_y", "s1") == "c"


# ---- self_check ----

def test_self_check_returns_ok_when_redis_available():
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        result = self_check()
        assert result["write_ok"] is True
        assert result["read_back"] is not None


def test_self_check_never_raises():
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.side_effect = RuntimeError("all down")
        # Should not raise
        result = self_check()
        assert "stats" in result


# ---- Multi-worker simulation ----

def test_two_caches_share_redis_state():
    """Two StoryboardCache instances pointing at the same Redis must
    see each other's writes — this is the multi-worker safety guarantee.
    """
    fake = FakeRedis()
    with patch("redis.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake
        cache_a = StoryboardCache("redis://shared:6379/0")
        cache_b = StoryboardCache("redis://shared:6379/0")
        cache_a.set("shared_key", {"from": "A"})
        # cache_b fetches via Redis — must see A's write
        assert cache_b.get("shared_key") == {"from": "A"}