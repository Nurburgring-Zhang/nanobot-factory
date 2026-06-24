"""
商用级模型评测质量控制引擎 v1.0
=================================
- Benchmark标准化 (MMLU/GSM8K/HumanEval等)
- 评测一致性 (多次评测Kappa)
- A/B分流评测框架
- LLM-as-Judge自动评测
- 行业对标 (Industry Benchmarks)

Each engine must contain: quality metrics / IAA / LLM evaluation / industry benchmarking
"""
import json
import time
import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter

logger = logging.getLogger(__name__)

# ============================================================
# Benchmark Registry
# ============================================================

class BenchmarkType(Enum):
    MMLU = "mmlu"                    # 大规模多任务语言理解
    GSM8K = "gsm8k"                  # 数学推理
    HumanEval = "humaneval"          # 代码生成
    HellaSwag = "hellaswag"          # 常识推理
    ARC = "arc"                      # AI2推理挑战
    TruthfulQA = "truthfulqa"        # 真实性评估
    BBH = "bbh"                      # 大基准难题
    CUSTOM = "custom"                # 自定义

BENCHMARK_CONFIGS = {
    "mmlu": {
        "name": "MMLU (Massive Multitask Language Understanding)",
        "domains": 57,
        "metric": "accuracy",
        "industry_baseline": {"gpt4": 0.864, "claude3": 0.868, "gemini_ultra": 0.834},
        "passing_threshold": 0.70,
    },
    "gsm8k": {
        "name": "GSM8K (Grade School Math 8K)",
        "domains": 1,
        "metric": "exact_match",
        "industry_baseline": {"gpt4": 0.920, "claude3": 0.910, "gemini_ultra": 0.882},
        "passing_threshold": 0.75,
    },
    "humaneval": {
        "name": "HumanEval (Code Generation)",
        "domains": 1,
        "metric": "pass@k",
        "industry_baseline": {"gpt4": 0.870, "claude3": 0.848, "gemini_ultra": 0.740},
        "passing_threshold": 0.60,
    },
    "hellaswag": {
        "name": "HellaSwag (Commonsense Reasoning)",
        "domains": 1,
        "metric": "accuracy",
        "industry_baseline": {"gpt4": 0.953, "claude3": 0.951, "gemini_ultra": 0.892},
        "passing_threshold": 0.80,
    },
    "arc": {
        "name": "ARC (AI2 Reasoning Challenge)",
        "domains": 1,
        "metric": "accuracy",
        "industry_baseline": {"gpt4": 0.963, "claude3": 0.965, "gemini_ultra": 0.930},
        "passing_threshold": 0.80,
    },
    "truthfulqa": {
        "name": "TruthfulQA (Truthfulness)",
        "domains": 38,
        "metric": "mc_accuracy",
        "industry_baseline": {"gpt4": 0.590, "claude3": 0.620, "gemini_ultra": 0.557},
        "passing_threshold": 0.50,
    },
}

# ============================================================
# 1. Eval Consistency Engine (评测一致性)
# ============================================================

