"""统计仪表盘

三维统计:
- 用户维度: 个人产出/准确率/评分/排行
- 项目维度: 数据量/类型分布/完成率/成本
- 全局维度: DAU/MAU/总量/增长趋势

排行: 标注效率排行 / 质量排行 / 综合排行
"""

from core.stats_manager import (
    UserStats,
    ProjectStats,
    GlobalStats,
    Ranking,
    StatsManager,
)

__all__ = [
    "UserStats", "ProjectStats", "GlobalStats",
    "Ranking", "StatsManager",
]
