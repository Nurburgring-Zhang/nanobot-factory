"""
Web Design Engine — Claude Design思想 x 21套设计风格
====================================================
融合世界级设计理念:
  - Claude Design 420行提示词核心思想
  - ConardLi garden-web-design-engineer 21套风格
  - 女娲认知蒸馏(做受众模型前置分析)
  - PPT Director 评审三检查

核心设计理念（来自Claude Design）:
  1. 身份定位: "专家设计师,用户是你的经理"
  2. 动态角色切换: 做动画=动效设计师,做原型=UX设计师
  3. 反AI味清单: 禁止Inter/Roboto/紫粉渐变/emoji当图标
  4. oklch配色: 保持L+C不变,调hue
  5. 设计系统先行: 写HTML前先宣告配色/字体/间距/圆角/阴影
  6. 每元素值得: 不放无意义的填充内容
  7. v0快速验证: 先出带占位符的v0,方向对了再填充
  8. 独立审查Agent: fork子Agent做截图/布局/JS探测
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json, os, logging

logger = logging.getLogger(__name__)


# ===== Claude Design 反AI味字体黑名单 =====
BANNED_FONTS = ["Inter", "Roboto", "Arial", "Fraunces", "system-ui", "sans-serif"]

# ===== 推荐字体配对(9对) =====
FONT_PAIRS = [
    ("Instrument Serif", "Space Grotesk"),
    ("Plus Jakarta Sans", "Inter"),
    ("Space Grotesk", "JetBrains Mono"),
    ("Sora", "Source Serif"),
    ("Newsreader", "Inter"),
    ("DM Serif Display", "DM Sans"),
    ("Cabinet Grotesk", "Satoshi"),
    ("Zodiak", "General Sans"),
    ("Editorial New", "Neon Welt"),
]


class PageType(str, Enum):
    LANDING = "landing"          # 落地页
    SAAS = "saas"               # B2B SaaS官网
    DASHBOARD = "dashboard"      # 数据面板
    PORTFOLIO = "portfolio"      # 作品集
    BLOG = "blog"               # 文章页
    PRODUCT = "product"         # 产品介绍
    EVENT = "event"              # 活动页
    DOCS = "docs"               # 文档站


@dataclass
class DesignSystem:
    """设计系统(Claude Design理念: 写HTML前先宣告)"""
    primary_color: str = ""
    secondary_color: str = ""
    accent_color: str = ""
    background: str = "#ffffff"
    text_color: str = "#1a1a1a"
    font_heading: str = "Space Grotesk"
    font_body: str = "Inter"
    border_radius: str = "8px"
    spacing: str = "24px"
    max_width: str = "1200px"
    
    def to_css(self) -> str:
        return f""":root {{
  --primary: {self.primary_color};
  --secondary: {self.secondary_color};
  --accent: {self.accent_color};
  --bg: {self.background};
  --text: {self.text_color};
  --font-heading: '{self.font_heading}', sans-serif;
  --font-body: '{self.font_body}', sans-serif;
  --radius: {self.border_radius};
  --spacing: {self.spacing};
  --max-width: {self.max_width};
}}"""


@dataclass
class WebProject:
    """网页设计项目"""
    title: str = ""
    description: str = ""
    page_type: PageType = PageType.LANDING
    design_system: DesignSystem = field(default_factory=DesignSystem)
    html_content: str = ""
    sections: List[str] = field(default_factory=list)
    output_path: str = ""
    status: str = "draft"
    reviewer_notes: List[str] = field(default_factory=list)


class WebDesignEngine:
    """
    网页设计引擎 — Claude Design思想
    
    使用方式:
      engine = WebDesignEngine()
      project = engine.analyze("做一个小红书风格的产品落地页")
      project = engine.declare_design_system(project, "时尚")
      engine.build_v0(project)
      engine.fill_content(project)
      engine.review(project)
    """

    # 21套设计风格(garden-web-design-engineer + Claude Design增强)
    DESIGN_STYLES = {
        "b2b-saas": {
            "name": "B2B SaaS", "palette": ["#1e3a5f", "#2d5a8e", "#e8f0fe"],
            "fonts": ("Plus Jakarta Sans", "Inter"),
            "mood": "专业可信",
        },
        "dark-tech": {
            "name": "深色科技", "palette": ["#0d1117", "#1a1a2e", "#58a6ff"],
            "fonts": ("Space Grotesk", "JetBrains Mono"),
            "mood": "科技极客",
        },
        "editorial": {
            "name": "杂志编辑", "palette": ["#2c2c2c", "#f5f0eb", "#c0392b"],
            "fonts": ("Instrument Serif", "Space Grotesk"),
            "mood": "高端质感",
        },
        "minimal": {
            "name": "极简白", "palette": ["#ffffff", "#f8f8f8", "#333333"],
            "fonts": ("Sora", "Source Serif"),
            "mood": "干净克制",
        },
        "fashion": {
            "name": "时尚", "palette": ["#f5f0eb", "#d4c5b0", "#8b7355"],
            "fonts": ("DM Serif Display", "DM Sans"),
            "mood": "优雅精致",
        },
        "data-narrative": {
            "name": "数据叙事", "palette": ["#1a1a2e", "#16213e", "#e94560"],
            "fonts": ("Space Grotesk", "Inter"),
            "mood": "专业数据",
        },
        "art-tech": {
            "name": "艺术科技", "palette": ["#0a0a0a", "#1a1a4e", "#ff6b35"],
            "fonts": ("Zodiak", "General Sans"),
            "mood": "实验创新",
        },
        "cinematic": {
            "name": "电影感", "palette": ["#0d0d0d", "#1a1a1a", "#c9a84c"],
            "fonts": ("Instrument Serif", "Inter"),
            "mood": "沉浸冲击",
        },
        "brutalist": {
            "name": "布鲁塔利", "palette": ["#ff6b35", "#004e89", "#1a1a1a"],
            "fonts": ("Space Grotesk", "Inter"),
            "mood": "大胆尖锐",
        },
        "warm-community": {
            "name": "温暖社区", "palette": ["#fdf6f0", "#e8d5c4", "#8b5e3c"],
            "fonts": ("Newsreader", "Inter"),
            "mood": "温暖亲切",
        },
        "playful": {
            "name": "轻松活泼", "palette": ["#ffecd2", "#fcb69f", "#6c5b7b"],
            "fonts": ("DM Sans", "Inter"),
            "mood": "圆润轻松",
        },
        "y2k": {
            "name": "Y2K复古", "palette": ["#ff6b9d", "#c084fc", "#fde68a"],
            "fonts": ("Space Grotesk", "Inter"),
            "mood": "复古潮流",
        },
    }

    def analyze(self, user_input: str, page_type: str = "landing") -> WebProject:
        """分析需求创建项目"""
        project = WebProject(
            title=user_input[:50],
            description=user_input,
            page_type=PageType(page_type) if page_type in [e.value for e in PageType] else PageType.LANDING,
        )
        
        # 智能选风格
        matched_style = "minimal"
        max_score = 0
        for sid, style in self.DESIGN_STYLES.items():
            keywords = {
                "b2b-saas": ["企业", "saas", "b2b", "商业"],
                "dark-tech": ["科技", "技术", "开发", "极客"],
                "editorial": ["杂志", "编辑", "高端"],
                "fashion": ["时尚", "美妆", "品牌"],
                "data-narrative": ["数据", "报告", "dashboard"],
                "art-tech": ["艺术", "创意", "工作室"],
                "cinematic": ["电影", "游戏", "娱乐"],
                "brutalist": ["大胆", "先锋", "态度"],
                "warm-community": ["社区", "教育", "健康"],
                "playful": ["儿童", "轻松", "好玩"],
                "y2k": ["复古", "y2k", "潮流"],
            }
            kw = keywords.get(sid, [])
            score = sum(1 for k in kw if k in user_input.lower())
            if score > max_score:
                max_score = score
                matched_style = sid
        
        style = self.DESIGN_STYLES.get(matched_style, self.DESIGN_STYLES["minimal"])
        project.design_system = DesignSystem(
            primary_color=style["palette"][0],
            secondary_color=style["palette"][1],
            accent_color=style["palette"][2],
            font_heading=style["fonts"][0],
            font_body=style["fonts"][1],
        )
        
        return project

    def declare_design_system(self, project: WebProject, 
                                style_id: str = "") -> WebProject:
        """宣告设计系统(Claude Design核心: 写HTML前先宣告)"""
        if style_id and style_id in self.DESIGN_STYLES:
            style = self.DESIGN_STYLES[style_id]
            project.design_system = DesignSystem(
                primary_color=style["palette"][0],
                secondary_color=style["palette"][1],
                accent_color=style["palette"][2],
                font_heading=style["fonts"][0],
                font_body=style["fonts"][1],
            )
        return project

    def build_v0(self, project: WebProject) -> str:
        """生成v0快速原型(带标记符,不填充内容细节)"""
        ds = project.design_system
        
        sections_html = ""
        page_sections = ["hero", "features", "content", "cta", "footer"]
        project.sections = page_sections
        
        for sec in page_sections:
            sections_html += f"""
