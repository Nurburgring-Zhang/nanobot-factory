# Filter Operator — 声明式数据筛选算子

> **类型**: Declarative operator (声明式算子, 非 runtime)
> **状态**: 已实现 (P6-2)
> **所属模块**: `backend/imdf/engines/filter_quality.py`
> **版本**: v1.0

## 概述

Filter Operator 是智影平台的数据筛选质量评估引擎。它**不直接执行筛选动作**, 而是为上层业务筛选器提供**精度评估 / A/B 测试 / LLM-as-Judge / 多维评估**四类质量度量能力。

适用场景:

- 上线前验证一套筛选规则的精度/召回率
- 多个筛选规则并行跑, 选 F1 最高的
- 用 LLM 抽样检查筛选结果的人工一致性
- 同时启用多个维度的筛选(resolution / nsfw / 清晰度 / ...), 评估整体通过率

> **重要**: 本模块是 **declarative** 的 — 调用方传入预测结果 `List[bool]` 和真值, 本模块**计算指标**, 不做实际过滤。真正的运行时筛选在 `data_pipeline.py` / `ingestion_engine.py` 等模块。

## API 概览

### 1. `FilterMetrics` — 指标数据结构

```python
from backend.imdf.engines.filter_quality import FilterMetrics

m = FilterMetrics(true_positives=90, false_positives=5,
                   true_negatives=80, false_negatives=10)
print(m.precision, m.recall, m.f1, m.accuracy, m.specificity)
```

| 指标 | 公式 | 业务含义 |
|------|------|---------|
| precision | TP / (TP + FP) | 筛选出来的有多准 (漏网率) |
| recall | TP / (TP + FN) | 该留的都留下了 (误杀率) |
| f1 | 2·P·R / (P + R) | 综合评分 |
| accuracy | (TP + TN) / 总数 | 整体准确率 |
| specificity | TN / (TN + FP) | 真正拒绝率 |

### 2. `FilterQualityEngine` — 质量评估引擎

```python
from backend.imdf.engines.filter_quality import get_filter_quality

engine = get_filter_quality()

# 1) 加 golden set
engine.add_golden_item(
    item={"id": "img001", "resolution": 4096},
    expected_pass=True,        # 这个图应通过筛选
    filter_name="resolution_check",
)

# 2) 用真实筛选器评估
result = engine.evaluate_on_golden(
    filter_func=lambda item: item.get("resolution", 0) >= 1920,
    filter_name="resolution_check",
)

# 3) 返回结构化指标 + 行业对标
print(result["metrics"]["f1"])            # → 0.95
print(result["industry_benchmark"])      # → 对标商用/学术/规则引擎
print(result["quality_rating"])          # → "excellent" / "good" / ...
```

### 3. A/B Test

```python
test_id = engine.start_ab_test(
    test_id="ab_2026_06_25",
    filter_a_config={"rule": "resolution>=1920"},
    filter_b_config={"rule": "resolution>=2560"},
    test_items=items,
)
for item in items:
    engine.record_ab_result(test_id,
        result_a=item["res"] >= 1920,
        result_b=item["res"] >= 2560,
        item_id=item["id"],
        ground_truth=item["expected"])
report = engine.conclude_ab_test(test_id, ground_truth=...)
```

### 4. LLM-as-Judge

```python
from backend.imdf.engines.filter_quality import LLMFilterJudge

verdict = LLMFilterJudge.judge_filter_results(
    filter_name="resolution_check",
    items=sample_items, results=sample_results,
    sample_size=10,
)
# → {"quality_score": 8, "false_negatives_detected": 2, ...}
```

依赖 `engines.model_gateway.get_gateway().chat()` — 离线时返回降级默认值。

### 5. 多维筛选评估

```python
from backend.imdf.engines.filter_quality import FilterQualityEngine

result = FilterQualityEngine.multi_dimension_evaluate(
    filter_results={
        "resolution_check": [True, False, True, ...],
        "nsfw_check":       [True, True,  False, ...],
        "sharpness_check":  [True, True,  True,  ...],
    },
    ground_truth=[True, True, False, ...],
)
# → {"dimensions": {...}, "overall": {...}, "n_dimensions": 3}
```

AND 逻辑: 所有维度都通过才算通过(整体预测)。

### 6. 综合报告

```python
from backend.imdf.engines.filter_quality import get_filter_reporter

reporter = get_filter_reporter()
report = reporter.generate_report(
    filter_name="image_quality_v2",
    golden_eval=golden_eval_result,
    ab_test_result=ab_result,
    llm_judgment=llm_verdict,
    dimension_eval=multi_dim_result,
)
# → {"overall_rating": "production_ready", "overall_f1": 0.93, ...}
```

## 评级标准

| F1 范围 | 评级 | 含义 |
|---------|------|------|
| ≥ 0.95 | `excellent` | 可直接上线商用 |
| ≥ 0.85 | `good` | 可用, 监控运行 |
| ≥ 0.75 | `acceptable` | 需提升, 可灰度 |
| ≥ 0.60 | `needs_improvement` | 需调优 |
| < 0.60 | `poor` | 不可用 |

## 行业对标

| 类别 | precision | recall | f1 |
|------|-----------|--------|----|
| 商用数据筛选 | 0.95 | 0.95 | 0.95 |
| 学术数据筛选 | 0.85 | 0.85 | 0.85 |
| 规则引擎筛选 | 0.90 | 0.80 | 0.85 |

## 单例获取

```python
from backend.imdf.engines.filter_quality import (
    get_filter_quality,   # → FilterQualityEngine 单例
    get_filter_reporter,  # → FilterQualityReporter 单例
)
```

## 与运行时筛选的关系

| 模块 | 角色 |
|------|------|
| `data_pipeline.py` | 真正的运行时筛选 — 执行 filter |
| `ingestion_engine.py` | 入库时筛选 — 与 oss 配合 |
| **`filter_quality.py` (本文档)** | **筛选质量评估** — 评估 filter 的质量 |

声明式 ≠ 无用: 评估是上线前必做的验证步骤。本模块是**上线门禁**的一部分。

## 测试

参见 `tests/unit/test_filter_quality.py` (声明式测试, 不依赖运行时数据)。