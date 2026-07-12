"""智影 V5 — 16 部门 (The Agency 模式)"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class Department(str, Enum):
    """16 部门"""
    ENGINEERING = "engineering"            # 研发部
    DESIGN = "design"                       # 设计部
    PRODUCT = "product"                     # 产品部
    MARKETING = "marketing"                 # 市场部
    OPERATIONS = "operations"               # 运营部
    QA = "qa"                               # 测试部
    DATA = "data"                           # 数据部
    SECURITY = "security"                   # 安全部
    INFRASTRUCTURE = "infrastructure"      # 基础设施
    SALES = "sales"                         # 销售部
    CUSTOMER_SUCCESS = "customer_success"   # 客户成功
    LEGAL = "legal"                         # 法务部
    FINANCE = "finance"                     # 财务部
    HR = "hr"                              # 人力资源
    CONTENT = "content"                     # 内容部
    RESEARCH = "research"                   # 研究院


# 部门元数据
DEPARTMENTS: Dict[Department, Dict[str, Any]] = {
    Department.ENGINEERING: {
        "name_cn": "研发部",
        "description": "前端/后端/移动端/小程序/架构/算法",
        "role_count": 35,
        "color": "#1f6feb",
        "icon": "code",
    },
    Department.DESIGN: {
        "name_cn": "设计部",
        "description": "UI/品牌/视觉/交互/动效/插画",
        "role_count": 18,
        "color": "#bf3989",
        "icon": "palette",
    },
    Department.PRODUCT: {
        "name_cn": "产品部",
        "description": "产品经理/需求排期/数据分析/用户研究",
        "role_count": 14,
        "color": "#fb8500",
        "icon": "package",
    },
    Department.MARKETING: {
        "name_cn": "市场部",
        "description": "内容/品牌/SEO/广告/小红书/抖音",
        "role_count": 22,
        "color": "#06d6a0",
        "icon": "megaphone",
    },
    Department.OPERATIONS: {
        "name_cn": "运营部",
        "description": "用户运营/内容运营/活动/社群",
        "role_count": 16,
        "color": "#8338ec",
        "icon": "users",
    },
    Department.QA: {
        "name_cn": "测试部",
        "description": "功能测试/性能测试/接口测试/上线验收",
        "role_count": 12,
        "color": "#ef476f",
        "icon": "check-circle",
    },
    Department.DATA: {
        "name_cn": "数据部",
        "description": "数据分析师/数据工程师/数据科学家/BI",
        "role_count": 14,
        "color": "#118ab2",
        "icon": "bar-chart",
    },
    Department.SECURITY: {
        "name_cn": "安全部",
        "description": "安全审计/渗透测试/合规/隐私",
        "role_count": 10,
        "color": "#073b4c",
        "icon": "shield",
    },
    Department.INFRASTRUCTURE: {
        "name_cn": "基础设施部",
        "description": "DevOps/SRE/云架构/容器/网络",
        "role_count": 12,
        "color": "#06a77d",
        "icon": "server",
    },
    Department.SALES: {
        "name_cn": "销售部",
        "description": "客户经理/销售支持/合同",
        "role_count": 10,
        "color": "#dda15e",
        "icon": "briefcase",
    },
    Department.CUSTOMER_SUCCESS: {
        "name_cn": "客户成功部",
        "description": "客户成功经理/技术支持/培训",
        "role_count": 8,
        "color": "#9d4edd",
        "icon": "smile",
    },
    Department.LEGAL: {
        "name_cn": "法务部",
        "description": "合同/合规/知识产权",
        "role_count": 6,
        "color": "#5a189a",
        "icon": "scale",
    },
    Department.FINANCE: {
        "name_cn": "财务部",
        "description": "会计/预算/审计",
        "role_count": 8,
        "color": "#264653",
        "icon": "dollar-sign",
    },
    Department.HR: {
        "name_cn": "人力资源部",
        "description": "招聘/培训/绩效",
        "role_count": 8,
        "color": "#2a9d8f",
        "icon": "user-plus",
    },
    Department.CONTENT: {
        "name_cn": "内容部",
        "description": "编辑/记者/作家/翻译",
        "role_count": 12,
        "color": "#e76f51",
        "icon": "edit",
    },
    Department.RESEARCH: {
        "name_cn": "研究院",
        "description": "学术研究/产品研究/前沿",
        "role_count": 10,
        "color": "#003049",
        "icon": "book",
    },
}


def get_department(dept: Department) -> Dict[str, Any]:
    return DEPARTMENTS.get(dept, {})


def get_all_departments() -> List[Department]:
    return list(DEPARTMENTS.keys())
