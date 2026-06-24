"""
商用级数据寻源质量增强引擎 v1.0
- 数据源质量评分(可靠性/更新频率/许可证合规/社区活跃度)
- 源数据预览质量检查
- 来源可信度分级(A/B/C/D)
- IAA: 多源交叉验证一致性
"""
import json
import hashlib
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import math
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 1. 数据源质量评分模型
# ============================================================

@dataclass
class SourceQualityScore:
    """数据源质量评分"""
    source_id: str
    reliability: float = 0.0      # 可靠性 (0-100): 数据完整性/可用率
    freshness: float = 0.0        # 更新频率 (0-100): 最近更新/更新间隔
    license_compliance: float = 0.0  # 许可证合规 (0-100): 商业可用性/限制
    community_activity: float = 0.0  # 社区活跃度 (0-100): stars/downloads/contributors
    overall: float = 0.0          # 综合评分 (加权)
    tier: str = "D"              # A/B/C/D
    details: Dict = field(default_factory=dict)


class DiscoveryQualityEngine:
    """寻源质量评估引擎"""

    # 评分权重
    WEIGHTS = {
        "reliability": 0.35,
        "freshness": 0.25,
        "license_compliance": 0.25,
        "community_activity": 0.15,
    }

    # 开源许可证商业友好度评分
    LICENSE_SCORES = {
        "mit": 95, "apache-2.0": 95, "bsd-2-clause": 90, "bsd-3-clause": 90,
        "cc0": 85, "unlicense": 80, "cc-by-4.0": 75, "cc-by-sa-4.0": 65,
        "cc-by-nc-4.0": 40, "cc-by-nc-sa-4.0": 30, "gpl-3.0": 50,
        "agpl-3.0": 35, "other": 50, "unknown": 30, "": 30,
    }

    @staticmethod
    def score_source(source: Dict) -> SourceQualityScore:
        """对单个数据源进行质量评分"""
        sid = source.get("id", source.get("name", "unknown"))

        # 1. 可靠性评分
        reliability = DiscoveryQualityEngine._score_reliability(source)

        # 2. 更新频率评分
        freshness = DiscoveryQualityEngine._score_freshness(source)

        # 3. 许可证合规评分
        license_compliance = DiscoveryQualityEngine._score_license(source)

        # 4. 社区活跃度评分
        community_activity = DiscoveryQualityEngine._score_community(source)

        # 综合加权
        overall = (
            reliability * DiscoveryQualityEngine.WEIGHTS["reliability"] +
            freshness * DiscoveryQualityEngine.WEIGHTS["freshness"] +
            license_compliance * DiscoveryQualityEngine.WEIGHTS["license_compliance"] +
            community_activity * DiscoveryQualityEngine.WEIGHTS["community_activity"]
        )

        # 分级
        tier = DiscoveryQualityEngine._tier_from_score(overall)

        return SourceQualityScore(
            source_id=sid,
            reliability=round(reliability, 2),
            freshness=round(freshness, 2),
            license_compliance=round(license_compliance, 2),
            community_activity=round(community_activity, 2),
            overall=round(overall, 2),
            tier=tier,
            details={"source": source}
        )

    @staticmethod
    def _score_reliability(source: Dict) -> float:
        """评估数据源可靠性: 描述完整性、格式规范性、来源权威性"""
        score = 50.0
        desc = source.get("description", "")
        if desc and len(desc) > 50:
            score += 15
        if source.get("format"):
            score += 10
        if source.get("size"):
            score += 10
        platform = source.get("platform", "").lower()
        if platform in ("huggingface", "kaggle", "arxiv"):
            score += 15
        elif platform in ("github",):
            score += 10
        # 有明确ID加分
        if source.get("id") and len(source.get("id", "")) > 5:
            score += 10
        return min(100, max(0, score))

    @staticmethod
    def _score_freshness(source: Dict) -> float:
        """评估更新频率: 最近更新时间、更新历史"""
        score = 40.0
        updated = source.get("updated_at") or source.get("last_modified") or source.get("discovered_at")
        if updated:
            try:
                if isinstance(updated, str):
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00")[:19])
                else:
                    updated_dt = updated
                days_ago = (datetime.now() - updated_dt.replace(tzinfo=None)).days
                if days_ago < 30:
                    score += 30
                elif days_ago < 90:
                    score += 20
                elif days_ago < 180:
                    score += 10
            except Exception as e:
                logger.error(f"Operation failed: {e}")
        # 下载量/活跃度暗示更新
        downloads = source.get("downloads", 0)
        if isinstance(downloads, str):
            downloads = DiscoveryQualityEngine._parse_num(downloads)
        if downloads > 10000:
            score += 20
        elif downloads > 1000:
            score += 10
        return min(100, max(0, score))

    @staticmethod
    def _score_license(source: Dict) -> float:
        """评估许可证合规性"""
        license_str = str(source.get("license", "unknown")).lower()
        # 尝试匹配已知许可证
        for key, val in DiscoveryQualityEngine.LICENSE_SCORES.items():
            if key in license_str or license_str in key:
                return float(val)
        return float(DiscoveryQualityEngine.LICENSE_SCORES.get("unknown", 30))

    @staticmethod
    def _score_community(source: Dict) -> float:
        """评估社区活跃度: stars/downloads/contributors"""
        score = 20.0
        stars = source.get("stars", 0) or source.get("likes", 0)
        downloads = source.get("downloads", 0)
        if isinstance(stars, str):
            stars = DiscoveryQualityEngine._parse_num(stars)
        if isinstance(downloads, str):
            downloads = DiscoveryQualityEngine._parse_num(downloads)
        if stars > 1000:
            score += 30
        elif stars > 100:
            score += 20
        elif stars > 10:
            score += 10
        if downloads > 100000:
            score += 30
        elif downloads > 10000:
            score += 20
        elif downloads > 1000:
            score += 10
        if source.get("contributors") or source.get("author"):
            score += 10
        return min(100, max(0, score))

    @staticmethod
    def _parse_num(val: Any) -> int:
        """解析数值字符串"""
        if isinstance(val, (int, float)):
            return int(val)
        try:
            s = str(val).lower().replace(",", "").strip()
            if "k" in s:
                return int(float(s.replace("k", "")) * 1000)
            if "m" in s:
                return int(float(s.replace("m", "")) * 1000000)
            return int(float(s))
        except Exception:
            return 0

    @staticmethod
    def _tier_from_score(score: float) -> str:
        if score >= 80:
            return "A"
        elif score >= 65:
            return "B"
        elif score >= 50:
            return "C"
        return "D"

    @staticmethod
    def batch_score(sources: List[Dict]) -> List[SourceQualityScore]:
        """批量评分"""
        return [DiscoveryQualityEngine.score_source(s) for s in sources]

    @staticmethod
    def quality_report(sources: List[Dict]) -> Dict:
        """生成寻源质量报告"""
        scores = DiscoveryQualityEngine.batch_score(sources)
        if not scores:
            return {"error": "无数据源", "status": "empty"}

        tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for s in scores:
            tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1

        avg_overall = sum(s.overall for s in scores) / len(scores)
        avg_reliability = sum(s.reliability for s in scores) / len(scores)
        avg_freshness = sum(s.freshness for s in scores) / len(scores)
        avg_license = sum(s.license_compliance for s in scores) / len(scores)
        avg_community = sum(s.community_activity for s in scores) / len(scores)

        return {
            "total_sources": len(scores),
            "tier_distribution": tier_counts,
            "avg_scores": {
                "overall": round(avg_overall, 2),
                "reliability": round(avg_reliability, 2),
                "freshness": round(avg_freshness, 2),
                "license_compliance": round(avg_license, 2),
                "community_activity": round(avg_community, 2),
            },
            "top_sources": sorted(
                [{"id": s.source_id, "overall": s.overall, "tier": s.tier}
                 for s in scores],
                key=lambda x: x["overall"], reverse=True
            )[:10],
            "industry_benchmark": DiscoveryQualityEngine._industry_benchmark(avg_overall),
            "status": "complete"
        }

    @staticmethod
    def _industry_benchmark(avg_score: float) -> Dict:
        """行业对标"""
        benchmarks = {
            "商用标注公司": 85,
            "开源社区平均": 60,
            "学术数据集": 70,
            "企业数据湖": 80,
        }
        return {
            "compared_to": benchmarks,
            "percentile": round(avg_score / 100 * 100, 1),
            "rating": "above_average" if avg_score > 70 else "average" if avg_score > 55 else "below_average"
        }


