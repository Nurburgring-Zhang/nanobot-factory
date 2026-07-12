"""智影 V5 — MoA 子包: Mixture of Agents

迁移自 Hermes Agent MoA:
- 多个参考模型各自思考
- aggregator 真正输出答案、调用工具
- 参考模型只给观点, 不拿工具 schema
"""
from .moa_engine import (
    MoAEngine,
    MoAConfig,
    MoAReference,
    MoAResult,
    MoAMode,
    moa_engine,
)

__all__ = [
    "MoAEngine",
    "MoAConfig",
    "MoAReference",
    "MoAResult",
    "MoAMode",
    "moa_engine",
]
