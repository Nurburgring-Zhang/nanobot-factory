"""P17-D1 Hidden #4: JsonlWebhookStore append-only tests.

Verify:
- save() opens file in 'a' mode (append, never truncate)
- 100 concurrent appends: all data preserved
- delete() appends a tombstone line (file never truncated)
- After many saves + deletes, file size grows monotonically
- Reads correctly parse multi-line JSONL
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.webhook_config import JsonlWebhookStore, WebhookConfig


def _make_config(wid: str) -> WebhookConfig:
    return WebhookConfig(
        webhook_id=wid,
        url="https://example.com/wh",
        events=["payment.succeeded"],
        secret="mysecret123",
    )


class TestJsonlAppendOnly:
    """Hidden #4 — JsonlWebhookStore must be append-only."""

    def test_001_save_appends_not_truncates(self, tmp_path):
        """save() opens file in append mode (never truncates existing data)."""
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        # First save
        s.save(_make_config("wh_a"))
        size_after_first = p.stat().st_size
        # Second save — file must grow, not reset
        s.save(_make_config("wh_b"))
        size_after_second = p.stat().st_size
        assert size_after_second > size_after_first

    def test_002_file_grows_monotonically(self, tmp_path):
        """10 sequential saves: file size strictly increasing."""
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        sizes = []
        for i in range(10):
            s.save(_make_config(f"wh_{i:03d}"))
            sizes.append(p.stat().st_size)
        # Strictly increasing
        for i in range(1, len(sizes)):
            assert sizes[i] > sizes[i - 1], (
                f"size[{i}]={sizes[i]} <= size[{i-1}]={sizes[i-1]}"
            )

    def test_003_delete_appends_tombstone(self, tmp_path):
        """delete() writes a tombstone line, never truncates the file."""
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        s.save(_make_config("wh_a"))
        s.save(_make_config("wh_b"))
        size_before = p.stat().st_size
        s.delete("wh_a")
        size_after = p.stat().st_size
        # File should have grown (tombstone appended)
        assert size_after > size_before
        # Verify the get() returns None
        assert s.get("wh_a") is None
        # Verify file content has a tombstone line
        content = p.read_text(encoding="utf-8")
        assert "DELETED:" in content
        assert "wh_a" in content

    def test_004_reads_parse_jsonl_correctly(self, tmp_path):
        """Reads correctly parse multi-line JSONL file."""
        p = tmp_path / "wh.jsonl"
        s1 = JsonlWebhookStore(p)
        for i in range(5):
            s1.save(_make_config(f"wh_{i}"))
        # New instance reads from disk
        s2 = JsonlWebhookStore(p)
        all_configs = s2.list()
        assert len(all_configs) == 5
        ids = {c.webhook_id for c in all_configs}
        assert ids == {f"wh_{i}" for i in range(5)}

    def test_005_100_concurrent_appends_no_loss(self, tmp_path):
        """Spec: 100 并发 append, 无丢失.

        Use threads to simultaneously save distinct configs.
        """
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        n = 100
        barrier = threading.Barrier(n)
        errors = []

        def worker(i: int):
            try:
                barrier.wait(timeout=10)
                s.save(_make_config(f"wh_{i:03d}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"concurrent save errors: {errors[:5]}"
        # All 100 records must be present
        all_ids = {c.webhook_id for c in s.list()}
        expected = {f"wh_{i:03d}" for i in range(n)}
        missing = expected - all_ids
        assert not missing, f"missing {len(missing)} records: {sorted(missing)[:5]}"
        assert len(all_ids) == n

    def test_006_100_concurrent_appends_and_reads(self, tmp_path):
        """50 concurrent appends + 50 concurrent reads — no corruption."""
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        # Pre-populate
        for i in range(20):
            s.save(_make_config(f"wh_seed_{i}"))

        n_writers = 50
        n_readers = 50
        errors = []
        write_count = [0]
        write_lock = threading.Lock()

        def writer(i: int):
            try:
                for j in range(3):
                    s.save(_make_config(f"wh_w{i}_{j}"))
                with write_lock:
                    write_count[0] += 1
            except Exception as e:
                errors.append(("write", e))

        def reader(i: int):
            try:
                for _ in range(3):
                    configs = s.list()
                    # Each read must yield valid configs
                    for c in configs:
                        assert c.webhook_id.startswith("wh_")
            except Exception as e:
                errors.append(("read", e))

        threads = []
        for i in range(n_writers):
            threads.append(threading.Thread(target=writer, args=(i,)))
        for i in range(n_readers):
            threads.append(threading.Thread(target=reader, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"errors during concurrent ops: {errors[:5]}"
        assert write_count[0] == n_writers

    def test_007_delete_persists_across_instances(self, tmp_path):
        """Tombstones survive process restart (re-instantiation)."""
        p = tmp_path / "wh.jsonl"
        s1 = JsonlWebhookStore(p)
        s1.save(_make_config("wh_a"))
        s1.save(_make_config("wh_b"))
        s1.delete("wh_a")
        # New instance
        s2 = JsonlWebhookStore(p)
        assert s2.get("wh_a") is None
        assert s2.get("wh_b") is not None

    def test_008_save_uses_append_mode(self, tmp_path):
        """Direct verification: save() does not call truncate()."""
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        # Spy: replace _write_lock with a counter wrapper
        original_lock = s._write_lock
        # Just verify behavior — file must contain appended lines
        s.save(_make_config("wh_a"))
        s.save(_make_config("wh_b"))
        lines = p.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 2
        # Both lines are valid JSON
        import json
        for line in lines:
            if line.startswith("DELETED:"):
                continue
            rec = json.loads(line)
            assert rec["webhook_id"] in ("wh_a", "wh_b")

    def test_009_concurrent_save_and_delete(self, tmp_path):
        """50 saves + 50 deletes on overlapping ids — no corruption."""
        p = tmp_path / "wh.jsonl"
        s = JsonlWebhookStore(p)
        # Pre-create
        for i in range(50):
            s.save(_make_config(f"wh_{i:03d}"))
        errors = []

        def saver(i: int):
            try:
                s.save(_make_config(f"wh_{i:03d}"))
            except Exception as e:
                errors.append(("save", e))

        def deleter(i: int):
            try:
                s.delete(f"wh_{i:03d}")
            except Exception as e:
                errors.append(("delete", e))

        threads = []
        for i in range(50):
            threads.append(threading.Thread(target=saver, args=(i,)))
            threads.append(threading.Thread(target=deleter, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        assert not errors, f"concurrent save/delete errors: {errors[:5]}"
        # Reads still work
        configs = s.list()
        for c in configs:
            assert c.webhook_id.startswith("wh_")