# ============================================================
# 2. 源数据预览质量检查
# ============================================================

class SourcePreviewChecker:
    """源数据预览质量检查: 抽样验证、格式一致性、字段完整性"""

    @staticmethod
    def check_preview_quality(preview_data: List[Dict], expected_schema: Dict = None) -> Dict:
        """
        检查预览数据质量
        - 字段完整性
        - 数据类型一致性
        - 空值率
        - 格式有效性
        """
        if not preview_data:
            return {"error": "无预览数据", "status": "empty"}

        n = len(preview_data)
        all_keys = set()
        for item in preview_data:
            if isinstance(item, dict):
                all_keys.update(item.keys())

        field_stats = {}
        for key in all_keys:
            values = [item.get(key) for item in preview_data if isinstance(item, dict)]
            non_null = [v for v in values if v is not None and v != ""]
            null_rate = 1.0 - len(non_null) / n if n > 0 else 1.0

            # 类型一致性
            types = {type(v).__name__ for v in non_null}
            type_consistent = len(types) <= 1

            field_stats[key] = {
                "present_count": len(non_null),
                "null_rate": round(null_rate, 4),
                "types": list(types),
                "type_consistent": type_consistent,
                "sample_values": [str(v)[:100] for v in non_null[:3]]
            }

        # Schema匹配度
        schema_match = 1.0
        missing_fields = []
        if expected_schema:
            required = expected_schema.get("required", list(expected_schema.keys()))
            present = all_keys
            missing_fields = [f for f in required if f not in present]
            schema_match = 1.0 - len(missing_fields) / len(required) if required else 1.0

        # 整体质量评分
        avg_null_rate = sum(fs["null_rate"] for fs in field_stats.values()) / len(field_stats) if field_stats else 1.0
        quality_score = (1.0 - avg_null_rate) * 0.5 + schema_match * 0.3 + 0.2  # 基础分

        # 质量判定
        if quality_score > 0.9:
            quality = "excellent"
        elif quality_score > 0.75:
            quality = "good"
        elif quality_score > 0.6:
            quality = "fair"
        else:
            quality = "poor"

        return {
            "total_records": n,
            "total_fields": len(all_keys),
            "field_quality": field_stats,
            "schema_match": round(schema_match, 4),
            "missing_required_fields": missing_fields,
            "overall_quality_score": round(quality_score, 4),
            "quality": quality,
            "status": "complete"
        }


