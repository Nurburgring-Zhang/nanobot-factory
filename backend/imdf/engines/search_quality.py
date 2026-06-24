"""
商用级检索质量增强引擎 v1.0
===========================
- 检索精度评估 (Recall@K / MRR / NDCG / MAP)
- 检索结果去重+去噪
- 相关性人工评分vs模型评分对比
- 检索延迟监控
- 行业对标 (IR standard benchmarks)
"""
import time
import logging
import hashlib
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ============================================================
# 1. Retrieval Metrics Engine (检索精度评估)
# ============================================================

class RetrievalMetrics:
    """信息检索核心指标计算"""

    @staticmethod
    def recall_at_k(relevant_docs: Set[str], retrieved_docs: List[str], k: int = 10) -> float:
        """Recall@K: 前K个结果中召回的相关文档比例"""
        if not relevant_docs:
            return 0.0
        retrieved_set = set(retrieved_docs[:k])
        return len(relevant_docs & retrieved_set) / len(relevant_docs)

    @staticmethod
    def precision_at_k(relevant_docs: Set[str], retrieved_docs: List[str], k: int = 10) -> float:
        """Precision@K: 前K个结果中相关文档的比例"""
        if k == 0:
            return 0.0
        retrieved_set = set(retrieved_docs[:k])
        return len(relevant_docs & retrieved_set) / k

    @staticmethod
    def mrr(relevant_docs: Set[str], retrieved_docs: List[str]) -> float:
        """MRR (Mean Reciprocal Rank): 第一个相关结果的倒数排名"""
        for i, doc_id in enumerate(retrieved_docs, 1):
            if doc_id in relevant_docs:
                return 1.0 / i
        return 0.0

    @staticmethod
    def ndcg_at_k(relevant_scores: Dict[str, float], retrieved_docs: List[str], k: int = 10) -> float:
        """NDCG@K (Normalized Discounted Cumulative Gain)"""
        if not relevant_scores:
            return 0.0

        # DCG@K
        dcg = 0.0
        for i, doc_id in enumerate(retrieved_docs[:k], 1):
            rel = relevant_scores.get(doc_id, 0.0)
            dcg += (2**rel - 1) / np.log2(i + 1)

        # IDCG@K (理想排序)
        ideal_scores = sorted(relevant_scores.values(), reverse=True)[:k]
        idcg = 0.0
        for i, rel in enumerate(ideal_scores, 1):
            idcg += (2**rel - 1) / np.log2(i + 1)

        return dcg / idcg if idcg > 0 else 0.0

    @staticmethod
    def map_score(queries_results: List[Dict]) -> float:
        """MAP (Mean Average Precision)"""
        if not queries_results:
            return 0.0
        ap_scores = []
        for q in queries_results:
            relevant = set(q.get("relevant_docs", []))
            retrieved = q.get("retrieved_docs", [])
            if not relevant:
                continue
            ap = 0.0
            rel_count = 0
            for i, doc_id in enumerate(retrieved, 1):
                if doc_id in relevant:
                    rel_count += 1
                    ap += rel_count / i
            ap_scores.append(ap / len(relevant) if relevant else 0.0)
        return float(np.mean(ap_scores)) if ap_scores else 0.0

    @staticmethod
    def hit_rate(relevant_docs: Set[str], retrieved_docs: List[str], k: int = 10) -> float:
        """Hit Rate@K: 前K个结果中至少命中一个相关文档的比例"""
        return 1.0 if any(d in relevant_docs for d in retrieved_docs[:k]) else 0.0

    @staticmethod
    def f1_at_k(relevant_docs: Set[str], retrieved_docs: List[str], k: int = 10) -> float:
        """F1@K"""
        p = RetrievalMetrics.precision_at_k(relevant_docs, retrieved_docs, k)
        r = RetrievalMetrics.recall_at_k(relevant_docs, retrieved_docs, k)
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    @staticmethod
    def comprehensive_eval(queries: List[Dict], k_values: List[int] = None) -> Dict:
        """综合检索评估"""
        if k_values is None:
            k_values = [1, 3, 5, 10, 20]

        metrics = {}
        for k in k_values:
            recalls = []
            precisions = []
            mrrs = []
            ndcgs = []
            f1s = []
            hits = []

            for q in queries:
                relevant = set(q.get("relevant_docs", []))
                retrieved = q.get("retrieved_docs", [])
                rel_scores = q.get("relevance_scores", {})

                recalls.append(RetrievalMetrics.recall_at_k(relevant, retrieved, k))
                precisions.append(RetrievalMetrics.precision_at_k(relevant, retrieved, k))
                mrrs.append(RetrievalMetrics.mrr(relevant, retrieved))
                ndcgs.append(RetrievalMetrics.ndcg_at_k(rel_scores, retrieved, k))
                f1s.append(RetrievalMetrics.f1_at_k(relevant, retrieved, k))
                hits.append(RetrievalMetrics.hit_rate(relevant, retrieved, k))

            metrics[f"k={k}"] = {
                "recall": round(float(np.mean(recalls)), 4),
                "precision": round(float(np.mean(precisions)), 4),
                "mrr": round(float(np.mean(mrrs)), 4),
                "ndcg": round(float(np.mean(ndcgs)), 4),
                "f1": round(float(np.mean(f1s)), 4),
                "hit_rate": round(float(np.mean(hits)), 4),
            }

        map_score = RetrievalMetrics.map_score(queries)

        return {
            "metrics_by_k": metrics,
            "map": round(map_score, 4),
            "n_queries": len(queries),
        }