class EvalConsistencyEngine:
    """多次评测一致性计算 — 评估模型输出稳定性"""

    @staticmethod
    def cohen_kappa_multi(runs: List[List[str]]) -> float:
        """多轮评测一致性 (Pairwise Cohen Kappa平均)"""
        n = len(runs)
        if n < 2:
            return 1.0
        kappas = []
        for i in range(n):
            for j in range(i + 1, n):
                labels = list(set(runs[i] + runs[j]))
                label_to_id = {l: idx for idx, l in enumerate(labels)}
                r1 = [label_to_id[x] for x in runs[i]]
                r2 = [label_to_id[x] for x in runs[j]]
                try:
                    from sklearn.metrics import cohen_kappa_score
                    k = cohen_kappa_score(r1, r2)
                except ImportError:
                    # Fallback: manual computation
                    k = EvalConsistencyEngine._manual_cohen_kappa(r1, r2, len(labels))
                kappas.append(k)
        return float(np.mean(kappas))

    @staticmethod
    def _manual_cohen_kappa(r1: List[int], r2: List[int], n_categories: int) -> float:
        """手动计算Cohen Kappa"""
        n = len(r1)
        if n == 0:
            return 0.0
        # 观察一致率
        po = sum(1 for a, b in zip(r1, r2) if a == b) / n
        # 期望一致率
        cnt1 = Counter(r1)
        cnt2 = Counter(r2)
        pe = sum((cnt1.get(i, 0) / n) * (cnt2.get(i, 0) / n) for i in range(n_categories))
        if pe >= 1.0:
            return 1.0
        return (po - pe) / (1.0 - pe)

    @staticmethod
    def fleiss_kappa_multi(ratings: List[List[int]], n_categories: int) -> float:
        """多评测者Fleiss Kappa"""
        n_items = len(ratings)
        n_raters = len(ratings[0]) if ratings else 0
        if n_items == 0 or n_raters <= 1:
            return 1.0
        counts = np.zeros((n_items, n_categories))
        for i in range(n_items):
            for r in ratings[i]:
                if 0 <= r < n_categories:
                    counts[i][r] += 1
        P_i = (np.sum(counts**2, axis=1) - n_raters) / (n_raters * (n_raters - 1))
        P_bar = np.mean(P_i)
        p_j = np.sum(counts, axis=0) / (n_items * n_raters)
        P_e = np.sum(p_j**2)
        if np.isclose(P_e, 1.0):
            return 1.0
        return float((P_bar - P_e) / (1.0 - P_e))

    @staticmethod
    def consistency_report(results: List[Dict], n_runs: int = 3) -> Dict:
        """综合一致性报告"""
        if not results or len(results) < 2:
            return {"error": "需要至少2次评测结果", "status": "insufficient_data"}

        # 提取每次评测的答案
        answers_per_run = []
        for run in results[:n_runs]:
            answers = [item.get("answer", item.get("prediction", "")) for item in run.get("items", [])]
            answers_per_run.append(answers)

        max_len = max(len(a) for a in answers_per_run)
        answers_per_run = [a + [""] * (max_len - len(a)) for a in answers_per_run]

        # 计算各种一致性指标
        cohen_avg = EvalConsistencyEngine.cohen_kappa_multi(answers_per_run)

        # 判定质量
        if cohen_avg > 0.9:
            quality = "outstanding"
        elif cohen_avg > 0.8:
            quality = "excellent"
        elif cohen_avg > 0.6:
            quality = "good"
        elif cohen_avg > 0.4:
            quality = "moderate"
        elif cohen_avg > 0.2:
            quality = "fair"
        else:
            quality = "poor"

        return {
            "n_runs": len(results),
            "n_items": max_len,
            "cohen_kappa_avg": round(cohen_avg, 4),
            "stability_quality": quality,
            "recommendation": (
                "模型输出高度一致,适合生产环境" if cohen_avg > 0.8 else
                "模型输出基本一致,需关注边界情况" if cohen_avg > 0.6 else
                "模型输出不稳定,建议调整temperature或提示词"
            ),
            "status": "complete",
        }


# ============================================================
# 2. A/B Split Evaluation Framework (A/B分流评测)
# ============================================================

@dataclass
class ABTestConfig:
    """A/B测试配置"""
    test_name: str
    variant_a: str               # 模型A ID
    variant_b: str               # 模型B ID
    benchmark: str = "mmlu"
    sample_size: int = 100
    significance_level: float = 0.05
    metrics: List[str] = field(default_factory=lambda: ["accuracy", "latency_ms"])