# ============================================================
# 3. 来源可信度分级
# ============================================================

class SourceCredibilityTier:
    """来源可信度分级引擎"""

    # 平台基准可信度
    PLATFORM_BASELINE = {
        "huggingface": 80,
        "kaggle": 75,
        "arxiv": 70,
        "github": 70,
        "official_api": 85,
        "gov_data": 90,
        "public_web": 40,
        "social_media": 25,
        "unknown": 30,
    }

    @staticmethod
    def assess_credibility(source: Dict, cross_validation: List[Dict] = None) -> Dict:
        """评估来源可信度"""
        platform = source.get("platform", "unknown").lower()
        baseline = SourceCredibilityTier.PLATFORM_BASELINE.get(platform, 30)

        # 调整因子
        adjustments = []

        # 是否有DOI/永久ID
        if source.get("doi") or source.get("arxiv_id"):
            baseline += 10
            adjustments.append({"factor": "persistent_id", "adjustment": +10})

        # 是否有明确的机构/作者
        if source.get("author") and len(str(source.get("author", ""))) > 3:
            baseline += 5
            adjustments.append({"factor": "author_verified", "adjustment": +5})

        # 描述是否充分
        desc = source.get("description", "")
        if len(desc) > 200:
            baseline += 5
            adjustments.append({"factor": "detailed_description", "adjustment": +5})
        elif len(desc) < 20:
            baseline -= 10
            adjustments.append({"factor": "vague_description", "adjustment": -10})

        # 交叉验证一致性
        cross_consistency = None
        if cross_validation:
            cross_consistency = SourceCredibilityTier._cross_validate(source, cross_validation)
            if cross_consistency > 0.8:
                baseline += 10
                adjustments.append({"factor": "cross_validation_high", "adjustment": +10})
            elif cross_consistency < 0.4:
                baseline -= 15
                adjustments.append({"factor": "cross_validation_low", "adjustment": -15})

        credibility = max(0, min(100, baseline))

        # 信度分级
        if credibility >= 85:
            tier = "A"  # 高度可信
        elif credibility >= 70:
            tier = "B"  # 可信
        elif credibility >= 50:
            tier = "C"  # 需验证
        else:
            tier = "D"  # 不可信

        return {
            "source_id": source.get("id", ""),
            "platform": platform,
            "credibility_score": round(credibility, 2),
            "tier": tier,
            "adjustments": adjustments,
            "cross_validation_consistency": cross_consistency,
            "recommendation": SourceCredibilityTier._recommendation(tier),
        }

    @staticmethod
    def _cross_validate(source: Dict, other_sources: List[Dict]) -> float:
        """交叉验证: 检查多个来源对同一数据的一致性"""
        if not other_sources:
            return 0.5

        matches = 0
        total_checks = 0

        source_name = str(source.get("name", "")).lower()
        source_desc = str(source.get("description", "")).lower()
        source_format = str(source.get("format", "")).lower()

        for other in other_sources:
            if other.get("id") == source.get("id"):
                continue

            other_name = str(other.get("name", "")).lower()
            other_desc = str(other.get("description", "")).lower()
            other_format = str(other.get("format", "")).lower()

            # 名称相似度 (简化)
            if source_name and other_name:
                total_checks += 1
                # 简单重叠词检测
                src_words = set(source_name.split())
                oth_words = set(other_name.split())
                if src_words and oth_words:
                    overlap = len(src_words & oth_words) / max(len(src_words), len(oth_words))
                    if overlap > 0.3:
                        matches += 1

            # 格式一致性
            if source_format and other_format:
                total_checks += 1
                if source_format == other_format:
                    matches += 1

        return matches / total_checks if total_checks > 0 else 0.5

    @staticmethod
    def _recommendation(tier: str) -> str:
        recs = {
            "A": "可直接用于生产训练",
            "B": "建议抽样验证后使用",
            "C": "必须全量审核后使用",
            "D": "不建议使用,或仅作参考",
        }
        return recs.get(tier, "未知")