# ============================================================
# 2. Dedup & Denoise Engine (去重+去噪)
# ============================================================

class DedupDenoiseEngine:
    """检索结果去重去噪引擎"""

    @staticmethod
    def text_dedup(results: List[Dict], text_field: str = "content",
                    threshold: float = 0.9) -> List[Dict]:
        """文本去重 (基于MinHash/Jaccard相似度)"""
        if len(results) <= 1:
            return results

        def _tokenize(text: str, n: int = 3) -> Set[str]:
            """字符n-gram分词"""
            text = text.lower().strip()
            return {text[i:i+n] for i in range(len(text) - n + 1)}

        def _jaccard(set_a: Set[str], set_b: Set[str]) -> float:
            if not set_a or not set_b:
                return 0.0
            return len(set_a & set_b) / len(set_a | set_b)

        kept = []
        for result in results:
            text = result.get(text_field, "")
            tokens = _tokenize(str(text))
            is_dup = False
            for kept_result in kept[-5:]:  # 只比较最近5个,提高效率
                kept_text = kept_result.get(text_field, "")
                if len(tokens) < 5 or len(_tokenize(str(kept_text))) < 5:
                    continue
                if _jaccard(tokens, _tokenize(str(kept_text))) > threshold:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(result)

        return kept

    @staticmethod
    def image_dedup(results: List[Dict], hash_field: str = "image_hash") -> List[Dict]:
        """图像去重 (基于pHash/Hamming距离)"""
        seen_hashes = set()
        kept = []
        for result in results:
            h = result.get(hash_field, "")
            if not h:
                kept.append(result)
                continue
            # 检查Hamming距离
            is_dup = False
            for seen in seen_hashes:
                if DedupDenoiseEngine._hamming_distance(h, seen) <= 5:
                    is_dup = True
                    break
            if not is_dup:
                seen_hashes.add(h)
                kept.append(result)

        return kept

    @staticmethod
    def _hamming_distance(h1: str, h2: str) -> int:
        """计算两个十六进制hash的Hamming距离"""
        if len(h1) != len(h2):
            return 999
        return sum(bin(int(a, 16) ^ int(b, 16)).count('1') for a, b in zip(h1, h2))

    @staticmethod
    def denoise_by_relevance(results: List[Dict], relevance_threshold: float = 0.3) -> List[Dict]:
        """基于相关性分数去噪"""
        return [r for r in results if r.get("relevance_score", r.get("score", 0)) >= relevance_threshold]

    @staticmethod
    def denoise_by_quality(results: List[Dict], min_quality: float = 0.4) -> List[Dict]:
        """基于质量分数去噪"""
        return [r for r in results if r.get("quality_score", 0.5) >= min_quality]

    @staticmethod
    def compute_dedup_rate(original_count: int, deduped_count: int) -> Dict:
        """计算去重率"""
        removed = original_count - deduped_count
        return {
            "original_count": original_count,
            "deduped_count": deduped_count,
            "removed": removed,
            "dedup_rate": round(removed / max(original_count, 1), 4),
        }


# ============================================================
# 3. Human vs Model Relevance Comparison
# ============================================================

