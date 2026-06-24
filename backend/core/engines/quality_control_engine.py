#!/usr/bin/env python3
"""
NanoBot Factory 质量控制引擎 (Quality Control Engine)
=====================================================

负责验证输入、评估输出质量、确保响应格式和安全。

核心功能：
1. 输入验证 - 验证用户输入的合法性和安全性
2. 输出质量评估 - 评估Agent输出的质量
3. 响应格式检查 - 确保输出符合格式要求
4. 安全性检查 - 检测潜在的安全问题
5. 性能监控 - 监控响应时间和资源使用

@author MiniMax Agent
@date 2026-04-14
"""

import asyncio
import logging
import re
import json
import time
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import html
import urllib.parse

logger = logging.getLogger(__name__)


class QualityLevel(Enum):
    """质量等级"""
    EXCELLENT = "excellent"  # 优秀 (>=90分)
    GOOD = "good"           # 良好 (>=75分)
    ACCEPTABLE = "acceptable"  # 可接受 (>=60分)
    POOR = "poor"           # 较差 (>=40分)
    FAIL = "fail"           # 不合格 (<40分)


class ValidationResult(Enum):
    """验证结果"""
    PASS = "pass"           # 通过
    WARNING = "warning"     # 警告
    FAIL = "fail"          # 失败


@dataclass
class QualityScore:
    """质量评分"""
    overall: float = 0.0          # 综合评分 (0-100)
    accuracy: float = 0.0        # 准确性
    completeness: float = 0.0    # 完整性
    clarity: float = 0.0         # 清晰度
    safety: float = 0.0           # 安全性
    format_score: float = 0.0    # 格式正确性
    relevance: float = 0.0        # 相关性
    
    @property
    def level(self) -> QualityLevel:
        """获取质量等级"""
        if self.overall >= 90:
            return QualityLevel.EXCELLENT
        elif self.overall >= 75:
            return QualityLevel.GOOD
        elif self.overall >= 60:
            return QualityLevel.ACCEPTABLE
        elif self.overall >= 40:
            return QualityLevel.POOR
        else:
            return QualityLevel.FAIL


@dataclass
class ValidationReport:
    """验证报告"""
    result: ValidationResult
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        return self.result in [ValidationResult.PASS, ValidationResult.WARNING]


@dataclass
class QualityReport:
    """质量报告"""
    score: QualityScore
    validation: ValidationReport
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InputValidationConfig:
    """输入验证配置"""
    max_length: int = 10000          # 最大输入长度
    min_length: int = 1             # 最小输入长度
    allowed_languages: List[str] = None  # 允许的语言
    block_patterns: List[str] = None     # 拦截模式
    require_sanitization: bool = True    # 需要清理
    max_urls: int = 10              # 最大URL数量
    max_emails: int = 5             # 最大邮箱数量


@dataclass
class OutputQualityConfig:
    """输出质量配置"""
    min_quality_threshold: float = 60.0  # 最低质量阈值
    min_completeness: float = 70.0       # 最低完整度
    min_safety: float = 80.0             # 最低安全度
    require_format_check: bool = True     # 需要格式检查
    allow_partial_response: bool = True   # 允许部分响应