# ============================================================
# 4. IAA: 多源交叉验证一致性
# ============================================================

class MultiSourceCrossValidator:
    """多源交叉验证 — 评估不同数据源对同一概念/实体的标注一致性"""

    @staticmethod
    def compute_multi_source_agreement(sources_data: Dict[str, List[Dict]],
                                       key_field: str = "label") -> Dict:
        """
        计算多源数据一致性
        sources_data: {"source_A": [...], "source_B": [...], ...}
        """
        if len(sources_data) < 2:
            return {"error": "需要至少2个数据源", "status": "insufficient_data"}

        source_names = list(sources_data.keys())
        n_sources = len(source_names)

        # 找出所有共同项 (通过ID或其他唯一标识)
        all_ids = None
        for items in sources_data.values():
            ids = {item.get("id", item.get("name", "")) for item in items}
            if all_ids is None:
                all_ids = ids
            else:
                all_ids = all_ids & ids

        if not all_ids:
            return {"error": "数据源之间无共同项", "common_items": 0, "status": "no_overlap"}

        # 逐项比较
        pair_agreements = defaultdict(list)
        item_agreements = {}

        for item_id in sorted(all_ids):
            values = {}
            for src_name, items in sources_data.items():
                item = next((i for i in items if i.get("id", i.get("name")) == item_id), None)
                if item:
                    values[src_name] = item.get(key_field)

            # 两两比较
            src_list = list(values.keys())
            agreements_for_item = []
            for i in range(len(src_list)):
                for j in range(i + 1, len(src_list)):
                    a_val = values[src_list[i]]
                    b_val = values[src_list[j]]
                    agree = 1.0 if a_val == b_val else 0.0
                    pair_agreements[(src_list[i], src_list[j])].append(agree)
                    agreements_for_item.append(agree)

            item_agreements[item_id] = {
                "values": {k: str(v)[:100] for k, v in values.items()},
                "agreement_rate": round(sum(agreements_for_item) / len(agreements_for_item), 4)
                if agreements_for_item else 0
            }

        # 每对源的一致性
        pairwise_consistency = {}
        all_rates = []
        for pair, agreements in pair_agreements.items():
            rate = sum(agreements) / len(agreements) if agreements else 0
            pairwise_consistency[f"{pair[0]} vs {pair[1]}"] = round(rate, 4)
            all_rates.append(rate)

        overall_consistency = sum(all_rates) / len(all_rates) if all_rates else 0

        # 质量判定
        if overall_consistency > 0.9:
            quality = "excellent"
        elif overall_consistency > 0.75:
            quality = "good"
        elif overall_consistency > 0.6:
            quality = "moderate"
        elif overall_consistency > 0.4:
            quality = "low"
        else:
            quality = "poor"

        return {
            "n_sources": n_sources,
            "common_items": len(all_ids),
            "pairwise_consistency": pairwise_consistency,
            "overall_consistency": round(overall_consistency, 4),
            "quality": quality,
            "item_details": item_agreements,
            "industry_benchmark": {
                "commercial_annotation": 0.90,
                "crowdsourcing": 0.75,
                "automated": 0.85
            },
            "status": "complete"
        }

    @staticmethod
    def detect_anomalies(sources_data: Dict[str, List[Dict]],
                         key_field: str = "label") -> List[Dict]:
        """检测多源数据中的异常/冲突"""
        consensus = MultiSourceCrossValidator.compute_multi_source_agreement(
            sources_data, key_field
        )
        if consensus.get("status") != "complete":
            return []

        anomalies = []
        for item_id, detail in consensus.get("item_details", {}).items():
            if detail["agreement_rate"] < 0.5:
                anomalies.append({
                    "item_id": item_id,
                    "agreement_rate": detail["agreement_rate"],
                    "conflicting_values": detail["values"],
                    "severity": "high" if detail["agreement_rate"] < 0.3 else "medium"
                })

        return sorted(anomalies, key=lambda x: x["agreement_rate"])