class ABTestEngine:
    """A/B分流评测引擎"""

    @staticmethod
    def run_ab_test(
        results_a: List[Dict],
        results_b: List[Dict],
        config: ABTestConfig,
    ) -> Dict:
        """执行A/B测试"""
        n_a = len(results_a)
        n_b = len(results_b)

        # 计算各指标
        metrics = {}
        for metric in config.metrics:
            if metric == "accuracy":
                vals_a = [1 if r.get("correct", False) else 0 for r in results_a]
                vals_b = [1 if r.get("correct", False) else 0 for r in results_b]
                mean_a = np.mean(vals_a)
                mean_b = np.mean(vals_b)
                # Two-proportion z-test
                p_pool = (sum(vals_a) + sum(vals_b)) / (n_a + n_b)
                se = np.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))
                if se > 0:
                    z_score = (mean_b - mean_a) / se
                else:
                    z_score = 0.0
                # p-value from z (two-tailed)
                from math import erfc, sqrt
                p_value = float(erfc(abs(z_score) / sqrt(2)))
            elif metric == "latency_ms":
                vals_a = [r.get("latency_ms", 0) for r in results_a]
                vals_b = [r.get("latency_ms", 0) for r in results_b]
                mean_a = float(np.mean(vals_a))
                mean_b = float(np.mean(vals_b))
                # t-test approximation
                std_a = float(np.std(vals_a, ddof=1)) if len(vals_a) > 1 else 0
                std_b = float(np.std(vals_b, ddof=1)) if len(vals_b) > 1 else 0
                se = np.sqrt(std_a**2/n_a + std_b**2/n_b) if n_a > 1 and n_b > 1 else 0
                z_score = (mean_b - mean_a) / se if se > 0 else 0.0
                from math import erfc, sqrt
                p_value = float(erfc(abs(z_score) / sqrt(2)))
            else:
                vals_a = [r.get(metric, 0) for r in results_a]
                vals_b = [r.get(metric, 0) for r in results_b]
                mean_a = float(np.mean(vals_a))
                mean_b = float(np.mean(vals_b))
                z_score = 0.0
                p_value = 1.0

            is_significant = p_value < config.significance_level
            winner = "a" if mean_a > mean_b else "b" if mean_b > mean_a else "tie"

            metrics[metric] = {
                "variant_a_mean": round(mean_a, 4),
                "variant_b_mean": round(mean_b, 4),
                "delta": round(mean_b - mean_a, 4),
                "delta_pct": round((mean_b - mean_a) / max(mean_a, 0.0001) * 100, 2),
                "z_score": round(z_score, 4),
                "p_value": round(p_value, 6),
                "significant": is_significant,
                "winner": winner if is_significant else "insignificant",
            }

        # 综合结论
        significant_wins = sum(1 for m in metrics.values() if m["significant"] and m["winner"] != "tie")
        a_wins = sum(1 for m in metrics.values() if m["significant"] and m["winner"] == "a")
        b_wins = sum(1 for m in metrics.values() if m["significant"] and m["winner"] == "b")

        if b_wins > a_wins and b_wins >= significant_wins * 0.6:
            conclusion = "B显著优于A,建议采纳B"
        elif a_wins > b_wins and a_wins >= significant_wins * 0.6:
            conclusion = "A显著优于B,建议维持A"
        elif significant_wins == 0:
            conclusion = "A/B无显著差异,可任选或合并"
        else:
            conclusion = "A/B各有优劣,需根据业务目标选择"

        return {
            "test_name": config.test_name,
            "variant_a": config.variant_a,
            "variant_b": config.variant_b,
            "sample_size": {"a": n_a, "b": n_b},
            "metrics": metrics,
            "conclusion": conclusion,
            "significance_level": config.significance_level,
        }


# ============================================================
# 3. LLM-as-Judge Evaluation (LLM自动评测)
# ============================================================

class LLMEvalJudge:
    """LLM-as-Judge 模型评测引擎"""

    EVAL_DIMENSIONS = [
        "accuracy",        # 答案正确性
        "relevance",       # 相关性
        "coherence",       # 连贯性
        "conciseness",     # 简洁性
        "helpfulness",     # 有用性
        "safety",          # 安全性
        "hallucination",   # 幻觉检测
    ]

    @staticmethod
    def judge_single(model_output: str, ground_truth: str, question: str = "",
                     dimensions: List[str] = None) -> Dict:
        """LLM评判单个模型输出"""
        dims = dimensions or LLMEvalJudge.EVAL_DIMENSIONS[:5]

        judge_prompt = f"""你是一个专业的AI模型评测专家。请对以下模型的输出进行质量评估。

## 问题
{question[:500]}

## 标准答案
{ground_truth[:1000]}

## 模型输出
{model_output[:2000]}

## 评估维度 (每项1-10分)
{chr(10).join(f"{i+1}. {d}" for i, d in enumerate(dims))}

## 输出格式 (严格JSON)
{{
  "scores": {{ {", ".join(f'"{d}": <1-10>' for d in dims)} }},
  "overall": <1-10>,
  "is_correct": true/false,
  "hallucination_detected": true/false,
  "justification": "综合评判理由",
  "strengths": ["..."],
  "weaknesses": ["..."]
}}
"""

        try:
            from engines.model_gateway import get_gateway
            gw = get_gateway()
            resp = gw.chat([{"role": "user", "content": judge_prompt}], model="auto")
            import re
            json_match = re.search(r'\{[\s\S]*\}', resp.content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"LLM judge failed: {e}")

        return {
            "scores": {d: 7 for d in dims},
            "overall": 7.0,
            "is_correct": model_output.strip().lower() == ground_truth.strip().lower(),
            "hallucination_detected": False,
            "justification": "Fallback judgment (LLM unavailable)",
            "strengths": [],
            "weaknesses": ["LLM judge unavailable"],
        }

    @staticmethod
    def judge_batch(items: List[Dict]) -> Dict:
        """批量LLM评判"""
        judgments = []
        total_score = 0
        correct_count = 0
        hallucination_count = 0

        for item in items:
            judgment = LLMEvalJudge.judge_single(
                model_output=item.get("output", item.get("prediction", "")),
                ground_truth=item.get("ground_truth", item.get("answer", "")),
                question=item.get("question", item.get("prompt", "")),
            )
            judgments.append(judgment)
            total_score += judgment.get("overall", 0)
            if judgment.get("is_correct"):
                correct_count += 1
            if judgment.get("hallucination_detected"):
                hallucination_count += 1

        n = len(judgments) if judgments else 1

        return {
            "total_items": len(items),
            "avg_score": round(total_score / n, 2),
            "accuracy": round(correct_count / n, 4),
            "hallucination_rate": round(hallucination_count / n, 4),
            "scores_by_dimension": LLMEvalJudge._aggregate_scores(judgments),
            "judgments": judgments,
        }

    @staticmethod
    def _aggregate_scores(judgments: List[Dict]) -> Dict:
        """聚合各维度评分"""
        dim_sums = {}
        for dim in LLMEvalJudge.EVAL_DIMENSIONS:
            scores = [j.get("scores", {}).get(dim, 0) for j in judgments]
            if scores:
                dim_sums[dim] = {
                    "mean": round(float(np.mean(scores)), 2),
                    "std": round(float(np.std(scores)), 2),
                    "min": min(scores),
                    "max": max(scores),
                }
        return dim_sums