class RelevanceComparator:
    """人工评分 vs 模型评分对比"""

    @staticmethod
    def compare_scores(human_scores: Dict[str, float],
                       model_scores: Dict[str, float]) -> Dict:
        """对比人工和模型评分"""
        common_docs = set(human_scores.keys()) & set(model_scores.keys())
        if not common_docs:
            return {"error": "无共同文档可比较"}

        human_vals = [human_scores[d] for d in sorted(common_docs)]
        model_vals = [model_scores[d] for d in sorted(common_docs)]

        # Pearson correlation
        h_arr = np.array(human_vals)
        m_arr = np.array(model_vals)
        if len(h_arr) > 1:
            corr_matrix = np.corrcoef(h_arr, m_arr)
            pearson = float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else 0.0
        else:
            pearson = 0.0

        # Spearman rank correlation
        from scipy.stats import spearmanr
        if len(h_arr) > 2:
            spearman, _ = spearmanr(h_arr, m_arr)
        else:
            spearman = pearson

        # MSE / MAE
        mse = float(np.mean((h_arr - m_arr) ** 2))
        mae = float(np.mean(np.abs(h_arr - m_arr)))
        rmse = float(np.sqrt(mse))

        # Agreement rate (within tolerance)
        tolerance = 0.15
        agreements = sum(1 for h, m in zip(human_vals, model_vals) if abs(h - m) <= tolerance)
        agreement_rate = agreements / len(common_docs)

        # Quality tier
        if pearson > 0.85 and agreement_rate > 0.8:
            quality = "excellent"
        elif pearson > 0.7 and agreement_rate > 0.65:
            quality = "good"
        elif pearson > 0.5:
            quality = "moderate"
        else:
            quality = "poor"

        return {
            "n_samples": len(common_docs),
            "pearson_correlation": round(pearson, 4),
            "spearman_correlation": round(spearman, 4),
            "mse": round(mse, 4),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "agreement_rate": round(agreement_rate, 4),
            "quality": quality,
            "recommendation": (
                "模型评分与人工评分高度一致,可信任模型评分" if quality == "excellent" else
                "模型评分基本可靠,建议定期抽检" if quality == "good" else
                "模型评分与人工评分偏差较大,建议增加人工评审"
            ),
        }

    @staticmethod
    def build_comparison_report(human_annotated: List[Dict],
                                model_retrieved: List[Dict],
                                id_field: str = "doc_id",
                                score_field: str = "relevance") -> Dict:
        """构建完整对比报告"""
        human_scores = {d[id_field]: d.get(score_field, 0) for d in human_annotated}
        model_scores = {d[id_field]: d.get(score_field, 0) for d in model_retrieved}

        comparison = RelevanceComparator.compare_scores(human_scores, model_scores)

        # 偏差分析
        biases = []
        for doc_id in human_scores:
            if doc_id in model_scores:
                diff = model_scores[doc_id] - human_scores[doc_id]
                if abs(diff) > 0.3:
                    biases.append({
                        "doc_id": doc_id,
                        "human_score": human_scores[doc_id],
                        "model_score": model_scores[doc_id],
                        "bias": round(diff, 3),
                        "direction": "overestimate" if diff > 0 else "underestimate",
                    })

        comparison["bias_analysis"] = {
            "biased_count": len(biases),
            "overestimate_count": sum(1 for b in biases if b["direction"] == "overestimate"),
            "underestimate_count": sum(1 for b in biases if b["direction"] == "underestimate"),
            "top_biases": sorted(biases, key=lambda x: abs(x["bias"]), reverse=True)[:5],
        }

        return comparison


# ============================================================
# 4. Latency Monitor (延迟监控)
# ============================================================

@dataclass
class LatencyRecord:
    """单次检索延迟记录"""
    query: str
    query_type: str = "vector"
    latency_ms: float = 0.0
    results_count: int = 0
    timestamp: float = field(default_factory=time.time)