# ============================================================
# 5. LLM辅助寻源评估
# ============================================================

class LLMSourceEvaluator:
    """LLM辅助评估数据源质量"""

    @staticmethod
    def evaluate_source_with_llm(source: Dict, criteria: List[str] = None) -> Dict:
        """使用LLM评估单个数据源的质量"""
        if criteria is None:
            criteria = ["relevance", "completeness", "authority", "timeliness"]

        eval_prompt = f"""你是一个数据源质量评估专家。请评估以下数据源:

数据源信息:
- 名称: {source.get('name', 'N/A')}
- 平台: {source.get('platform', 'N/A')}
- 描述: {source.get('description', 'N/A')[:500]}
- 许可证: {source.get('license', 'N/A')}
- 格式: {source.get('format', 'N/A')}

评估维度 (每项1-10分):
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(criteria))}

输出JSON格式:
{{"scores": {{"relevance": 8, ...}}, "overall": 7.5, "summary": "...", "risks": ["..."], "recommendation": "..."}}
"""

        try:
            from engines.model_gateway import get_gateway
            gw = get_gateway()
            resp = gw.chat([{"role": "user", "content": eval_prompt}], model="auto")
            import re
            json_match = re.search(r'\{[\s\S]*\}', resp.content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Operation failed: {e}")

        return {
            "scores": {c: 7 for c in criteria},
            "overall": 7.0,
            "summary": "无法调用LLM评估(离线模式)",
            "risks": [],
            "recommendation": "请手动评估"
        }


# 单例
_discovery_quality: DiscoveryQualityEngine = None
_preview_checker: SourcePreviewChecker = None
_credibility_tier: SourceCredibilityTier = None
_cross_validator: MultiSourceCrossValidator = None

def get_discovery_quality():
    global _discovery_quality
    _discovery_quality = _discovery_quality or DiscoveryQualityEngine()
    return _discovery_quality

def get_preview_checker():
    global _preview_checker
    _preview_checker = _preview_checker or SourcePreviewChecker()
    return _preview_checker

def get_credibility_tier():
    global _credibility_tier
    _credibility_tier = _credibility_tier or SourceCredibilityTier()
    return _credibility_tier

def get_cross_validator():
    global _cross_validator
    _cross_validator = _cross_validator or MultiSourceCrossValidator()
    return _cross_validator
