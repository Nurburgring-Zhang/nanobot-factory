"""
智影算子库 — 44个算子 + OPERATOR_REGISTRY
===========================================
基于智影数据工场平台设计文档第3章 + 开发文档第4章实现。
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import json, os, hashlib, re, logging

logger = logging.getLogger(__name__)


class OperatorCategory(str, Enum):
    SOURCE = "source"
    FILTER = "filter"
    LABEL = "label"
    SCORE = "score"
    SELECT = "select"
    EXPORT = "export"


@dataclass
class OperatorSchema:
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None


@dataclass
class Operator:
    id: str = ""
    name: str = ""
    category: OperatorCategory = OperatorCategory.FILTER
    description: str = ""
    parameters: Dict[str, OperatorSchema] = field(default_factory=dict)
    inputs: List[OperatorSchema] = field(default_factory=list)
    outputs: List[OperatorSchema] = field(default_factory=list)
    run_func: Optional[Callable] = None

    def run(self, data: Any, params: Dict = None) -> Any:
        if self.run_func:
            return self.run_func(data, params or {})
        # 默认实现: 基于算子类型的通用处理
        params = params or {}
        if self.category == OperatorCategory.FILTER:
            # 清洗算子: 按参数过滤
            if self.id == "filter.null_filter":
                if isinstance(data, list):
                    return [x for x in data if x is not None and x != ""]
                return data
            elif self.id == "filter.length_filter":
                min_len = params.get("min", 0)
                max_len = params.get("max", 100000)
                if isinstance(data, list):
                    return [x for x in data if min_len <= (len(str(x)) if not isinstance(x, int) else x) <= max_len]
                return data
            elif self.id == "filter.dedup_md5":
                if isinstance(data, list):
                    seen = set()
                    result = []
                    for x in data:
                        h = hashlib.md5(str(x).encode()).hexdigest()
                        if h not in seen:
                            seen.add(h)
                            result.append(x)
                    return result
                return data
            elif self.id == "filter.html_cleaner":
                import re
                if isinstance(data, str):
                    return re.sub(r'<[^>]+>', '', data)
                return data
            elif self.id == "filter.whitespace_normalizer":
                if isinstance(data, str):
                    return ' '.join(data.split())
                return data
            elif self.id == "filter.regex_filter":
                pattern = params.get("pattern")
                if pattern and isinstance(data, list):
                    import re
                    return [x for x in data if not re.search(pattern, str(x))]
                return data
        elif self.category == OperatorCategory.SOURCE:
            return data  # 采集算子在外部调用
        elif self.category == OperatorCategory.LABEL:
            return data  # 标注算子在外部调用
        elif self.category == OperatorCategory.SCORE:
            # 评分算子: 返回随机分数(占位)
            if isinstance(data, list):
                import random
                return [{"input": x, "score": random.uniform(0.5, 1.0)} for x in data]
            return data
        elif self.category == OperatorCategory.SELECT:
            k = params.get("k", 10)
            if isinstance(data, list):
                return data[:min(k, len(data))]
            return data
        elif self.category == OperatorCategory.EXPORT:
            return data  # 导出算子在外部调用
        return data


class OperatorRegistry:
    def __init__(self):
        self._operators: Dict[str, Operator] = {}
        self._register_all()

    def register(self, op: Operator):
        self._operators[op.id] = op

    def get(self, op_id: str) -> Optional[Operator]:
        return self._operators.get(op_id)

    def list_by_category(self, category: OperatorCategory) -> List[Operator]:
        return [op for op in self._operators.values() if op.category == category]

    def list_all(self) -> List[Operator]:
        return list(self._operators.values())

    def count(self) -> int:
        return len(self._operators)

    def _register_all(self):
        cats = OperatorCategory
        # 采集(7)
        for args in [
            ("source.web_scraper", "网页爬取", cats.SOURCE, "从URL列表或RSS订阅批量采集网页内容", {"urls":("array","URL列表",True),"depth":("number","爬取深度",False,1)}),
            ("source.rss_collector", "RSS订阅采集", cats.SOURCE, "从RSS/Atom订阅源自动采集", {"feeds":("array","订阅URL",True),"max_per_feed":("number","每源最大条数",False,50)}),
            ("source.api_puller", "API拉取", cats.SOURCE, "通过REST API定时拉取数据", {"api_url":("string","API端点",True)}),
            ("source.db_sync", "数据库同步", cats.SOURCE, "从关系型数据库同步", {"conn_str":("string","连接串",True),"query":("string","SQL",True)}),
            ("source.file_importer", "文件导入", cats.SOURCE, "批量导入本地文件", {"paths":("array","文件路径",True),"format":("string","格式",True)}),
            ("source.clipboard_monitor", "剪贴板监听", cats.SOURCE, "监听剪贴板自动保存", {}),
            ("source.screenshot", "截图采集", cats.SOURCE, "内置截图工具", {"delay":("number","延迟秒",False,0)}),
        ]:
            op = Operator(id=args[0], name=args[1], category=args[2], description=args[3])
            for k,v in args[4].items():
                op.parameters[k] = OperatorSchema(type=v[0], description=v[1], required=v[2], default=v[3] if len(v)>3 else None)
            self.register(op)

        # 清洗(13)
        for args in [
            ("filter.null_filter", "空值过滤", cats.FILTER, "删除空内容", {}),
            ("filter.length_filter", "长度过滤", cats.FILTER, "按长度筛选", {"min":("number","最小字符",False,0),"max":("number","最大字符",False,100000)}),
            ("filter.dedup_md5", "MD5精确去重", cats.FILTER, "基于MD5哈希去重", {}),
            ("filter.dedup_minhash", "MinHash近似去重", cats.FILTER, "近似去重", {"threshold":("number","阈值",False,0.8)}),
            ("filter.lang_detector", "语言检测", cats.FILTER, "识别过滤非目标语言", {"target":("string","目标语言",False,"zh")}),
            ("filter.sensitive_filter", "敏感词过滤", cats.FILTER, "过滤敏感内容", {"mode":("string","drop/mask/warn",False,"drop")}),
            ("filter.spam_filter", "垃圾过滤", cats.FILTER, "过滤广告乱码", {}),
            ("filter.regex_filter", "正则过滤", cats.FILTER, "正则规则过滤", {"pattern":("string","正则",True)}),
            ("filter.html_cleaner", "HTML清洗", cats.FILTER, "去除HTML标签", {}),
            ("filter.markdown_converter", "Markdown转换", cats.FILTER, "Markdown转纯文本", {}),
            ("filter.whitespace_normalizer", "空白规范化", cats.FILTER, "合并多余空格", {}),
            ("filter.unicode_normalizer", "Unicode规范化", cats.FILTER, "统一Unicode", {"form":("string","NFC/NFD/NFKC",False,"NFKC")}),
            ("filter.pii_detector", "PII检测脱敏", cats.FILTER, "识别脱敏隐私信息", {"mode":("string","detect/mask",False,"mask")}),
        ]:
            op = Operator(id=args[0], name=args[1], category=args[2], description=args[3])
            for k,v in args[4].items():
                op.parameters[k] = OperatorSchema(type=v[0], description=v[1], required=v[2], default=v[3] if len(v)>3 else None)
            self.register(op)

        # 标注(8)
        for args in [
            ("label.text_classifier", "文本分类", cats.LABEL, "文本分类标注", {"labels":("array","候选标签",True)}),
            ("label.sequence_labeler", "序列标注", cats.LABEL, "序列标注", {"entities":("array","实体类型",True)}),
            ("label.text_pair", "文本对标注", cats.LABEL, "相似度标注", {"relations":("array","关系类型",True)}),
            ("label.generation_eval", "生成评估", cats.LABEL, "生成质量评估", {}),
            ("label.instruction_label", "指令标注", cats.LABEL, "指令意图识别", {"intents":("array","意图列表",True)}),
            ("label.dialogue_label", "对话标注", cats.LABEL, "多轮对话标注", {}),
            ("label.preference_label", "偏好标注", cats.LABEL, "DPO偏好数据", {"choices":("number","候选数",False,2)}),
            ("label.image_labeler", "图像标注", cats.LABEL, "图像分类标注", {"task":("string","任务类型",True)}),
        ]:
            op = Operator(id=args[0], name=args[1], category=args[2], description=args[3])
            for k,v in args[4].items():
                op.parameters[k] = OperatorSchema(type=v[0], description=v[1], required=v[2], default=v[3] if len(v)>3 else None)
            self.register(op)

        # 评分(5)
        for args in [
            ("score.aesthetic", "美学评分", cats.SCORE, "图像美学评分0-100", {}),
            ("score.technical_quality", "技术质量", cats.SCORE, "技术指标评分", {}),
            ("score.nsfw_detector", "NSFW检测", cats.SCORE, "不安全内容检测", {}),
            ("score.coherence", "连贯性评分", cats.SCORE, "时序连贯性评分", {}),
            ("score.diversity", "多样性评分", cats.SCORE, "数据集多样性", {}),
        ]:
            self.register(Operator(id=args[0], name=args[1], category=args[2], description=args[3]))

        # 筛选(5)
        for args in [
            ("select.top_k", "Top-K选取", cats.SELECT, "按评分取前K", {"k":("number","数量",True)}),
            ("select.diversity_sampler", "多样性采样", cats.SELECT, "特征多样性子集采样", {"size":("number","目标数量",True)}),
            ("select.hard_mining", "困难挖掘", cats.SELECT, "选取困难样本", {"ratio":("number","比例",False,0.3)}),
            ("select.random_sampler", "随机采样", cats.SELECT, "随机抽取子集", {"size":("number","数量",True)}),
            ("select.threshold_filter", "阈值过滤", cats.SELECT, "评分阈值筛选", {"field":("string","字段",True),"min":("number","最低",False)}),
        ]:
            op = Operator(id=args[0], name=args[1], category=args[2], description=args[3])
            for k,v in args[4].items():
                op.parameters[k] = OperatorSchema(type=v[0], description=v[1], required=v[2], default=v[3] if len(v)>3 else None)
            self.register(op)

        # 导出(6)
        for args in [
            ("export.coco", "COCO导出", cats.EXPORT, "COCO JSON格式", {"path":("string","输出路径",True)}),
            ("export.webdataset", "WebDataset", cats.EXPORT, "WebDataset tar包", {"dir":("string","输出目录",True)}),
            ("export.jsonl", "JSONL导出", cats.EXPORT, "每行JSON", {"path":("string","输出路径",True)}),
            ("export.parquet", "Parquet导出", cats.EXPORT, "Parquet列存", {"path":("string","输出路径",True)}),
            ("export.llava", "LLaVA导出", cats.EXPORT, "LLaVA指令格式", {"path":("string","输出路径",True)}),
            ("export.internvl", "InternVL导出", cats.EXPORT, "InternVL对话格式", {"path":("string","输出路径",True)}),
        ]:
            op = Operator(id=args[0], name=args[1], category=args[2], description=args[3])
            for k,v in args[4].items():
                op.parameters[k] = OperatorSchema(type=v[0], description=v[1], required=v[2], default=v[3] if len(v)>3 else None)
            self.register(op)


_registry: Optional[OperatorRegistry] = None


def get_registry() -> OperatorRegistry:
    global _registry
    if _registry is None:
        _registry = OperatorRegistry()
    return _registry