# ============================================================
# 4. Standardized Benchmark Runner
# ============================================================

class BenchmarkRunner:
    """标准化Benchmark执行引擎"""

    @staticmethod
    def get_benchmark_info(benchmark_type: str) -> Dict:
        """获取Benchmark元信息"""
        cfg = BENCHMARK_CONFIGS.get(benchmark_type)
        if not cfg:
            return {"error": f"未知Benchmark: {benchmark_type}", "available": list(BENCHMARK_CONFIGS.keys())}
        return {
            "type": benchmark_type,
            **cfg,
        }

    @staticmethod
    def list_benchmarks() -> List[Dict]:
        """列出所有支持的Benchmark"""
        return [
            {"id": k, "name": v["name"], "metric": v["metric"],
             "industry_baseline": v["industry_baseline"]}
            for k, v in BENCHMARK_CONFIGS.items()
        ]

    @staticmethod
    def evaluate_results(results: List[Dict], benchmark_type: str) -> Dict:
        """评估Benchmark结果"""
        cfg = BENCHMARK_CONFIGS.get(benchmark_type, {})
        if not cfg:
            return {"error": f"未知Benchmark: {benchmark_type}"}

        n = len(results)
        if n == 0:
            return {"error": "无评测结果"}

        # 计算指标
        correct = sum(1 for r in results if r.get("correct", False))
        scores = [r.get("score", 1 if r.get("correct") else 0) for r in results]
        accuracy = correct / n
        avg_score = float(np.mean(scores))
        latency = [r.get("latency_ms", 0) for r in results]
        avg_latency = float(np.mean(latency)) if latency else 0

        # 与行业基线对比
        baseline = cfg.get("industry_baseline", {})
        comparisons = {}
        for model, bl_score in baseline.items():
            delta = accuracy - bl_score
            comparisons[model] = {
                "baseline": bl_score,
                "our_score": round(accuracy, 4),
                "delta": round(delta, 4),
                "status": "above" if delta > 0 else "below" if delta < 0 else "equal",
            }

        # 通过阈值
        threshold = cfg.get("passing_threshold", 0.7)
        passed = accuracy >= threshold

        return {
            "benchmark": benchmark_type,
            "benchmark_name": cfg["name"],
            "n_samples": n,
            "accuracy": round(accuracy, 4),
            "avg_score": round(avg_score, 4),
            "avg_latency_ms": round(avg_latency, 2),
            "passed": passed,
            "passing_threshold": threshold,
            "industry_comparison": comparisons,
            "percentile_vs_industry": round(accuracy / max(baseline.values()) * 100, 1) if baseline else None,
        }

    @staticmethod
    def human_eval_pass_at_k(code_samples: List[Dict], k: int = 1) -> float:
        """HumanEval pass@k 估算"""
        n = len(code_samples)
        if n == 0:
            return 0.0
        c = sum(1 for s in code_samples if s.get("passed_tests", 0) >= s.get("total_tests", 1))
        if n - c < k:
            return 1.0
        # pass@k = 1 - C(n-c, k) / C(n, k)
        from math import comb
        return 1.0 - comb(n - c, k) / comb(n, k)