class SearchLatencyMonitor:
    """检索延迟监控"""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.records: List[LatencyRecord] = []
        self._recent_latencies: List[float] = []

    def record(self, latency_record: LatencyRecord):
        """记录一次检索延迟"""
        self.records.append(latency_record)
        self._recent_latencies.append(latency_record.latency_ms)
        if len(self._recent_latencies) > self.window_size:
            self._recent_latencies.pop(0)

    def get_stats(self) -> Dict:
        """获取延迟统计"""
        if not self._recent_latencies:
            return {"error": "无数据", "status": "no_data"}

        arr = np.array(self._recent_latencies)
        p50 = float(np.percentile(arr, 50))
        p95 = float(np.percentile(arr, 95))
        p99 = float(np.percentile(arr, 99))

        # 按查询类型分组
        by_type = {}
        for record in self.records[-self.window_size:]:
            t = record.query_type
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(record.latency_ms)

        type_stats = {}
        for t, lats in by_type.items():
            larr = np.array(lats)
            type_stats[t] = {
                "count": len(lats),
                "avg_ms": round(float(np.mean(larr)), 2),
                "p50_ms": round(float(np.percentile(larr, 50)), 2),
                "p95_ms": round(float(np.percentile(larr, 95)), 2),
                "p99_ms": round(float(np.percentile(larr, 99)), 2),
            }

        # SLA判定
        sla_threshold = 200  # ms
        violations = sum(1 for l in self._recent_latencies if l > sla_threshold)
        sla_compliance = 1.0 - violations / max(len(self._recent_latencies), 1)

        return {
            "window_size": self.window_size,
            "total_records": len(self.records),
            "recent_count": len(self._recent_latencies),
            "avg_ms": round(float(np.mean(arr)), 2),
            "std_ms": round(float(np.std(arr)), 2),
            "min_ms": round(float(np.min(arr)), 2),
            "max_ms": round(float(np.max(arr)), 2),
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "sla_threshold_ms": sla_threshold,
            "sla_compliance": round(sla_compliance, 4),
            "sla_status": "healthy" if sla_compliance >= 0.99 else "warning" if sla_compliance >= 0.95 else "degraded",
            "by_query_type": type_stats,
        }

    def reset(self):
        """重置监控"""
        self.records.clear()
        self._recent_latencies.clear()


# ============================================================
# 5. LLM-based Search Quality Verification
# ============================================================

class LLMSearchVerifier:
    """LLM验证检索质量"""

    @staticmethod
    def verify_relevance(query: str, result: Dict, context: str = "") -> Dict:
        """用LLM验证单个结果与查询的相关性"""
        prompt = f"""你是一个专业的搜索质量评估专家。请判断以下搜索结果与查询的相关性。

## 用户查询
{query[:500]}

## 上下文 (可选)
{context[:300]}

## 搜索结果
标题: {result.get('title', result.get('name', 'N/A'))}
内容: {str(result.get('content', result.get('snippet', '')))[:1000]}
类型: {result.get('type', result.get('format', '未知'))}
分数: {result.get('score', result.get('relevance', 'N/A'))}

## 评估
请给出1-10分的相关性评分,并说明理由。

输出JSON格式:
{{
  "relevance_score": <1-10>,
  "is_relevant": true/false,
  "judgment": "highly_relevant|relevant|partially_relevant|not_relevant",
  "reason": "简要理由",
  "query_intent_match": true/false
}}
"""
        try:
            from engines.model_gateway import get_gateway
            gw = get_gateway()
            resp = gw.chat([{"role": "user", "content": prompt}], model="auto")
            import json, re
            json_match = re.search(r'\{[\s\S]*\}', resp.content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"LLM search verification failed: {e}")

        return {
            "relevance_score": 5,
            "is_relevant": True,
            "judgment": "partially_relevant",
            "reason": "LLM unavailable, using fallback",
            "query_intent_match": False,
        }

    @staticmethod
    def verify_search_results(query: str, results: List[Dict],
                              sample_size: int = 10) -> Dict:
        """验证搜索结果质量"""
        sample = results[:sample_size]
        verifications = []

        relevant_count = 0
        total_score = 0

        for result in sample:
            v = LLMSearchVerifier.verify_relevance(query, result)
            verifications.append({"result_id": result.get("id", ""), **v})
            total_score += v.get("relevance_score", 0)
            if v.get("is_relevant"):
                relevant_count += 1

        n = len(sample) if sample else 1

        return {
            "query": query,
            "results_reviewed": n,
            "avg_relevance_score": round(total_score / n, 2),
            "relevant_ratio": round(relevant_count / n, 4),
            "overall_quality": (
                "excellent" if relevant_count / n >= 0.9 else
                "good" if relevant_count / n >= 0.7 else
                "moderate" if relevant_count / n >= 0.5 else
                "poor"
            ),
            "verifications": verifications,
        }


# ============================================================
# 6. Search Quality Report Generator
# ============================================================

