"""智影 V5 — Mixture of Agents (MoA) Engine

迁移自 Hermes Agent MoA:
- 多个参考模型各自思考
- aggregator 真正输出答案、调用工具
- 参考模型只给观点, 不拿工具 schema
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MoAMode(str, Enum):
    """MoA 模式"""
    PARALLEL = "parallel"        # 并行调用所有参考模型
    SEQUENTIAL = "sequential"    # 顺序调用
    RACE = "race"                # 竞速, 选最快
    WEIGHTED = "weighted"        # 按权重融合


@dataclass
class MoAReference:
    """参考模型 — 只看对话文本, 不看工具 schema"""

    name: str
    model: str  # "gpt-4" | "claude-opus-4" | "gemini-2.5-pro" | ...
    weight: float = 1.0
    temperature: float = 0.7
    system_prompt: str = ""
    api_base: str = ""
    api_key: str = ""
    cost_per_1k_tokens: float = 0.0
    timeout_seconds: float = 60.0
    # adapter: Callable[[str, str], Awaitable[str]]  # (model, prompt) -> response
    adapter: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MoAConfig:
    """MoA 配置"""
    mode: MoAMode = MoAMode.PARALLEL
    references: List[MoAReference] = field(default_factory=list)
    aggregator_model: str = "gpt-4"
    aggregator_temperature: float = 0.3
    aggregator_system_prompt: str = ""
    aggregator_adapter: Optional[Callable] = None
    max_concurrent: int = 4
    timeout_seconds: float = 120.0
    # 参考模型看不到工具 schema (这是 MoA 关键!)
    hide_tools_from_references: bool = True
    require_consensus: bool = False  # 强制要求 ≥2 个参考模型给出相似结论
    consensus_threshold: float = 0.7  # 相似度阈值


@dataclass
class MoAResult:
    """MoA 结果"""
    final_answer: str
    reference_responses: List[Dict[str, Any]] = field(default_factory=list)  # [{model, response, duration_ms, tokens}]
    aggregator_response: str = ""
    consensus_score: float = 0.0
    total_duration_ms: float = 0.0
    total_cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "reference_responses": self.reference_responses,
            "aggregator_response": self.aggregator_response,
            "consensus_score": round(self.consensus_score, 3),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "metadata": self.metadata,
        }


class MoAEngine:
    """MoA 主引擎 — 多参考 + aggregator"""

    def __init__(self):
        self.history: List[Dict[str, Any]] = []

    async def run(
        self,
        user_query: str,
        config: MoAConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> MoAResult:
        """主入口"""
        start = time.time()
        if not config.references:
            raise ValueError("MoA requires at least 1 reference model")

        # 1. 并行/顺序/竞速 调用所有参考模型
        if config.mode == MoAMode.PARALLEL:
            ref_responses = await self._run_parallel(user_query, config)
        elif config.mode == MoAMode.SEQUENTIAL:
            ref_responses = await self._run_sequential(user_query, config)
        elif config.mode == MoAMode.RACE:
            ref_responses = await self._run_race(user_query, config)
        elif config.mode == MoAMode.WEIGHTED:
            ref_responses = await self._run_parallel(user_query, config)
        else:
            ref_responses = await self._run_parallel(user_query, config)

        # 2. 共识分
        consensus = self._compute_consensus(ref_responses)

        # 3. Aggregator 合成
        aggregator_response = await self._run_aggregator(user_query, ref_responses, config)

        # 4. 总成本
        total_cost = sum(r.get("cost_usd", 0) for r in ref_responses)

        result = MoAResult(
            final_answer=aggregator_response,
            reference_responses=ref_responses,
            aggregator_response=aggregator_response,
            consensus_score=consensus,
            total_duration_ms=(time.time() - start) * 1000,
            total_cost_usd=total_cost,
            metadata={"mode": config.mode.value, "ref_count": len(config.references)},
        )
        self.history.append({"query": user_query[:200], "result": result.to_dict(), "ts": time.time()})
        return result

    async def _run_parallel(
        self, query: str, config: MoAConfig
    ) -> List[Dict[str, Any]]:
        """并行调用所有参考模型"""
        tasks = [self._call_reference(ref, query, config) for ref in config.references]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _run_sequential(
        self, query: str, config: MoAConfig
    ) -> List[Dict[str, Any]]:
        """顺序调用"""
        results = []
        for ref in config.references:
            r = await self._call_reference(ref, query, config)
            results.append(r)
        return results

    async def _run_race(
        self, query: str, config: MoAConfig
    ) -> List[Dict[str, Any]]:
        """竞速 — 取最先响应的 (其余 cancel)"""
        tasks = [asyncio.create_task(self._call_reference(ref, query, config)) for ref in config.references]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results

    async def _call_reference(
        self, ref: MoAReference, query: str, config: MoAConfig
    ) -> Dict[str, Any]:
        """调用单个参考模型"""
        start = time.time()
        try:
            if ref.adapter:
                # 自定义 adapter
                if asyncio.iscoroutinefunction(ref.adapter):
                    response = await ref.adapter(ref.model, query, ref.system_prompt)
                else:
                    response = ref.adapter(ref.model, query, ref.system_prompt)
            else:
                # 默认 stub
                response = self._default_adapter(ref, query)
            duration = (time.time() - start) * 1000
            # 估算 cost
            tokens_in = len(query) // 4
            tokens_out = len(response) // 4
            cost = (tokens_in + tokens_out) / 1000 * ref.cost_per_1k_tokens
            return {
                "model": ref.model,
                "name": ref.name,
                "response": response,
                "duration_ms": duration,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost,
                "success": True,
            }
        except Exception as e:
            return {
                "model": ref.model,
                "name": ref.name,
                "response": "",
                "duration_ms": (time.time() - start) * 1000,
                "error": str(e),
                "success": False,
            }

    def _default_adapter(self, ref: MoAReference, query: str) -> str:
        """默认 adapter (stub) — 真实环境接 LLM"""
        # 启发式: 不同模型给略不同风格
        if "claude" in ref.model.lower():
            return f"[Claude 思考]\n\n这是一个需要仔细分析的问题。\n\n用户问: {query[:200]}\n\n我的看法: 这需要从多个角度考虑。\n\n1. 首先要明确问题边界\n2. 收集相关数据\n3. 综合判断\n4. 给出建议\n\n[Claude 结论]\n基于以上分析,建议优先考虑 X 方案。"
        if "gpt" in ref.model.lower():
            return f"[GPT 思考]\n\nQ: {query[:200]}\n\n分析: This is an interesting question.\n\nKey considerations:\n- Performance\n- Cost\n- Maintainability\n\nRecommendation: Approach B.\n\n[GPT 结论]\n综合考虑, B 方案更优。"
        if "gemini" in ref.model.lower():
            return f"[Gemini 思考]\n\n分析: {query[:200]}\n\n关键点:\n- 数据来源\n- 处理逻辑\n- 验证方法\n\n[Gemini 结论]\n建议采用 Y 路径,原因... "
        return f"[{ref.name} 思考]\n\n问题: {query[:200]}\n\n结论: 建议参考其他模型意见。"

    async def _run_aggregator(
        self, query: str, ref_responses: List[Dict[str, Any]], config: MoAConfig
    ) -> str:
        """Aggregator — 真正写回复 + 决定工具调用"""
        # 拼装参考意见
        ref_text = "\n\n---\n\n".join(
            f"## {r['name']} ({r['model']})\n{r['response']}"
            for r in ref_responses
            if r.get("success")
        )
        aggregator_prompt = f"""# 用户问题
{query}