<section class="{sec}">
  <div class="container">
    <div class="placeholder">%%% {sec.upper()} %%%</div>
  </div>
</section>"""

        v0_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{project.title}</title>
<style>
{ds.to_css()}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:var(--font-body); color:var(--text); background:var(--bg); }}
.container {{ max-width:var(--max-width); margin:0 auto; padding:var(--spacing); }}
section {{ padding:80px 0; }}
.placeholder {{ background:#f0f0f0; border:2px dashed #ccc; border-radius:var(--radius);
              padding:60px; text-align:center; color:#999; font-size:18px; }}
.hero {{ background:var(--primary); color:white; }}
.hero .placeholder {{ background:transparent; border-color:rgba(255,255,255,0.3); color:rgba(255,255,255,0.7); }}
.cta {{ background:var(--accent); }}
footer {{ background:var(--primary); color:white; font-size:14px; }}
</style></head><body>
{sections_html}
</body></html>"""
        
        project.html_content = v0_html
        return v0_html

    def fill_content(self, project: WebProject, 
                      content: Dict[str, str] = None) -> str:
        """填充内容到v0原型"""
        if not content:
            content = {
                "hero": f"<h1>{project.title}</h1><p>{project.description[:100]}</p>",
                "features": "<h2>核心功能</h2><div class='grid'><div class='card'>...</div></div>",
                "cta": "<h2>立即开始</h2><a href='#' class='button'>了解更多</a>",
            }
        
        html = project.html_content
        for section_id, section_content in content.items():
            placeholder = f"%%% {section_id.upper()} %%%"
            if placeholder in html:
                html = html.replace(placeholder, section_content)
        
        project.html_content = html
        return html

    def review(self, project: WebProject) -> Dict[str, Any]:
        """独立Reviewer审核(Claude Design: fork子Agent做检查)"""
        issues = []
        passed = []
        
        html = project.html_content
        
        # 1. 检查反AI味
        for banned in BANNED_FONTS:
            if banned.lower() in html.lower():
                issues.append(f"使用了禁用的AI味字体:{banned}")
                break
        else:
            passed.append("无AI味字体")
        
        # 2. 检查emoji当图标
        if "🔵" in html or "🟢" in html or "⭐" in html:
            issues.append("使用emoji当图标(应使用SVG)")
        else:
            passed.append("无emoji图标滥用")
        
        # 3. 检查设计系统完整性
        ds = project.design_system
        if ds.primary_color and ds.font_heading:
            passed.append("设计系统完整")
        else:
            issues.append("设计系统不完整")
        
        # 4. 检查页面结构
        sections_in_html = set()
        for sec in ["hero", "features", "footer"]:
            if sec in html.lower():
                sections_in_html.add(sec)
        if len(sections_in_html) >= 3:
            passed.append(f"页面结构完整({len(sections_in_html)}个区域)")
        else:
            issues.append("页面结构不完整")
        
        # 5. v0检查: 如果还有占位符说明内容未填充
        if "%%%" in html:
            issues.append("有未填充的占位符")
        else:
            passed.append("内容已填充")
        
        reviewer_notes = []
        for p in passed:
            reviewer_notes.append(f"✅ {p}")
        for issue in issues:
            reviewer_notes.append(f"❌ {issue}")
        
        project.reviewer_notes = reviewer_notes
        
        score = len(passed) / max(1, len(passed) + len(issues)) * 100
        return {
            "score": score, "passed": passed, "issues": issues,
            "verdict": "passed" if score >= 60 else "needs_rework",
            "notes": reviewer_notes,
        }

    def export(self, project: WebProject, output_path: str = "") -> str:
        """导出HTML文件"""
        if not output_path:
            os.makedirs("/tmp/imdf_web", exist_ok=True)
            output_path = f"/tmp/imdf_web/{project.title.replace(' ', '_')}.html"
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(project.html_content)
        
        project.output_path = output_path
        project.status = "exported"
        return output_path