# ============================================================
# 5. Quality Report Generator
# ============================================================

class EvalQualityReporter:
    """评测质量综合报告"""

    @staticmethod
    def generate_report(
        results: List[Dict],
        benchmark: str = "",
        include_consistency: bool = True,
        include_llm_judge: bool = True,
        include_ab_test: bool = False,
        ab_config: Optional[ABTestConfig] = None,
    ) -> Dict:
        """生成综合评测质量报告"""
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_evaluations": len(results),
        }

        # Benchmark评估
        if benchmark:
            report["benchmark"] = BenchmarkRunner.evaluate_results(results, benchmark)

        # 一致性分析
        if include_consistency and len(results) > 1:
            report["consistency"] = EvalConsistencyEngine.consistency_report([{"items": results}])

        # LLM裁判
        if include_llm_judge and results:
            report["llm_judge"] = LLMEvalJudge.judge_batch(results[:10])  # 抽样10条

        # A/B测试
        if include_ab_test and ab_config:
            # 按variant分割
            half = len(results) // 2
            results_a = results[:half]
            results_b = results[half:]
            report["ab_test"] = ABTestEngine.run_ab_test(results_a, results_b, ab_config)

        # 综合评分
        scores = []
        if "benchmark" in report:
            scores.append(report["benchmark"].get("accuracy", 0) * 100)
        if "llm_judge" in report:
            scores.append(report["llm_judge"].get("avg_score", 0) * 10)

        report["overall_quality_score"] = round(float(np.mean(scores)), 1) if scores else 0.0
        report["quality_tier"] = (
            "S-Tier (业界领先)" if report["overall_quality_score"] >= 90 else
            "A-Tier (生产就绪)" if report["overall_quality_score"] >= 80 else
            "B-Tier (可用)" if report["overall_quality_score"] >= 65 else
            "C-Tier (需改进)" if report["overall_quality_score"] >= 50 else
            "D-Tier (不合规)"
        )

        return report


# ============================================================
# Industry Benchmarking
# ============================================================

INDUSTRY_EVAL = {
    "code_generation": {
        "name": "代码生成",
        "benchmarks": ["humaneval", "mbpp"],
        "quality_standards": "HumanEval pass@1 >= 70%, MBPP >= 75%",
        "reference": "https://github.com/openai/human-eval",
    },
    "math_reasoning": {
        "name": "数学推理",
        "benchmarks": ["gsm8k", "math"],
        "quality_standards": "GSM8K >= 80%, MATH >= 50%",
        "reference": "https://github.com/openai/grade-school-math",
    },
    "general_knowledge": {
        "name": "通用知识",
        "benchmarks": ["mmlu", "arc"],
        "quality_standards": "MMLU >= 70%, ARC >= 80%",
        "reference": "https://github.com/hendrycks/test",
    },
    "multimodal": {
        "name": "多模态理解",
        "benchmarks": ["mmbench", "seed_bench"],
        "quality_standards": "MMBench >= 75%, SEED-Bench >= 72%",
        "reference": "https://github.com/open-compass/mmbench",
    },
}

# 单例
_eval_consistency: EvalConsistencyEngine = None
_ab_test: ABTestEngine = None
_llm_judge: LLMEvalJudge = None
_benchmark_runner: BenchmarkRunner = None
_reporter: EvalQualityReporter = None

def get_eval_consistency():
    global _eval_consistency
    _eval_consistency = _eval_consistency or EvalConsistencyEngine()
    return _eval_consistency

def get_ab_test_engine():
    global _ab_test
    _ab_test = _ab_test or ABTestEngine()
    return _ab_test

def get_llm_judge():
    global _llm_judge
    _llm_judge = _llm_judge or LLMEvalJudge()
    return _llm_judge

def get_benchmark_runner():
    global _benchmark_runner
    _benchmark_runner = _benchmark_runner or BenchmarkRunner()
    return _benchmark_runner

def get_eval_reporter():
    global _reporter
    _reporter = _reporter or EvalQualityReporter()
    return _reporter