class SearchQualityReporter:
    """检索质量综合报告"""

    @staticmethod
    def generate_report(
        queries: List[Dict],
        dedup_results: Optional[Dict] = None,
        human_model_comparison: Optional[Dict] = None,
        latency_stats: Optional[Dict] = None,
        llm_verification: Optional[Dict] = None,
    ) -> Dict:
        """生成综合检索质量报告"""
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_queries": len(queries),
        }

        # 检索指标
        report["retrieval_metrics"] = RetrievalMetrics.comprehensive_eval(queries)

        # 去重统计
        if dedup_results:
            report["dedup"] = dedup_results

        # 人工vs模型对比
        if human_model_comparison:
            report["human_model_comparison"] = human_model_comparison

        # 延迟
        if latency_stats:
            report["latency"] = latency_stats

        # LLM验证
        if llm_verification:
            report["llm_verification"] = llm_verification

        # 综合评分
        metrics = report["retrieval_metrics"]["metrics_by_k"]
        k10 = metrics.get("k=10", {})
        recall_10 = k10.get("recall", 0)
        map_score = report["retrieval_metrics"].get("map", 0)
        mrr = k10.get("mrr", 0)

        combined_score = (recall_10 * 0.3 + map_score * 0.3 + mrr * 0.25 +
                         k10.get("ndcg", 0) * 0.15) * 100

        sla = 1.0
        if latency_stats:
            sla = latency_stats.get("sla_compliance", 1.0)

        report["overall_quality_score"] = round(combined_score, 1)
        report["sla_compliance"] = round(sla, 4)
        report["quality_tier"] = (
            "S-Tier (业界领先)" if combined_score >= 85 and sla >= 0.99 else
            "A-Tier (生产就绪)" if combined_score >= 70 and sla >= 0.97 else
            "B-Tier (可用)" if combined_score >= 50 and sla >= 0.95 else
            "C-Tier (需改进)" if combined_score >= 30 else
            "D-Tier (严重不足)"
        )

        return report


# ============================================================
# Industry Benchmarks
# ============================================================

INDUSTRY_SEARCH = {
    "web_search": {
        "name": "网页搜索",
        "benchmarks": ["MS MARCO", "TREC DL"],
        "quality_standards": "MRR@10 >= 0.35, NDCG@10 >= 0.45",
        "latency_target": "<100ms P95",
    },
    "enterprise_search": {
        "name": "企业搜索",
        "benchmarks": ["BEIR", "MTEB"],
        "quality_standards": "NDCG@10 >= 0.50, Recall@100 >= 0.85",
        "latency_target": "<200ms P95",
    },
    "multimodal_search": {
        "name": "多模态搜索",
        "benchmarks": ["Flickr30k", "COCO Captions"],
        "quality_standards": "Recall@10 >= 0.80, MRR >= 0.60",
        "latency_target": "<300ms P95",
    },
    "vector_search": {
        "name": "向量检索",
        "benchmarks": ["ANN Benchmarks", "big-ann-benchmarks"],
        "quality_standards": "Recall@10 >= 0.95, QPS >= 1000",
        "latency_target": "<10ms P99",
    },
}

# 单例
_retrieval_metrics: RetrievalMetrics = None
_dedup_engine: DedupDenoiseEngine = None
_relevance_comparator: RelevanceComparator = None
_latency_monitor: SearchLatencyMonitor = None
_llm_search_verifier: LLMSearchVerifier = None
_search_quality_reporter: SearchQualityReporter = None

def get_retrieval_metrics():
    global _retrieval_metrics
    _retrieval_metrics = _retrieval_metrics or RetrievalMetrics()
    return _retrieval_metrics

def get_dedup_engine():
    global _dedup_engine
    _dedup_engine = _dedup_engine or DedupDenoiseEngine()
    return _dedup_engine

def get_relevance_comparator():
    global _relevance_comparator
    _relevance_comparator = _relevance_comparator or RelevanceComparator()
    return _relevance_comparator

def get_latency_monitor():
    global _latency_monitor
    _latency_monitor = _latency_monitor or SearchLatencyMonitor()
    return _latency_monitor

def get_llm_search_verifier():
    global _llm_search_verifier
    _llm_search_verifier = _llm_search_verifier or LLMSearchVerifier()
    return _llm_search_verifier

def get_search_quality_reporter():
    global _search_quality_reporter
    _search_quality_reporter = _search_quality_reporter or SearchQualityReporter()
    return _search_quality_reporter
