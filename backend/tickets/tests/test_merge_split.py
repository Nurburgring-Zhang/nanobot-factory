"""P6-Fix-C-8 / P1-6: 工单合并/拆分 tests."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

import tickets
from tickets import _TICKETS, merge_tickets, split_ticket
from tickets.routes import router


@pytest.fixture(autouse=True)
def _clean():
    _TICKETS.clear()
    yield
    _TICKETS.clear()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 合并测试 ──────────────────────────────────────────────────────────
class TestMergeTickets:
    def test_001_merge_two_tickets(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="磁盘满", description="A 机器磁盘已满",
            customer_id="CUS-001", reporter="alice",
        )
        t2 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="数据库慢", description="查询慢",
            customer_id="CUS-001", reporter="alice",
        )
        # t1 先加一条 comment
        t1.add_comment("已扩容", by="ops")
        t2.add_comment("已加索引", by="ops")
        res = merge_tickets(
            primary_ticket_id=t1.ticket_id,
            secondary_ticket_ids=[t2.ticket_id],
            operator="admin",
            note="同一根因",
        )
        assert res["moved_comments"] == 1
        assert len(res["merged"]) == 1
        # t2 状态 = merged
        assert res["merged"][0].status == "merged"
        assert res["merged"][0].merged_into == t1.ticket_id
        # t1 comments 包含 t2 的
        assert any("已加索引" in c["content"] for c in t1.comments)

    def test_002_merge_priority_upgrade(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t2 = tickets.create_ticket(
            ticket_type="problem", priority="P0",
            subject="B", description="d",
        )
        merge_tickets(t1.ticket_id, [t2.ticket_id])
        # t1 升级为 P0
        assert t1.priority == "P0"

    def test_003_merge_nonexistent_raises(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        with pytest.raises(KeyError):
            merge_tickets(t1.ticket_id, ["TK-FAKE-XXXXXX"])

    def test_004_merge_into_closed_raises(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t1.transition("closed", by="ops")
        t2 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="B", description="d",
        )
        with pytest.raises(ValueError):
            merge_tickets(t1.ticket_id, [t2.ticket_id])

    def test_005_merge_closed_secondary_raises(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t2 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="B", description="d",
        )
        t2.transition("closed", by="ops")
        with pytest.raises(ValueError):
            merge_tickets(t1.ticket_id, [t2.ticket_id])

    def test_006_merge_already_merged_raises(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t2 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="B", description="d",
        )
        merge_tickets(t1.ticket_id, [t2.ticket_id])
        with pytest.raises(ValueError):
            merge_tickets(t1.ticket_id, [t2.ticket_id])

    def test_007_merge_three(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="Main", description="d",
        )
        t2 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="X", description="d",
        )
        t3 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="Y", description="d",
        )
        res = merge_tickets(t1.ticket_id, [t2.ticket_id, t3.ticket_id])
        assert len(res["merged"]) == 2

    def test_008_merge_self_skipped(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        # 主 ID 在 secondary 列表里 — 应该跳过
        res = merge_tickets(t1.ticket_id, [t1.ticket_id])
        assert len(res["merged"]) == 0


# ── 2. 拆分测试 ──────────────────────────────────────────────────────────
class TestSplitTicket:
    def test_010_split_basic(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="原工单", description="d",
        )
        t1.add_comment("comment 0", by="alice")
        t1.add_comment("comment 1 - 拆走", by="alice")
        t1.add_comment("comment 2", by="alice")
        t1.add_comment("comment 3 - 拆走", by="alice")
        # comments 列表: [0, 1, 2, 3]  — 拆 1, 3
        res = split_ticket(
            ticket_id=t1.ticket_id,
            comment_indices=[1, 3],
            new_subject="拆出的工单",
            operator="admin",
        )
        assert res["moved_count"] == 2
        # t1 现在有 2 个原始 comments (0, 2) + 1 个 audit comment = 3
        assert len(res["original"].comments) == 3
        # 新工单有 2 个迁过来的 comments + 1 个 audit comment
        assert len(res["new"].comments) == 3
        # 新工单的 description 含原 ID
        assert "拆分自" in res["new"].description

    def test_011_split_invalid_index(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t1.add_comment("c0", by="x")
        with pytest.raises(ValueError):
            split_ticket(
                ticket_id=t1.ticket_id,
                comment_indices=[99],
                new_subject="new",
            )

    def test_012_split_empty_indices(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        with pytest.raises(ValueError):
            split_ticket(t1.ticket_id, [], "new")

    def test_013_split_nonexistent_raises(self):
        with pytest.raises(KeyError):
            split_ticket("TK-FAKE", [0], "new")

    def test_014_split_closed_raises(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t1.add_comment("c", by="x")
        t1.transition("closed", by="x")
        with pytest.raises(ValueError):
            split_ticket(t1.ticket_id, [0], "new")

    def test_015_split_with_new_priority(self):
        t1 = tickets.create_ticket(
            ticket_type="problem", priority="P3",
            subject="A", description="d",
        )
        t1.add_comment("c", by="x")
        res = split_ticket(
            ticket_id=t1.ticket_id,
            comment_indices=[0],
            new_subject="new",
            new_priority="P0",
        )
        assert res["new"].priority == "P0"


# ── 3. HTTP API ──────────────────────────────────────────────────────────
class TestMergeSplitRoutes:
    def test_020_merge_via_api(self, client):
        r1 = client.post("/api/v1/tickets", json={
            "type": "problem", "priority": "P3",
            "subject": "A", "description": "d",
        })
        r2 = client.post("/api/v1/tickets", json={
            "type": "problem", "priority": "P3",
            "subject": "B", "description": "d",
        })
        tid1 = r1.json()["ticket_id"]
        tid2 = r2.json()["ticket_id"]
        r = client.post(f"/api/v1/tickets/{tid1}/merge", json={
            "primary_ticket_id": tid1,
            "secondary_ticket_ids": [tid2],
            "operator": "admin",
            "note": "test",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["primary"]["ticket_id"] == tid1
        assert len(data["merged"]) == 1

    def test_021_merge_404(self, client):
        r1 = client.post("/api/v1/tickets", json={
            "type": "problem", "priority": "P3",
            "subject": "A", "description": "d",
        })
        tid1 = r1.json()["ticket_id"]
        r = client.post(f"/api/v1/tickets/{tid1}/merge", json={
            "primary_ticket_id": tid1,
            "secondary_ticket_ids": ["TK-FAKE"],
        })
        assert r.status_code == 404

    def test_022_split_via_api(self, client):
        r1 = client.post("/api/v1/tickets", json={
            "type": "problem", "priority": "P3",
            "subject": "A", "description": "d",
        })
        tid = r1.json()["ticket_id"]
        client.post(f"/api/v1/tickets/{tid}/comments", json={
            "content": "comment 0", "by": "x",
        })
        client.post(f"/api/v1/tickets/{tid}/comments", json={
            "content": "comment 1 - 拆走", "by": "x",
        })
        r = client.post(f"/api/v1/tickets/{tid}/split", json={
            "comment_indices": [1],
            "new_subject": "新工单",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["moved_count"] == 1
        assert data["new"]["subject"] == "新工单"

    def test_023_split_404(self, client):
        r = client.post("/api/v1/tickets/TK-FAKE/split", json={
            "comment_indices": [0], "new_subject": "new",
        })
        assert r.status_code == 404
