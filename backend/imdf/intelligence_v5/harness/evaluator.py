"""智影 V5 — Evaluator: 真实评估产出,任一阈值不通过则 sprint 失败"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .generator import FileArtifact, GeneratorOutput, ImplementationSprint

logger = logging.getLogger(__name__)


class CriterionStatus(str, Enum):
    """验收项状态"""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class CriterionType(str, Enum):
    """验收类型"""
    FUNCTIONAL = "functional"   # 功能性
    PERFORMANCE = "performance"  # 性能
    VISUAL = "visual"            # 视觉
    CODE_QUALITY = "code_quality"  # 代码质量
    SECURITY = "security"        # 安全
    USABILITY = "usability"      # 可用性
    DOCUMENTATION = "documentation"  # 文档


@dataclass
class EvaluationCriteria:
    """单个评估项"""
    name: str
    description: str = ""
    criterion_type: CriterionType = CriterionType.FUNCTIONAL
    weight: float = 1.0
    threshold: float = 0.7  # 0-1, 通过阈值
    required: bool = True


@dataclass
class EvaluationResult:
    """评估结果"""
    criterion_name: str
    score: float  # 0-1
    status: CriterionStatus = CriterionStatus.FAIL
    feedback: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.criterion_name,
            "score": round(self.score, 3),
            "status": self.status.value,
            "feedback": self.feedback,
            "evidence": self.evidence,
            "evaluated_at": self.evaluated_at,
        }


class Evaluator:
    """Evaluator — 真实评估产出, 任一必过项 fail 则 sprint 失败

    借鉴 Anthropic Full Harness:
    - 多维评估: 功能/视觉/代码质量
    - 任一 required 阈值不通过 → sprint 失败
    - 详细反馈交回 Generator 重做
    """

    DEFAULT_CRITERIA = [
        EvaluationCriteria(
            name="code_lint",
            description="代码通过 lint 检查",
            criterion_type=CriterionType.CODE_QUALITY,
            threshold=0.8,
            required=True,
        ),
        EvaluationCriteria(
            name="test_coverage",
            description="测试覆盖率",
            criterion_type=CriterionType.CODE_QUALITY,
            threshold=0.7,
            required=True,
        ),
        EvaluationCriteria(
            name="test_pass_rate",
            description="测试通过率",
            criterion_type=CriterionType.FUNCTIONAL,
            threshold=0.9,
            required=True,
        ),
        EvaluationCriteria(
            name="performance",
            description="性能达标 (响应时间 P95 < 500ms)",
            criterion_type=CriterionType.PERFORMANCE,
            threshold=0.7,
            required=True,
        ),
        EvaluationCriteria(
            name="visual_design",
            description="UI 视觉设计达标",
            criterion_type=CriterionType.VISUAL,
            threshold=0.6,
            required=False,  # 非必需
        ),
        EvaluationCriteria(
            name="security",
            description="无 P0/P1 安全问题",
            criterion_type=CriterionType.SECURITY,
            threshold=0.9,
            required=True,
        ),
        EvaluationCriteria(
            name="documentation",
            description="有 README + 使用文档",
            criterion_type=CriterionType.DOCUMENTATION,
            threshold=0.6,
            required=False,
        ),
    ]

    def __init__(self, criteria: Optional[List[EvaluationCriteria]] = None):
        self.criteria = criteria or self.DEFAULT_CRITERIA
        self.history: List[Dict[str, Any]] = []

    def evaluate(
        self,
        sprint: ImplementationSprint,
        artifacts: Optional[List[FileArtifact]] = None,
    ) -> Tuple[bool, List[EvaluationResult]]:
        """评估整个 Sprint"""
        results: List[EvaluationResult] = []
        # 收集所有 artifacts
        all_artifacts: List[FileArtifact] = []
        for out in sprint.step_outputs.values():
            all_artifacts.extend(out.artifacts)
        if artifacts:
            all_artifacts.extend(artifacts)

        for criterion in self.criteria:
            eval_result = self._evaluate_criterion(criterion, sprint, all_artifacts)
            results.append(eval_result)

        # 决定整体通过
        all_passed = all(
            r.status != CriterionStatus.FAIL
            for r, c in zip(results, self.criteria)
            if c.required
        )
        # 记录
        self.history.append({
            "sprint_id": sprint.sprint_id,
            "all_passed": all_passed,
            "results": [r.to_dict() for r in results],
            "ts": time.time(),
        })
        return all_passed, results

    def _evaluate_criterion(
        self,
        criterion: EvaluationCriteria,
        sprint: ImplementationSprint,
        artifacts: List[FileArtifact],
    ) -> EvaluationResult:
        """评估单项"""
        if criterion.name == "code_lint":
            return self._eval_lint(criterion, artifacts)
        if criterion.name == "test_coverage":
            return self._eval_coverage(criterion, artifacts)
        if criterion.name == "test_pass_rate":
            return self._eval_test_pass(criterion, artifacts)
        if criterion.name == "performance":
            return self._eval_performance(criterion, artifacts)
        if criterion.name == "visual_design":
            return self._eval_visual(criterion, artifacts)
        if criterion.name == "security":
            return self._eval_security(criterion, artifacts)
        if criterion.name == "documentation":
            return self._eval_documentation(criterion, artifacts)
        return EvaluationResult(
            criterion_name=criterion.name,
            score=0.5,
            status=CriterionStatus.WARN,
            feedback=f"未知评估项: {criterion.name}",
            evaluated_at=time.time(),
        )

    def _eval_lint(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """代码 lint — 简单启发式: 看是否有明显问题"""
        score = 1.0
        issues: List[str] = []
        for art in artifacts:
            if art.language not in ("python", "typescript", "javascript", "markdown", "toml", "yaml", "json"):
                continue
            # 简单检查
            if art.language == "python":
                # 没有 import 错误 / 缩进一致
                if "\t" in art.content and "    " in art.content:
                    score -= 0.1
                    issues.append(f"{art.path}: 混用 tab/space")
                # 没有未闭合的括号
                if art.content.count("(") != art.content.count(")"):
                    score -= 0.2
                    issues.append(f"{art.path}: 括号不匹配")
                if art.content.count("[") != art.content.count("]"):
                    score -= 0.1
                    issues.append(f"{art.path}: 中括号不匹配")
        score = max(score, 0.0)
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"发现 {len(issues)} 个问题" if issues else "代码格式良好",
            evidence={"issues": issues[:10]},
            evaluated_at=time.time(),
        )

    def _eval_coverage(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """测试覆盖率 — 启发式: 测试文件 / 实现文件"""
        impl_files = [a for a in artifacts if a.language == "python" and "main" in a.path or "src/" in a.path]
        test_files = [a for a in artifacts if a.language == "python" and "test" in a.path.lower()]
        if not impl_files:
            return EvaluationResult(
                criterion_name=criterion.name,
                score=0.0,
                status=CriterionStatus.FAIL,
                feedback="无实现文件",
                evaluated_at=time.time(),
            )
        ratio = len(test_files) / len(impl_files)
        # ratio 1.0 = 100% 覆盖 (理想), 0 = 0%
        score = min(ratio, 1.0)
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"测试文件 {len(test_files)} / 实现 {len(impl_files)} = {ratio:.0%}",
            evidence={"test_files": [t.path for t in test_files], "impl_files": [i.path for i in impl_files]},
            evaluated_at=time.time(),
        )

    def _eval_test_pass(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """测试通过率 — 启发式: 测试文件存在 + 含 assert"""
        test_files = [a for a in artifacts if a.language == "python" and "test" in a.path.lower()]
        if not test_files:
            return EvaluationResult(
                criterion_name=criterion.name,
                score=0.0,
                status=CriterionStatus.FAIL,
                feedback="无测试文件",
                evaluated_at=time.time(),
            )
        # 启发式:有 assert 算通过
        all_have_assert = all("assert" in t.content or "pytest.raises" in t.content or "expect" in t.content for t in test_files)
        score = 1.0 if all_have_assert else 0.7
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"测试 {len(test_files)} 个, 含 assert: {all_have_assert}",
            evaluated_at=time.time(),
        )

    def _eval_performance(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """性能 — 启发式: 文件大小 + 函数复杂度"""
        total_size = sum(a.size_bytes for a in artifacts)
        # 总文件大小 < 1MB 算合格
        score = max(0, 1.0 - (total_size / 1_000_000))
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"总大小 {total_size} bytes",
            evidence={"total_bytes": total_size},
            evaluated_at=time.time(),
        )

    def _eval_visual(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """视觉 — 启发式: 是否有 vue/css/html 文件 + 含样式"""
        ui_files = [a for a in artifacts if a.language in ("vue", "html", "css", "scss")]
        if not ui_files:
            return EvaluationResult(
                criterion_name=criterion.name,
                score=0.5,  # 没 UI 算中等
                status=CriterionStatus.SKIP,
                feedback="无 UI 文件",
                evaluated_at=time.time(),
            )
        # 有 UI 算合格
        has_styling = any("style" in u.content or "class=" in u.content or "css" in u.content.lower() for u in ui_files)
        score = 0.85 if has_styling else 0.65
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"UI 文件 {len(ui_files)}, 含样式: {has_styling}",
            evaluated_at=time.time(),
        )

    def _eval_security(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """安全 — 检查明文密码/密钥/eval/exec"""
        score = 1.0
        issues: List[str] = []
        for art in artifacts:
            if art.language != "python":
                continue
            # 检查危险模式
            if re.search(r"eval\s*\(", art.content):
                score -= 0.3
                issues.append(f"{art.path}: 使用 eval()")
            if re.search(r"exec\s*\(", art.content):
                score -= 0.3
                issues.append(f"{art.path}: 使用 exec()")
            if re.search(r"password\s*=\s*['\"]", art.content, re.IGNORECASE):
                score -= 0.2
                issues.append(f"{art.path}: 硬编码密码")
            if re.search(r"api[_-]?key\s*=\s*['\"]", art.content, re.IGNORECASE):
                score -= 0.2
                issues.append(f"{art.path}: 硬编码 API key")
            if "shell=True" in art.content:
                score -= 0.2
                issues.append(f"{art.path}: shell=True 注入风险")
        score = max(score, 0.0)
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"发现 {len(issues)} 个安全问题" if issues else "无安全问题",
            evidence={"issues": issues[:10]},
            evaluated_at=time.time(),
        )

    def _eval_documentation(self, criterion: EvaluationCriteria, artifacts: List[FileArtifact]) -> EvaluationResult:
        """文档 — README + 注释密度"""
        readme = next((a for a in artifacts if a.path.upper() == "README.MD"), None)
        if not readme:
            return EvaluationResult(
                criterion_name=criterion.name,
                score=0.0,
                status=CriterionStatus.FAIL,
                feedback="无 README",
                evaluated_at=time.time(),
            )
        # 启发式: README 长度 + 代码中 docstring 比例
        code_files = [a for a in artifacts if a.language == "python"]
        total_lines = sum(a.lines for a in code_files) or 1
        docstring_lines = sum(
            a.content.count('"""') // 2 * 3 for a in code_files
        )  # 粗略估算
        doc_ratio = min(docstring_lines / total_lines, 1.0)
        readme_score = min(len(readme.content) / 2000, 1.0)  # 2KB 满分
        score = (readme_score * 0.6 + doc_ratio * 0.4)
        return EvaluationResult(
            criterion_name=criterion.name,
            score=score,
            status=self._judge(score, criterion.threshold, criterion.required),
            feedback=f"README {len(readme.content)} bytes, doc 比例 {doc_ratio:.1%}",
            evaluated_at=time.time(),
        )

    def _judge(self, score: float, threshold: float, required: bool) -> CriterionStatus:
        """判定状态"""
        if score >= threshold:
            return CriterionStatus.PASS
        if required:
            return CriterionStatus.FAIL
        return CriterionStatus.WARN

    def get_summary(self, results: List[EvaluationResult]) -> Dict[str, Any]:
        """汇总"""
        passed = sum(1 for r in results if r.status == CriterionStatus.PASS)
        failed = sum(1 for r in results if r.status == CriterionStatus.FAIL)
        warned = sum(1 for r in results if r.status == CriterionStatus.WARN)
        skipped = sum(1 for r in results if r.status == CriterionStatus.SKIP)
        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "pass_rate": round(passed / max(len(results), 1), 3),
        }
