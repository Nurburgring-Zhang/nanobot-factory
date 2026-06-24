"""算子库 — 44原子数据处理算子

6大类: 采集(7) / 清洗(12) / 标注(8) / 评分(5) / 筛选(5) / 导出(6)
从 core.operators_lib 完整导出算子体系
"""

from core.operators_lib import (
    # 基类与结果
    BaseOperator,
    OperatorResult,
    # 算子工厂函数
    get_operator,
    list_operators,
    OPERATOR_REGISTRY,
    # 采集(7)
    SourceLocalFile,
    SourceOSS,
    SourceWebCrawler,
    SourceDatabase,
    SourceRSS,
    SourceAPI,
    SourceScreenshot,
    # 清洗/过滤(12)
    FilterResolution,
    FilterDuration,
    FilterAspectRatio,
    FilterBlur,
    FilterNSFW,
    FilterDedupMD5,
    FilterDedupPhash,
    FilterLanguage,
    FilterSensitive,
    FilterNoise,
    FilterSNR,
    FilterToxicity,
    # 标注(8)
    LabelImageClassification,
    LabelObjectDetection,
    LabelImageCaption,
    LabelImageTagging,
    LabelAesthetic,
    LabelSceneDetect,
    LabelKeyFrame,
    LabelSpeechRecognition,
    # 评分(5)
    ScoreAesthetic,
    ScoreTechnical,
    ScoreAlignment,
    ScoreDiversity,
    ScorePerplexity,
    # 筛选(5)
    SelectThreshold,
    SelectTopK,
    SelectRandom,
    SelectStratified,
    SelectDiversity,
    # 导出(6)
    ExportJSONL,
    ExportParquet,
    ExportCSV,
    ExportLLaVA,
    ExportCOCO,
    ExportLocal,
)

__all__ = [
    "BaseOperator", "OperatorResult",
    "get_operator", "list_operators", "OPERATOR_REGISTRY",
    # 采集
    "SourceLocalFile", "SourceOSS", "SourceWebCrawler", "SourceDatabase",
    "SourceRSS", "SourceAPI", "SourceScreenshot",
    # 清洗
    "FilterResolution", "FilterDuration", "FilterAspectRatio", "FilterBlur",
    "FilterNSFW", "FilterDedupMD5", "FilterDedupPhash", "FilterLanguage",
    "FilterSensitive", "FilterNoise", "FilterSNR", "FilterToxicity",
    # 标注
    "LabelImageClassification", "LabelObjectDetection", "LabelImageCaption",
    "LabelImageTagging", "LabelAesthetic", "LabelSceneDetect",
    "LabelKeyFrame", "LabelSpeechRecognition",
    # 评分
    "ScoreAesthetic", "ScoreTechnical", "ScoreAlignment",
    "ScoreDiversity", "ScorePerplexity",
    # 筛选
    "SelectThreshold", "SelectTopK", "SelectRandom",
    "SelectStratified", "SelectDiversity",
    # 导出
    "ExportJSONL", "ExportParquet", "ExportCSV",
    "ExportLLaVA", "ExportCOCO", "ExportLocal",
]