class InputValidator:
    """输入验证器"""
    
    # 恶意模式
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION)\b)",
        r"(--|/\*|\*/|#)",
        r"('|\"|;|\\)",
    ]
    
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
    ]
    
    # 路径遍历模式
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.\\",
        r"/etc/passwd",
        r"c:\\windows",
        r"boot\.ini",
    ]
    
    def __init__(self, config: Optional[InputValidationConfig] = None):
        self.config = config or InputValidationConfig()
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译正则表达式"""
        self._sql_patterns = [re.compile(p, re.IGNORECASE) for p in self.SQL_INJECTION_PATTERNS]
        self._xss_patterns = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in self.XSS_PATTERNS]
        self._path_patterns = [re.compile(p, re.IGNORECASE) for p in self.PATH_TRAVERSAL_PATTERNS]
        
        # 编译用户定义的拦截模式
        if self.config.block_patterns:
            self._block_patterns = [re.compile(p, re.IGNORECASE) for p in self.config.block_patterns]
        else:
            self._block_patterns = []
    
    async def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationReport:
        """
        验证输入
        
        Args:
            text: 待验证的文本
            context: 上下文信息
            
        Returns:
            验证报告
        """
        start_time = time.time()
        errors = []
        warnings = []
        suggestions = []
        
        # 1. 长度检查
        length_result = self._check_length(text)
        if length_result:
            warnings.append(length_result)
        
        # 2. SQL注入检查
        sql_result = self._check_sql_injection(text)
        if sql_result:
            errors.append(sql_result)
        
        # 3. XSS检查
        xss_result = self._check_xss(text)
        if xss_result:
            errors.append(xss_result)
        
        # 4. 路径遍历检查
        path_result = self._check_path_traversal(text)
        if path_result:
            errors.append(path_result)
        
        # 5. 用户定义模式检查
        pattern_result = self._check_custom_patterns(text)
        if pattern_result:
            errors.append(pattern_result)
        
        # 6. URL和邮箱检查
        url_email_result = self._check_urls_and_emails(text)
        if url_email_result:
            warnings.append(url_email_result)
        
        # 7. 清理建议
        if self.config.require_sanitization and any([sql_result, xss_result]):
            suggestions.append("建议对输入进行HTML转义和特殊字符过滤")
        
        # 确定验证结果
        if errors:
            result = ValidationResult.FAIL
        elif warnings:
            result = ValidationResult.WARNING
        else:
            result = ValidationResult.PASS
        
        processing_time = time.time() - start_time
        
        return ValidationReport(
            result=result,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            metadata={
                "input_length": len(text),
                "processing_time": processing_time,
                "has_urls": bool(re.search(r'https?://', text)),
                "has_emails": bool(re.search(r'\S+@\S+\.\S+', text)),
            }
        )
    
    def _check_length(self, text: str) -> Optional[str]:
        """检查长度"""
        if len(text) < self.config.min_length:
            return f"输入过短 (当前{len(text)}字符, 最少{self.config.min_length}字符)"
        if len(text) > self.config.max_length:
            return f"输入过长 (当前{len(text)}字符, 最多{self.config.max_length}字符)"
        return None
    
    def _check_sql_injection(self, text: str) -> Optional[str]:
        """检查SQL注入"""
        for pattern in self._sql_patterns:
            if pattern.search(text):
                return "检测到潜在的SQL注入模式"
        return None
    
    def _check_xss(self, text: str) -> Optional[str]:
        """检查XSS"""
        for pattern in self._xss_patterns:
            if pattern.search(text):
                return "检测到潜在的XSS攻击模式"
        return None
    
    def _check_path_traversal(self, text: str) -> Optional[str]:
        """检查路径遍历"""
        for pattern in self._path_patterns:
            if pattern.search(text):
                return "检测到潜在的路径遍历攻击"
        return None
    
    def _check_custom_patterns(self, text: str) -> Optional[str]:
        """检查自定义模式"""
        for pattern in self._block_patterns:
            if pattern.search(text):
                return "输入包含被拦截的内容"
        return None
    
    def _check_urls_and_emails(self, text: str) -> Optional[str]:
        """检查URL和邮箱数量"""
        urls = re.findall(r'https?://\S+', text)
        emails = re.findall(r'\S+@\S+\.\S+', text)
        
        warnings = []
        if len(urls) > self.config.max_urls:
            warnings.append(f"URL数量过多 ({len(urls)}个, 最多{self.config.max_urls}个)")
        if len(emails) > self.config.max_emails:
            warnings.append(f"邮箱数量过多 ({len(emails)}个, 最多{self.config.max_emails}个)")
        
        return "; ".join(warnings) if warnings else None
    
    def sanitize(self, text: str) -> str:
        """清理输入"""
        # HTML转义
        text = html.escape(text)
        # URL解码并重新转义（防止双重编码）
        try:
            text = urllib.parse.unquote(text)
            text = html.escape(text)
        except Exception:
            pass
        return text


class OutputQualityEvaluator:
    """输出质量评估器"""
    
    def __init__(self, config: Optional[OutputQualityConfig] = None):
        self.config = config or OutputQualityConfig()
    
    async def evaluate(
        self,
        output: str,
        expected: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> QualityScore:
        """
        评估输出质量
        
        Args:
            output: 待评估的输出
            expected: 期望输出（可选，用于准确性评估）
            context: 上下文信息
            
        Returns:
            质量评分
        """
        # 1. 准确性评估
        accuracy = await self._evaluate_accuracy(output, expected, context)
        
        # 2. 完整性评估
        completeness = self._evaluate_completeness(output, context)
        
        # 3. 清晰度评估
        clarity = self._evaluate_clarity(output)
        
        # 4. 安全性评估
        safety = self._evaluate_safety(output)
        
        # 5. 格式正确性评估
        format_score = self._evaluate_format(output)
        
        # 6. 相关性评估
        relevance = self._evaluate_relevance(output, context)
        
        # 计算综合评分（加权平均）
        overall = (
            accuracy * 0.25 +
            completeness * 0.20 +
            clarity * 0.15 +
            safety * 0.20 +
            format_score * 0.10 +
            relevance * 0.10
        )
        
        return QualityScore(
            overall=round(overall, 2),
            accuracy=round(accuracy, 2),
            completeness=round(completeness, 2),
            clarity=round(clarity, 2),
            safety=round(safety, 2),
            format_score=round(format_score, 2),
            relevance=round(relevance, 2)
        )
    
    async def _evaluate_accuracy(
        self,
        output: str,
        expected: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> float:
        """评估准确性"""
        score = 100.0
        
        # 检查输出是否为空
        if not output or not output.strip():
            return 0.0
        
        # 检查是否有明显的错误标记
        error_indicators = ["错误", "无法", "失败", "不对", "incorrect", "error", "failed"]
        for indicator in error_indicators:
            if indicator.lower() in output.lower():
                score -= 5
        
        # 如果有期望输出，计算相似度
        if expected:
            similarity = self._calculate_similarity(output, expected)
            score = score * 0.3 + similarity * 0.7
        
        # 检查事实一致性（简单检查）
        if context and "facts" in context:
            facts = context["facts"]
            matching_facts = sum(1 for fact in facts if fact in output)
            if facts:
                factual_score = (matching_facts / len(facts)) * 100
                score = score * 0.7 + factual_score * 0.3
        
        return max(0.0, min(100.0, score))
    
    def _evaluate_completeness(self, output: str, context: Optional[Dict[str, Any]]) -> float:
        """评估完整性"""
        score = 100.0
        
        # 检查输出长度是否过短
        if len(output) < 50:
            score -= 30
        elif len(output) < 100:
            score -= 15
        
        # 检查是否回答了用户的问题（如果有）
        if context and "user_query" in context:
            query = context["user_query"]
            # 检查是否包含疑问词对应的回答
            question_keywords = {
                "谁": ["是", "的"],
                "什么": ["是", "为"],
                "为什么": ["因为", "由于", "所以"],
                "如何": ["通过", "使用", "需要", "方法"],
                "哪里": ["在", "位于", "位于"],
                "什么时候": ["在", "于", "时"],
                "多少": ["个", "次", "元", "人"],
            }
            
            for keyword, needed in question_keywords.items():
                if keyword in query:
                    if not any(word in output for word in needed):
                        score -= 10
        
        # 检查是否包含未完成的句子
        incomplete_indicators = ["...", "未完", "待续", "to be continued"]
        for indicator in incomplete_indicators:
            if indicator in output:
                score -= 20
        
        return max(0.0, min(100.0, score))
    
    def _evaluate_clarity(self, output: str) -> float:
        """评估清晰度"""
        score = 100.0
        
        # 检查平均句子长度
        sentences = re.split(r'[.!?。！？]+', output)
        if sentences:
            avg_sentence_length = sum(len(s.strip()) for s in sentences) / len(sentences)
            if avg_sentence_length > 100:
                score -= 15  # 句子过长
            elif avg_sentence_length < 5:
                score -= 10  # 句子过短
        
        # 检查是否有乱码或特殊字符
        garbage_count = len(re.findall(r'[�]', output))
        if garbage_count > 0:
            score -= garbage_count * 5
        
        # 检查是否有重复内容
        words = output.split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                score -= 30  # 重复内容过多
        
        # 检查格式是否混乱
        formatting_issues = 0
        if "\n\n\n" in output:
            formatting_issues += 1
        if "  " in output and output.count("  ") > 5:
            formatting_issues += 1
        
        score -= formatting_issues * 10
        
        return max(0.0, min(100.0, score))
    
    def _evaluate_safety(self, output: str) -> float:
        """评估安全性"""
        score = 100.0
        
        # 检查是否包含敏感信息模式
        sensitive_patterns = [
            r"\b\d{15,18}\b",  # 身份证号
            r"\b\d{16,19}\b",  # 银行卡号
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # 邮箱
            r"password\s*[=:]\s*\S+",  # 密码
            r"api[_-]?key\s*[=:]\s*\S+",  # API密钥
        ]
        
        for pattern in sensitive_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                score -= 20
        
        # 检查是否有不当内容
        inappropriate_keywords = ["暴力", "色情", "赌博", "毒品"]
        for keyword in inappropriate_keywords:
            if keyword in output:
                score -= 15
        
        return max(0.0, min(100.0, score))
    
    def _evaluate_format(self, output: str) -> float:
        """评估格式正确性"""
        if not self.config.require_format_check:
            return 100.0
        
        score = 100.0
        
        # 如果期望JSON格式
        if context := getattr(self, '_context', None):
            if context.get("expected_format") == "json":
                try:
                    json.loads(output)
                except json.JSONDecodeError:
                    score -= 50
            
            elif context.get("expected_format") == "markdown":
                # 检查Markdown格式
                if not any(marker in output for marker in ["#", "**", "*", "```", "- "]):
                    score -= 20
        
        # 检查JSON格式
        if output.strip().startswith("{") and output.strip().endswith("}"):
            try:
                json.loads(output)
            except json.JSONDecodeError:
                score -= 30
        
        return max(0.0, min(100.0, score))
    
    def _evaluate_relevance(self, output: str, context: Optional[Dict[str, Any]]) -> float:
        """评估相关性"""
        if not context or "user_query" not in context:
            return 100.0
        
        score = 100.0
        query = context["user_query"].lower()
        output_lower = output.lower()
        
        # 提取查询关键词
        query_words = set(re.findall(r'\w+', query))
        output_words = set(re.findall(r'\w+', output_lower))
        
        # 计算关键词覆盖率
        common_words = query_words & output_words
        if query_words:
            coverage = len(common_words) / len(query_words)
            score = coverage * 100
        
        # 检查是否答非所问
        irrelevant_indicators = [
            "抱歉，我不知道",
            "无法回答",
            "这个问题",
            "与此无关",
        ]
        
        for indicator in irrelevant_indicators:
            if indicator in output:
                score -= 20
        
        return max(0.0, min(100.0, score))
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单实现）"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return (len(intersection) / len(union)) * 100


class QualityControlEngine:
    """
    质量控制引擎 - 主引擎类
    
    整合输入验证和输出质量评估功能。
    
    使用示例:
    ```python
    engine = QualityControlEngine()
    
    # 验证输入
    validation = await engine.validate_input("用户输入")
    
    # 评估输出质量
    quality = await engine.evaluate_output("Agent输出")
    
    # 生成综合报告
    report = await engine.check(input_text, output_text)
    ```
    """
    
    def __init__(
        self,
        input_config: Optional[InputValidationConfig] = None,
        output_config: Optional[OutputQualityConfig] = None
    ):
        # 输入验证器
        self.input_validator = InputValidator(input_config)
        
        # 输出质量评估器
        self.output_evaluator = OutputQualityEvaluator(output_config)
        
        # 质量阈值
        self._min_quality_threshold = output_config.min_quality_threshold if output_config else 60.0
        
        # 统计信息
        self._stats = {
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "warning_checks": 0,
            "avg_quality_score": 0.0,
            "avg_processing_time": 0.0,
        }
        
        logger.info("质量控制引擎初始化完成")
    
    async def validate_input(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationReport:
        """
        验证输入
        
        Args:
            text: 待验证的文本
            context: 上下文信息
            
        Returns:
            验证报告
        """
        logger.debug(f"验证输入，长度: {len(text)}")
        
        report = await self.input_validator.validate(text, context)
        
        self._stats["total_checks"] += 1
        if report.result == ValidationResult.PASS:
            self._stats["passed_checks"] += 1
        elif report.result == ValidationResult.WARNING:
            self._stats["warning_checks"] += 1
        else:
            self._stats["failed_checks"] += 1
        
        return report
    
    async def evaluate_output(
        self,
        output: str,
        expected: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> QualityScore:
        """
        评估输出质量
        
        Args:
            output: 待评估的输出
            expected: 期望输出（可选）
            context: 上下文信息
            
        Returns:
            质量评分
        """
        logger.debug(f"评估输出质量，长度: {len(output)}")
        
        score = await self.output_evaluator.evaluate(output, expected, context)
        
        # 更新统计
        total = self._stats["total_checks"]
        if total > 0:
            current_avg = self._stats["avg_quality_score"]
            self._stats["avg_quality_score"] = (current_avg * (total - 1) + score.overall) / total
        
        return score
    
    async def check(
        self,
        input_text: str,
        output_text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> QualityReport:
        """
        综合质量检查
        
        同时验证输入和评估输出，生成综合报告。
        
        Args:
            input_text: 用户输入
            output_text: Agent输出
            context: 上下文信息
            
        Returns:
            质量报告
        """
        start_time = time.time()
        
        # 验证输入
        validation = await self.validate_input(input_text, context)
        
        # 评估输出
        score = await self.evaluate_output(output_text, context=context)
        
        # 检查是否低于质量阈值
        if score.overall < self._min_quality_threshold:
            validation.warnings.append(
                f"输出质量低于阈值 ({score.overall:.1f} < {self._min_quality_threshold})"
            )
            if validation.result == ValidationResult.PASS:
                validation.result = ValidationResult.WARNING
        
        processing_time = time.time() - start_time
        
        # 更新处理时间统计
        total = self._stats["total_checks"]
        if total > 0:
            current_avg = self._stats["avg_processing_time"]
            self._stats["avg_processing_time"] = (
                (current_avg * (total - 1) + processing_time) / total
            )
        
        return QualityReport(
            score=score,
            validation=validation,
            processing_time=processing_time,
            metadata={
                "input_length": len(input_text),
                "output_length": len(output_text),
            }
        )
    
    async def batch_check(
        self,
        items: List[Tuple[str, str]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[QualityReport]:
        """
        批量质量检查
        
        Args:
            items: [(input, output), ...] 列表
            context: 共享上下文信息
            
        Returns:
            质量报告列表
        """
        logger.info(f"开始批量质量检查，数量: {len(items)}")
        
        reports = []
        for input_text, output_text in items:
            report = await self.check(input_text, output_text, context)
            reports.append(report)
        
        logger.info(f"批量质量检查完成，成功: {sum(1 for r in reports if r.validation.is_valid)}")
        
        return reports
    
    def sanitize_input(self, text: str) -> str:
        """清理输入"""
        return self.input_validator.sanitize(text)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "warning_checks": 0,
            "avg_quality_score": 0.0,
            "avg_processing_time": 0.0,
        }
        logger.info("统计信息已重置")


# 创建默认引擎实例的工厂函数
_default_engine: Optional[QualityControlEngine] = None


def get_default_engine() -> QualityControlEngine:
    """获取默认质量控制引擎"""
    global _default_engine
    if _default_engine is None:
        _default_engine = QualityControlEngine()
    return _default_engine


async def quick_check(input_text: str, output_text: str) -> QualityReport:
    """快速质量检查（使用默认引擎）"""
    engine = get_default_engine()
    return await engine.check(input_text, output_text)
