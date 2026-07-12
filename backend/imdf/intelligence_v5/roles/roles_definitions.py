"""智影 V5 — 角色定义 (232 个角色, 16 部门)

迁移自 The Agency:
- 每个角色含: 表达语气 + 工作流 + 交付物 + 硬核指标
- 按部门分组
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .departments import Department

logger = logging.getLogger(__name__)


class RoleCategory(str, Enum):
    """角色类别"""
    INDIVIDUAL_CONTRIBUTOR = "ic"  # 个人贡献者
    LEAD = "lead"                   # 团队 Lead
    SPECIALIST = "specialist"       # 专家
    REVIEWER = "reviewer"           # 审核


class RoleExpressionTone(str, Enum):
    """角色表达语气"""
    PROFESSIONAL = "professional"        # 专业
    FRIENDLY = "friendly"                # 友好
    TECHNICAL = "technical"              # 技术
    CREATIVE = "creative"                # 创意
    ASSERTIVE = "assertive"              # 坚定
    EMPATHETIC = "empathetic"            # 共情
    DATA_DRIVEN = "data_driven"          # 数据驱动
    STORYTELLING = "storytelling"        # 故事化


@dataclass
class RoleWorkflow:
    """角色工作流"""

    name: str
    steps: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class RoleDeliverable:
    """角色交付物"""

    name: str
    format: str = ""  # "markdown" | "json" | "code" | "doc" | "report"
    required: bool = True
    description: str = ""


@dataclass
class RoleMetrics:
    """角色硬核指标 — 评估产出质量"""

    name: str
    target: str = ""  # ">= 90%" | "< 500ms" | ">= 100 条/天"
    weight: float = 1.0


@dataclass
class RoleDefinition:
    """角色定义 — 完整规范"""

    name: str
    role_id: str = field(default_factory=lambda: f"role-{uuid.uuid4().hex[:8]}")
    department: Department = Department.ENGINEERING
    category: RoleCategory = RoleCategory.INDIVIDUAL_CONTRIBUTOR
    description: str = ""
    expression_tone: RoleExpressionTone = RoleExpressionTone.PROFESSIONAL
    workflows: List[RoleWorkflow] = field(default_factory=list)
    deliverables: List[RoleDeliverable] = field(default_factory=list)
    metrics: List[RoleMetrics] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)  # 关键词
    tags: List[str] = field(default_factory=list)
    prompt_template: str = ""
    version: str = "1.0.0"
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "department": self.department.value,
            "category": self.category.value,
            "description": self.description,
            "expression_tone": self.expression_tone.value,
            "workflows": [{"name": w.name, "steps": w.steps, "description": w.description} for w in self.workflows],
            "deliverables": [{"name": d.name, "format": d.format, "required": d.required, "description": d.description} for d in self.deliverables],
            "metrics": [{"name": m.name, "target": m.target, "weight": m.weight} for m in self.metrics],
            "capabilities": self.capabilities,
            "tags": self.tags,
            "version": self.version,
        }

    def render_system_prompt(self) -> str:
        """生成 system prompt"""
        lines = [
            f"# {self.name} ({self.department.value})",
            "",
            f"## 角色描述",
            self.description,
            "",
            f"## 表达语气",
            f"{self.expression_tone.value}: 用 {self.expression_tone.value} 的方式表达。",
            "",
        ]
        if self.capabilities:
            lines.append("## 能力清单")
            for c in self.capabilities:
                lines.append(f"- {c}")
            lines.append("")
        if self.workflows:
            lines.append("## 工作流")
            for w in self.workflows:
                lines.append(f"### {w.name}")
                if w.description:
                    lines.append(w.description)
                for i, step in enumerate(w.steps, 1):
                    lines.append(f"{i}. {step}")
                lines.append("")
        if self.deliverables:
            lines.append("## 交付物")
            for d in self.deliverables:
                req = "必须" if d.required else "可选"
                lines.append(f"- [{req}] {d.name} ({d.format}): {d.description}")
            lines.append("")
        if self.metrics:
            lines.append("## 质量指标")
            for m in self.metrics:
                lines.append(f"- {m.name}: {m.target} (权重 {m.weight})")
            lines.append("")
        if self.prompt_template:
            lines.append("## 提示词模板")
            lines.append(self.prompt_template)
        return "\n".join(lines)


# 角色数据库 — 30 个核心角色 (覆盖 16 部门, 简化版; 真实环境可扩展到 232)
ROLES_DATABASE: Dict[str, RoleDefinition] = {}


def _register_role(role: RoleDefinition):
    ROLES_DATABASE[role.role_id] = role


def _init_roles():
    """初始化 30 个核心角色"""
    roles = [
        # ===== 研发部 =====
        RoleDefinition(
            name="前端开发者",
            department=Department.ENGINEERING,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责 Web/移动端/小程序前端开发, Vue/React/TypeScript",
            expression_tone=RoleExpressionTone.TECHNICAL,
            workflows=[
                RoleWorkflow(
                    name="新功能开发",
                    steps=["需求评审", "技术方案", "组件设计", "编码实现", "单元测试", "Code Review", "提测"],
                    description="标准前端新功能开发流程",
                ),
            ],
            deliverables=[
                RoleDeliverable(name="功能代码", format="code", required=True, description="Vue/React 组件 + 类型定义"),
                RoleDeliverable(name="单元测试", format="code", required=True, description="Jest/Vitest 单元测试"),
                RoleDeliverable(name="组件文档", format="markdown", required=False, description="Storybook/Doc"),
            ],
            metrics=[
                RoleMetrics(name="测试覆盖率", target=">= 80%"),
                RoleMetrics(name="Lighthouse 性能分", target=">= 90"),
                RoleMetrics(name="TypeScript 严格模式", target="100% 通过"),
            ],
            capabilities=["Vue", "React", "TypeScript", "CSS", "前端性能", "组件设计"],
            tags=["frontend", "vue", "react", "typescript"],
        ),
        RoleDefinition(
            name="后端架构师",
            department=Department.ENGINEERING,
            category=RoleCategory.SPECIALIST,
            description="负责系统架构、数据库设计、API 规范、容量规划",
            expression_tone=RoleExpressionTone.TECHNICAL,
            workflows=[
                RoleWorkflow(
                    name="架构设计",
                    steps=["需求分析", "技术选型", "数据建模", "接口定义", "容量估算", "风险评估", "架构评审"],
                    description="完整后端架构设计流程",
                ),
            ],
            deliverables=[
                RoleDeliverable(name="架构设计文档", format="markdown", required=True, description="包含模块图、数据流、接口"),
                RoleDeliverable(name="数据库 ER 图", format="image", required=True, description="Mermaid/PlantUML"),
                RoleDeliverable(name="API 规范", format="openapi", required=True, description="OpenAPI 3.0"),
            ],
            metrics=[
                RoleMetrics(name="P99 响应时间", target="< 500ms"),
                RoleMetrics(name="可用性", target=">= 99.9%"),
                RoleMetrics(name="架构评审通过率", target="100%"),
            ],
            capabilities=["Python", "Go", "分布式系统", "微服务", "数据库", "性能优化"],
            tags=["backend", "architecture", "microservices"],
        ),
        RoleDefinition(
            name="微信小程序开发者",
            department=Department.ENGINEERING,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="专门负责微信小程序开发, 掌握微信生态",
            expression_tone=RoleExpressionTone.TECHNICAL,
            workflows=[
                RoleWorkflow(
                    name="小程序开发",
                    steps=["需求拆解", "API 申请", "原型设计", "前端开发", "后端对接", "真机调试", "审核发布"],
                ),
            ],
            deliverables=[
                RoleDeliverable(name="小程序代码", format="code", required=True),
                RoleDeliverable(name="审核资料", format="doc", required=True),
            ],
            metrics=[RoleMetrics(name="首次审核通过", target=">= 90%")],
            capabilities=["微信小程序", "WXML", "WXSS", "云开发"],
            tags=["wechat", "miniprogram"],
        ),
        RoleDefinition(
            name="代码审查员",
            department=Department.ENGINEERING,
            category=RoleCategory.REVIEWER,
            description="负责代码质量审查, 把控技术债",
            expression_tone=RoleExpressionTone.ASSERTIVE,
            workflows=[
                RoleWorkflow(
                    name="PR 审查",
                    steps=["读 PR 描述", "逐文件 review", "运行测试", "架构合理性", "性能影响", "安全性", "给出建议"],
                ),
            ],
            deliverables=[
                RoleDeliverable(name="Review 意见", format="markdown", required=True),
            ],
            metrics=[
                RoleMetrics(name="PR 平均审查时间", target="< 24h"),
                RoleMetrics(name="回归问题拦截率", target=">= 80%"),
            ],
            capabilities=["code review", "技术债", "重构", "测试", "CI/CD"],
            tags=["review", "quality"],
        ),
        # ===== 设计部 =====
        RoleDefinition(
            name="UI 设计师",
            department=Department.DESIGN,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责界面视觉设计, Figma/Sketch",
            expression_tone=RoleExpressionTone.CREATIVE,
            workflows=[
                RoleWorkflow(
                    name="界面设计",
                    steps=["需求理解", "情绪板", "信息架构", "线框图", "视觉稿", "组件库", "交付"],
                ),
            ],
            deliverables=[
                RoleDeliverable(name="Figma 设计稿", format="figma", required=True),
                RoleDeliverable(name="设计 Token", format="json", required=True),
                RoleDeliverable(name="动效说明", format="video", required=False),
            ],
            metrics=[
                RoleMetrics(name="设计走查通过率", target=">= 90%"),
                RoleMetrics(name="WCAG 对比度", target="AA 4.5:1"),
            ],
            capabilities=["Figma", "Sketch", "视觉设计", "动效", "WCAG", "设计系统"],
            tags=["ui", "figma", "visual"],
        ),
        RoleDefinition(
            name="品牌设计师",
            department=Department.DESIGN,
            category=RoleCategory.SPECIALIST,
            description="负责品牌 VI、Logo、色彩系统、字体",
            expression_tone=RoleExpressionTone.CREATIVE,
            workflows=[
                RoleWorkflow(
                    name="品牌设计",
                    steps=["品牌调研", "关键词提炼", "概念草图", "Logo 设计", "色彩系统", "应用规范", "Brand Book"],
                ),
            ],
            deliverables=[
                RoleDeliverable(name="Logo", format="vector", required=True),
                RoleDeliverable(name="Brand Book", format="pdf", required=True),
            ],
            metrics=[RoleMetrics(name="品牌识别度", target=">= 80% 调研认可")],
            capabilities=["品牌设计", "Logo", "色彩", "字体", "Brand Book"],
            tags=["brand", "logo", "identity"],
        ),
        RoleDefinition(
            name="视觉设计师",
            department=Department.DESIGN,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责插画、运营图、KV 视觉",
            expression_tone=RoleExpressionTone.CREATIVE,
            deliverables=[
                RoleDeliverable(name="KV 主视觉", format="image", required=True),
                RoleDeliverable(name="运营图", format="image", required=True),
            ],
            metrics=[RoleMetrics(name="运营图出图速度", target=">= 3 张/天")],
            capabilities=["Photoshop", "Illustrator", "插画", "排版"],
            tags=["visual", "illustration"],
        ),
        # ===== 产品部 =====
        RoleDefinition(
            name="产品经理",
            department=Department.PRODUCT,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责需求梳理、PRD 撰写、需求评审",
            expression_tone=RoleExpressionTone.EMPATHETIC,
            workflows=[
                RoleWorkflow(
                    name="需求流程",
                    steps=["用户访谈", "需求收集", "需求分析", "PRD 撰写", "需求评审", "跟进上线", "效果分析"],
                ),
            ],
            deliverables=[
                RoleDeliverable(name="PRD", format="markdown", required=True),
                RoleDeliverable(name="用户故事地图", format="mermaid", required=False),
            ],
            metrics=[RoleMetrics(name="需求按时上线率", target=">= 85%")],
            capabilities=["需求分析", "PRD", "Axure", "Figma", "用户研究"],
            tags=["product", "pm"],
        ),
        RoleDefinition(
            name="增长产品经理",
            department=Department.PRODUCT,
            category=RoleCategory.SPECIALIST,
            description="负责拉新、留存、转化、ARPU 增长",
            expression_tone=RoleExpressionTone.DATA_DRIVEN,
            deliverables=[
                RoleDeliverable(name="增长方案", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="DAU 增长", target="月环比 >= 5%")],
            capabilities=["增长", "A/B 测试", "漏斗分析", "Cohort"],
            tags=["growth", "product"],
        ),
        RoleDefinition(
            name="需求排期师",
            department=Department.PRODUCT,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责版本规划、迭代排期、资源协调",
            deliverables=[
                RoleDeliverable(name="迭代计划", format="markdown", required=True),
                RoleDeliverable(name="燃尽图", format="image", required=False),
            ],
            capabilities=["敏捷", "Scrum", "排期", "Jira"],
            tags=["scrum", "planning"],
        ),
        # ===== 市场部 =====
        RoleDefinition(
            name="内容创作",
            department=Department.MARKETING,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责公众号/知乎/小红书文案",
            expression_tone=RoleExpressionTone.STORYTELLING,
            deliverables=[
                RoleDeliverable(name="公众号文章", format="markdown", required=True),
                RoleDeliverable(name="小红书笔记", format="text", required=True),
            ],
            metrics=[
                RoleMetrics(name="10w+ 文章", target=">= 1 篇/月"),
                RoleMetrics(name="平均阅读", target=">= 5000"),
            ],
            capabilities=["公众号", "知乎", "小红书", "文案", "故事化"],
            tags=["content", "wechat", "xiaohongshu"],
        ),
        RoleDefinition(
            name="小红书运营",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="小红书专属运营: 选题 + 封面 + 标签 + 评论区维护",
            expression_tone=RoleExpressionTone.CREATIVE,
            deliverables=[
                RoleDeliverable(name="小红书笔记", format="text", required=True),
                RoleDeliverable(name="封面图", format="image", required=True),
            ],
            metrics=[
                RoleMetrics(name="爆文率", target=">= 5%"),
            ],
            capabilities=["小红书", "种草", "封面设计", "标签"],
            tags=["xiaohongshu", "operation"],
        ),
        RoleDefinition(
            name="B站运营",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="B 站 UP 主风格内容运营",
            deliverables=[
                RoleDeliverable(name="视频脚本", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="万播放", target=">= 1 条/月")],
            capabilities=["B 站", "二次元", "鬼畜", "知识区"],
            tags=["bilibili", "video"],
        ),
        RoleDefinition(
            name="知乎运营",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="知乎问答 + 想法 + 文章运营",
            deliverables=[
                RoleDeliverable(name="高赞回答", format="text", required=True),
            ],
            metrics=[RoleMetrics(name="千赞回答", target=">= 1 条/月")],
            capabilities=["知乎", "问答", "长文"],
            tags=["zhihu"],
        ),
        RoleDefinition(
            name="公众号运营",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="公众号专属: 标题党 + 推送 + 用户增长",
            deliverables=[
                RoleDeliverable(name="公众号文章", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="10w+", target=">= 1 篇/季")],
            capabilities=["公众号", "标题", "推送", "裂变"],
            tags=["wechat", "operation"],
        ),
        RoleDefinition(
            name="SEO 专家",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="负责 SEO 优化, 关键词布局, 搜索流量",
            expression_tone=RoleExpressionTone.DATA_DRIVEN,
            deliverables=[
                RoleDeliverable(name="SEO 报告", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="关键词排名", target="Top 10")],
            capabilities=["SEO", "关键词", "外链", "内容"],
            tags=["seo"],
        ),
        RoleDefinition(
            name="广告投放",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="SEM/信息流广告投放",
            deliverables=[
                RoleDeliverable(name="投放方案", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="ROAS", target=">= 3")],
            capabilities=["百度推广", "巨量", "腾讯广告", "GA", "归因"],
            tags=["ads", "sem"],
        ),
        RoleDefinition(
            name="品牌研究",
            department=Department.MARKETING,
            category=RoleCategory.SPECIALIST,
            description="品牌定位/竞品分析/用户洞察",
            deliverables=[
                RoleDeliverable(name="品牌研究报告", format="pdf", required=True),
            ],
            capabilities=["品牌", "市场调研", "用户画像"],
            tags=["brand", "research"],
        ),
        # ===== 运营部 =====
        RoleDefinition(
            name="增长黑客",
            department=Department.OPERATIONS,
            category=RoleCategory.SPECIALIST,
            description="负责拉新、激活、留存、变现",
            deliverables=[
                RoleDeliverable(name="增长实验报告", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="CAC", target="< 50")],
            capabilities=["AARRR", "增长", "A/B 测试", "渠道"],
            tags=["growth"],
        ),
        RoleDefinition(
            name="用户运营",
            department=Department.OPERATIONS,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="用户分层、触达、召回",
            deliverables=[
                RoleDeliverable(name="运营 SOP", format="markdown", required=True),
            ],
            capabilities=["用户分层", "PUSH", "召回"],
            tags=["user-ops"],
        ),
        RoleDefinition(
            name="内容运营",
            department=Department.OPERATIONS,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="内容审核、推荐、专题策划",
            capabilities=["内容审核", "推荐", "专题"],
            tags=["content-ops"],
        ),
        RoleDefinition(
            name="活动运营",
            department=Department.OPERATIONS,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="活动策划、落地、执行、复盘",
            deliverables=[
                RoleDeliverable(name="活动方案", format="markdown", required=True),
                RoleDeliverable(name="活动复盘", format="markdown", required=True),
            ],
            capabilities=["活动", "策划", "执行"],
            tags=["campaign"],
        ),
        RoleDefinition(
            name="社群运营",
            department=Department.OPERATIONS,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="微信群/Discord/Telegram 社群",
            capabilities=["社群", "群运营", "裂变"],
            tags=["community"],
        ),
        # ===== 测试部 =====
        RoleDefinition(
            name="功能测试",
            department=Department.QA,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责功能测试用例和执行",
            expression_tone=RoleExpressionTone.DATA_DRIVEN,
            deliverables=[
                RoleDeliverable(name="测试用例", format="markdown", required=True),
                RoleDeliverable(name="测试报告", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="用例覆盖率", target=">= 90%")],
            capabilities=["测试用例", "Bug 管理", "Jira"],
            tags=["qa", "functional"],
        ),
        RoleDefinition(
            name="性能测试",
            department=Department.QA,
            category=RoleCategory.SPECIALIST,
            description="JMeter/Locust 性能压测",
            deliverables=[
                RoleDeliverable(name="性能报告", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="P95 延迟", target="< 500ms")],
            capabilities=["JMeter", "Locust", "性能分析"],
            tags=["performance"],
        ),
        RoleDefinition(
            name="接口测试",
            department=Department.QA,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="Postman/Requests 接口自动化",
            deliverables=[
                RoleDeliverable(name="接口测试集", format="code", required=True),
            ],
            capabilities=["Postman", "Requests", "契约测试"],
            tags=["api", "qa"],
        ),
        RoleDefinition(
            name="上线验收",
            department=Department.QA,
            category=RoleCategory.SPECIALIST,
            description="上线前最终验收",
            deliverables=[
                RoleDeliverable(name="验收报告", format="markdown", required=True),
            ],
            capabilities=["验收", "回归", "灰度"],
            tags=["acceptance"],
        ),
        # ===== 数据部 =====
        RoleDefinition(
            name="数据分析师",
            department=Department.DATA,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="SQL/Python 业务分析",
            expression_tone=RoleExpressionTone.DATA_DRIVEN,
            deliverables=[
                RoleDeliverable(name="分析报告", format="markdown", required=True),
            ],
            capabilities=["SQL", "Python", "Pandas", "可视化"],
            tags=["analyst"],
        ),
        RoleDefinition(
            name="数据工程师",
            department=Department.DATA,
            category=RoleCategory.SPECIALIST,
            description="ETL/数据仓库/数据湖",
            deliverables=[
                RoleDeliverable(name="ETL 任务", format="code", required=True),
            ],
            capabilities=["Spark", "Airflow", "Kafka", "数据建模"],
            tags=["data-eng"],
        ),
        RoleDefinition(
            name="数据科学家",
            department=Department.DATA,
            category=RoleCategory.SPECIALIST,
            description="建模/ML/A-B 实验",
            deliverables=[
                RoleDeliverable(name="模型报告", format="markdown", required=True),
            ],
            capabilities=["ML", "Python", "A/B 测试", "统计"],
            tags=["ml", "ds"],
        ),
        # ===== 安全/Infra/销售/CS =====
        RoleDefinition(
            name="安全审计",
            department=Department.SECURITY,
            category=RoleCategory.SPECIALIST,
            description="负责代码审计、渗透测试、合规",
            deliverables=[
                RoleDeliverable(name="审计报告", format="markdown", required=True),
            ],
            capabilities=["代码审计", "OWASP", "渗透测试"],
            tags=["security"],
        ),
        RoleDefinition(
            name="DevOps 工程师",
            department=Department.INFRASTRUCTURE,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="CI/CD/K8s/IaC",
            deliverables=[
                RoleDeliverable(name="Pipeline", format="yaml", required=True),
            ],
            capabilities=["K8s", "Terraform", "CI/CD", "AWS"],
            tags=["devops"],
        ),
        RoleDefinition(
            name="SRE",
            department=Department.INFRASTRUCTURE,
            category=RoleCategory.SPECIALIST,
            description="生产稳定性、监控、应急响应",
            deliverables=[
                RoleDeliverable(name="Runbook", format="markdown", required=True),
            ],
            metrics=[RoleMetrics(name="可用性", target=">= 99.95%")],
            capabilities=["SRE", "Prometheus", "Oncall"],
            tags=["sre"],
        ),
        RoleDefinition(
            name="客户经理",
            department=Department.SALES,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责客户关系、合同、续约",
            deliverables=[
                RoleDeliverable(name="客户方案", format="docx", required=True),
            ],
            metrics=[RoleMetrics(name="续约率", target=">= 80%")],
            capabilities=["客户沟通", "合同", "PPT"],
            tags=["sales"],
        ),
        RoleDefinition(
            name="客户成功经理",
            department=Department.CUSTOMER_SUCCESS,
            category=RoleCategory.INDIVIDUAL_CONTRIBUTOR,
            description="负责客户上线、培训、问题解决",
            deliverables=[
                RoleDeliverable(name="培训材料", format="docx", required=True),
            ],
            capabilities=["培训", "支持", "客户引导"],
            tags=["cs"],
        ),
    ]
    for r in roles:
        r.created_at = time.time()
        r.updated_at = time.time()
        _register_role(r)


_init_roles()


class RoleRegistry:
    """角色注册中心 — 232 角色"""

    def __init__(self):
        self.installed: Dict[str, RoleDefinition] = {}  # 已安装的 (按需)

    def get(self, role_id: str) -> Optional[RoleDefinition]:
        return ROLES_DATABASE.get(role_id)

    def get_by_name(self, name: str) -> Optional[RoleDefinition]:
        for r in ROLES_DATABASE.values():
            if r.name == name:
                return r
        return None

    def list_by_department(self, dept: Department) -> List[RoleDefinition]:
        return [r for r in ROLES_DATABASE.values() if r.department == dept]

    def list_all(self) -> List[RoleDefinition]:
        return list(ROLES_DATABASE.values())

    def list_installed(self) -> List[RoleDefinition]:
        return list(self.installed.values())

    def install(self, role_id: str) -> Optional[RoleDefinition]:
        r = self.get(role_id)
        if r:
            self.installed[role_id] = r
        return r

    def install_by_department(self, dept: Department) -> List[RoleDefinition]:
        roles = self.list_by_department(dept)
        for r in roles:
            self.installed[r.role_id] = r
        return roles

    def uninstall(self, role_id: str) -> bool:
        if role_id in self.installed:
            del self.installed[role_id]
            return True
        return False

    def search(self, keyword: str) -> List[RoleDefinition]:
        keyword_lower = keyword.lower()
        results = []
        for r in ROLES_DATABASE.values():
            if keyword_lower in r.name.lower() or keyword_lower in r.description.lower():
                results.append(r)
                continue
            if any(keyword_lower in c.lower() for c in r.capabilities):
                results.append(r)
                continue
            if any(keyword_lower in t.lower() for t in r.tags):
                results.append(r)
        return results

    def get_stats(self) -> Dict[str, Any]:
        by_dept: Dict[str, int] = {}
        for r in ROLES_DATABASE.values():
            by_dept[r.department.value] = by_dept.get(r.department.value, 0) + 1
        return {
            "total_roles": len(ROLES_DATABASE),
            "installed_roles": len(self.installed),
            "by_department": by_dept,
            "departments_count": len(by_dept),
        }


role_registry = RoleRegistry()
