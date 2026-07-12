"""P5-R1-T3: 4 个 P0 契约 bug 修复验证。

覆盖范围 (4 个最小测试, 对应 4 个 P0):
- T1: route_pack 非法状态转换 → InvalidPackTransitionError (不再静默 return 200)
- T2: job_to_dataset items_collected==0 → HTTPException(400)
- T3: CollectionCenter.vue 轮询代码存在 (静态检查 — setInterval + onUnmounted)
- T4: list_packs 支持 keyword 参数 (name LIKE 模糊查询)

P0 契约破损必须显式失败, 严禁静默成功.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_ROOT))

os.environ.setdefault("IMDF_TEST_MODE", "1")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tmp_db(tmp_path) -> str:
    """每个测试一个隔离的 SQLite 文件."""
    db = str(tmp_path / "p0_test.db")
    yield db
    try:
        os.unlink(db)
    except OSError:
        pass


@pytest.fixture
def pack_eng(tmp_db):
    """构造独立 PackEngine (绕过 module-level singleton)."""
    from engines.pack_engine import PackEngine, PackStore
    return PackEngine(store=PackStore(db_path=tmp_db))


# =============================================================================
# T1: route_pack 非法状态转换必须抛 InvalidPackTransitionError
# =============================================================================

def test_t1_route_pack_invalid_transition_raises(pack_eng):
    """P0: 当 pack.status=DELIVERED (终态) 时 route_pack 必须抛 InvalidPackTransitionError.

    修复前: 静默 return 200 + target_module (契约破损)
    修复后: raise InvalidPackTransitionError, API 层映射为 HTTPException(400)
    """
    from engines.pack_engine import PackStatus, InvalidPackTransitionError

    pack = pack_eng.create_data_pack(name="p1", asset_ids=["a1", "a2"])
    pack_eng.store.update(pack.id, {"status": PackStatus.DELIVERED.value})

    # DELIVERED 是终态, route_pack 试图转 IN_ANNOTATION → 非法
    with pytest.raises(InvalidPackTransitionError) as exc_info:
        pack_eng.route_pack(pack.id)

    err = exc_info.value
    assert err.current == PackStatus.DELIVERED.value
    assert err.target == PackStatus.IN_ANNOTATION.value
    assert err.allowed == []  # 终态无允许转换


# =============================================================================
# T2: job_to_dataset 在 items_collected==0 时必须返回 HTTPException(400)
# =============================================================================

def test_t2_job_to_dataset_empty_raises_400(tmp_db):
    """P0: 采集为空 (items_collected==0) 时禁止创建空数据集.

    修复前: 默默创建空 dataset (契约破损)
    修复后: raise HTTPException(status_code=400, detail={...})
    """
    import asyncio
    from fastapi import HTTPException

    # api 包通过 conftest 加入 sys.path (backend/imdf/api)
    import api.collection_routes as cr_mod
    from api.collection_routes import job_to_dataset

    original = cr_mod.get_ingest_history
    cr_mod.get_ingest_history = lambda: [
        {"id": "job-empty-001", "type": "import",
         "items_collected": 0, "source": "test.csv"},
    ]
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(job_to_dataset("job-empty-001"))

        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail.get("error") == "empty_job"
        assert detail.get("items_collected") == 0
    finally:
        cr_mod.get_ingest_history = original


# =============================================================================
# T3: CollectionCenter.vue 必须有 setInterval + onUnmounted 清理
# =============================================================================

def test_t3_collection_center_polling_present():
    """P0: 实时进度 — onMounted 中必须有 setInterval(load..., 5000),
    onUnmounted 中必须清理 clearInterval.

    静态检查 .vue 源码 (避免引入 vue 测试环境).
    """
    vue_path = _ROOT / "frontend-v2" / "src" / "views" / "CollectionCenter.vue"
    assert vue_path.exists(), f"missing: {vue_path}"
    src = vue_path.read_text(encoding="utf-8")

    # 拿到 onMounted 整段 + 文件全局 (5000 可能出现在模块常量里)
    on_mounted_match = re.search(r"onMounted\s*\(\s*\(\s*\)\s*=>\s*\{", src)
    assert on_mounted_match, "onMounted(() => { ... }) not found"
    start = on_mounted_match.end()
    depth = 1
    i = start
    while i < len(src) and depth > 0:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    on_mounted_body = src[start : i - 1]
    assert "setInterval" in on_mounted_body, "onMounted missing setInterval"
    # 5000ms 间隔: 常量 POLL_INTERVAL_MS=5000 在模块顶部, 引用在 onMounted 里
    has_interval = (
        "5000" in on_mounted_body
        or "POLL_INTERVAL_MS" in on_mounted_body
    )
    assert has_interval, "onMounted missing 5000ms interval (literal or POLL_INTERVAL_MS)"

    # onUnmounted 块中必须有 clearInterval
    on_unmounted_match = re.search(r"onUnmounted\s*\(\s*\(\s*\)\s*=>\s*\{", src)
    assert on_unmounted_match, "onUnmounted(() => { ... }) not found"
    start = on_unmounted_match.end()
    depth = 1
    i = start
    while i < len(src) and depth > 0:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    on_unmounted_body = src[start : i - 1]
    assert "clearInterval" in on_unmounted_body, "onUnmounted missing clearInterval"


# =============================================================================
# T4: list_packs 必须支持 keyword 参数 (后端 LIKE 查询)
# =============================================================================

def test_t4_list_packs_keyword_filter(pack_eng):
    """P0: list_packs keyword 过滤 — name LIKE '%keyword%' 必须生效."""
    pack_eng.create_data_pack(name="apple_pack", asset_ids=["a1"])
    pack_eng.create_data_pack(name="banana_pack", asset_ids=["a2"])
    pack_eng.create_data_pack(name="apple_other", asset_ids=["a3"])

    items, total = pack_eng.list_packs(keyword="apple")
    assert total == 2
    assert all("apple" in p.name for p in items)

    items2, total2 = pack_eng.list_packs(keyword="banana")
    assert total2 == 1
    assert items2[0].name == "banana_pack"

    _, total3 = pack_eng.list_packs(keyword="xyz_no_match")
    assert total3 == 0