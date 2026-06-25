# P6-Fix P0-2: pytest `timeout` marker 缺失修复

**修复时间**: 2026-06-24 18:50
**修复人**: coder (worker session `mvs_8d6166c1f7fa4e71af6064fda146d28e`)
**来源审计**: `reports/p6_2_actions.md` P0-2 (5 min quick win)

---

## 1. 问题描述 (from P6-2 audit)

`backend/pytest.ini` 的 `[pytest] markers` 块未声明 `timeout` 标记,导致
`backend/tests/test_quality_engine.py` 第 266 行 `@pytest.mark.timeout(5)`
无法被 pytest 识别。又因为 `addopts` 中启用了 `--strict-markers`,pytest
会在 collection 阶段直接报错 (PytestUnknownMarkWarning → collection error),
**整个 test_quality_engine.py 共 39 个 test 全部无法被收集**。

原 markers 块 (修复前):

```ini
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
    asyncio: Async tests
```

---

## 2. 修改内容

### 2.1 `backend/pytest.ini` (核心修复)

在原有 markers 块新增 `e2e` 与 `timeout`,并补全 `integration` / `slow` 描述:

```ini
# Markers
markers =
    unit: Unit tests
    integration: Integration tests (need DB)
    e2e: End-to-end tests
    slow: Slow running tests (>1s)
    asyncio: Async tests
    timeout: pytest-timeout marker (pytest-timeout or asyncio.wait_for fallback)
```

### 2.2 `pytest.ini` (根目录,一致性修复)

新增 `timeout` marker (根目录测试也需要,如未来加入跨模块慢测试):

```ini
markers =
    slow: marks tests as slow
    unit: unit tests
    integration: integration tests
    e2e: end-to-end tests
    timeout: pytest-timeout marker (pytest-timeout or asyncio.wait_for fallback)
    dedup: deduplication tests
    iaa: inter-annotator agreement tests
    ...
```

---

## 3. 验证

### 3.1 Collection 结果 (修复后)

```
$ python -m pytest --collect-only backend/tests/test_quality_engine.py

============================= test session starts =============================
platform win32 -- Python 3.11.6, pytest-8.4.2, pluggy-1.6.0
configfile: pytest.ini
plugins: anyio-4.12.1, hydra-core-1.3.2, langsmith-0.4.59, asyncio-1.3.0,
         base-url-2.1.0, cov-7.1.0, django-4.7.0, playwright-0.4.4, respx-0.23.1
collecting ... collected 39 items

========================= 39 tests collected in 0.05s =========================
```

✅ **39/39 tests collected, 0 marker warnings, 0 collection errors** — P0-2 unblocked.

### 3.2 全部 backend/tests/ collection (sanity check)

```
$ python -m pytest --collect-only backend/tests/ -k "timeout or none"
collected 858 items / 2 errors / 1 skipped
```

`2 errors` 与本次 marker 修复无关,属其他模块既有失败 (与 P6-2 P0-1/P0-3/P0-4 关联)。
marker 警告已彻底消失。

---

## 4. 注意事项 (留给后续 task)

1. **`pytest-timeout` 插件当前未安装**:
   ```
   $ python -m pip show pytest-timeout
   WARNING: Package(s) not found: pytest-timeout
   ```
   `@pytest.mark.timeout(5)` 现在只是被 pytest 接受的合法标记,但**不会真的触发超时中断**。
   该插件已在 `backend/pyproject.toml` 的 `dev` extras 中声明
   (`pytest-timeout>=2.1.0`, line 114),只要运行 `pip install -e ".[dev]"` 即可激活。
   本次 task 范围仅修复 marker 声明,未触及插件安装 — 留作 P6-2 P2-3 后续。

2. **`--strict-markers` 已启用**: 任何后续新增 marker 都必须在 pytest.ini 提前声明,
   否则会触发 collection 失败。本次未关闭 strict-markers(属于安全防线,不应关闭)。

3. **根目录 `pytest.ini` 与 `backend/pytest.ini` 是双层配置**: pytest 默认就近加载
   `pytest.ini`(向上查找最近的),backend 测试走 `backend/pytest.ini`,IMDF 顶层
   测试走根目录 `pytest.ini`。两处都补 timeout 是为了一致性。

---

## 5. 修改文件清单

| 文件 | 修改类型 | 内容 |
|---|---|---|
| `backend/pytest.ini` | markers 块扩展 | 新增 `e2e` 与 `timeout`,完善 `integration`/`slow` 描述 |
| `pytest.ini` (root) | markers 块扩展 | 在 slow/unit/integration/e2e 之后插入 `timeout` |

**报告路径**: `reports/p6_fix_p0_2_pytest.md`