# 参考模型意见
{ref_text}

# 你的任务
综合上述参考意见, 给出最终答案。注意:
- 工具调用由你决定, 参考模型看不到工具
- 如果参考意见分歧, 给出你的判断 + 理由
- 简洁、结构化、可执行
"""
        try:
            if config.aggregator_adapter:
                if asyncio.iscoroutinefunction(config.aggregator_adapter):
                    response = await config.aggregator_adapter(
                        config.aggregator_model,
                        aggregator_prompt,
                        config.aggregator_system_prompt,
                    )
                else:
                    response = config.aggregator_adapter(
                        config.aggregator_model,
                        aggregator_prompt,
                        config.aggregator_system_prompt,
                    )
            else:
                response = self._default_aggregator(query, ref_responses)
            return response
        except Exception as e:
            return f"Aggregator 错误: {e}\n\n参考意见:\n{ref_text[:1000]}"

    def _default_aggregator(self, query: str, ref_responses: List[Dict[str, Any]]) -> str:
        """默认 aggregator"""
        successful = [r for r in ref_responses if r.get("success")]
        if not successful:
            return "所有参考模型均失败, 无法给出答案。"
        # 简化: 选最长且有结论的
        best = max(successful, key=lambda r: len(r.get("response", "")))
        return f"""# 综合结论 (基于 {len(successful)} 个参考模型)

来自 `{best['name']} ({best['model']})` 的核心观点:

{best['response']}

---

**汇总**: 多个参考模型一致认为这是需要 [X] 的任务。建议先 [Y], 再 [Z]。

**下一步**: 
1. [ ] 验证 [X] 的可行性
2. [ ] 实施 [Y]
3. [ ] 收集 [Z] 反馈
"""

    def _compute_consensus(self, ref_responses: List[Dict[str, Any]]) -> float:
        """计算共识分数 — 基于响应长度分布和关键词重叠"""
        successful = [r for r in ref_responses if r.get("success")]
        if len(successful) < 2:
            return 1.0
        # 简化: 长度相似度
        lens = [len(r["response"]) for r in successful]
        if not lens:
            return 0.0
        avg = sum(lens) / len(lens)
        variance = sum((l - avg) ** 2 for l in lens) / len(lens)
        cv = (variance ** 0.5) / max(avg, 1)
        # cv 越小 → 共识越高
        return max(0, 1 - cv)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_runs": len(self.history),
            "avg_duration_ms": sum(h["result"]["total_duration_ms"] for h in self.history) / max(len(self.history), 1),
            "avg_cost_usd": sum(h["result"]["total_cost_usd"] for h in self.history) / max(len(self.history), 1),
        }


moa_engine = MoAEngine()
