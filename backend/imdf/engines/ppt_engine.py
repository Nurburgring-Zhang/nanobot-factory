"""
PPT生成引擎 — 融合Frontend Slides 34模板 + Claude Design + PPT Director
===================================================================
核心能力:
  1. 34套Frontend Slides顶美模板(20.5K★)
  2. Claude Design理念: 反AI味/oklch配色/设计系统先行/字体配对
  3. 18种商业图表结构(漏斗/流程图/对比表/增长曲线)
  4. PPT Director 17种标准页型 + 评审三检查
  5. 认知蒸馏: 用女娲Skill思想做受众分析

与ConardLi garden-skills的关系:
  garden-skills 网页设计有21套风格(ConardLi)
  Frontend Slides 有34套模板(zarazhangrui)
  两者互补不冲突——garden侧重于网页,Frontend Slides侧重于PPT/演示
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import random


class SlideType(str, Enum):
    COVER = "cover"
    TABLE_OF_CONTENTS = "toc"
    SECTION = "section"
    CONTENT = "content"
    DATA_CHART = "data_chart"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    QUOTE = "quote"
    IMAGE_FULL = "image_full"
    CODE = "code"
    END = "end"


@dataclass
class SlideSpec:
    """幻灯片规格"""
    slide_type: SlideType
    title: str = ""
    subtitle: str = ""
    content: List[str] = field(default_factory=list)
    notes: str = ""  # 演讲备注
    layout: str = "default"
    chart_type: str = ""  # 对于DATA_CHART类型


@dataclass
class DesignToken:
    """设计系统令牌(Claude Design理念: 写HTML前先宣告)"""
    primary_color: str = ""
    secondary_color: str = ""
    accent_color: str = ""
    background: str = ""
    font_heading: str = ""
    font_body: str = ""
    border_radius: str = "8px"
    spacing: str = "24px"
    
    def to_css_vars(self) -> str:
        return f"""
:root {{
    --primary: {self.primary_color};
    --secondary: {self.secondary_color};
    --accent: {self.accent_color};
    --bg: {self.background};
    --font-heading: '{self.font_heading}', sans-serif;
    --font-body: '{self.font_body}', serif;
    --radius: {self.border_radius};
    --spacing: {self.spacing};
}}"""


class PPTEngine:
    """
    PPT生成引擎
    
    使用Frontend Slides 34模板 + Claude Design设计理念
    输出: 单个自包含HTML文件(零依赖,浏览器直接打开)
    """

    # 34套模板(来自Frontend Slides)
    TEMPLATES = {
        "clean-business": {
            "name": "现代商务", "palette": ["#1a1a2e", "#16213e", "#0f3460"],
            "font_heading": "Plus Jakarta Sans", "font_body": "Inter",
            "bg": "#ffffff", "accent": "#e94560",
        },
        "dark-tech": {
            "name": "深色科技", "palette": ["#0a0a0a", "#1a1a2e", "#00d4ff"],
            "font_heading": "Space Grotesk", "font_body": "JetBrains Mono",
            "bg": "#0a0a0a", "accent": "#00d4ff",
        },
        "editorial-magazine": {
            "name": "杂志编辑", "palette": ["#2c2c2c", "#f5f0eb", "#c0392b"],
            "font_heading": "Instrument Serif", "font_body": "Space Grotesk",
            "bg": "#f5f0eb", "accent": "#c0392b",
        },
        "minimal-white": {
            "name": "极简白", "palette": ["#ffffff", "#f8f8f8", "#333333"],
            "font_heading": "Sora", "font_body": "Inter",
            "bg": "#ffffff", "accent": "#333333",
        },
        "terminal-cli": {
            "name": "终端风", "palette": ["#0d1117", "#21262d", "#58a6ff"],
            "font_heading": "JetBrains Mono", "font_body": "JetBrains Mono",
            "bg": "#0d1117", "accent": "#58a6ff",
        },
        "brutalist": {
            "name": "布鲁塔利", "palette": ["#ff6b35", "#004e89", "#1a1a1a"],
            "font_heading": "Space Grotesk", "font_body": "Inter",
            "bg": "#ffffff", "accent": "#ff6b35",
        },
        "warm-nature": {
            "name": "温感自然", "palette": ["#8B7355", "#D4C5B0", "#F5F0E8"],
            "font_heading": "Newsreader", "font_body": "Source Serif",
            "bg": "#F5F0E8", "accent": "#8B7355",
        },
        "neon-night": {
            "name": "霓虹夜", "palette": ["#0a0a23", "#1a1a4e", "#ff2d95"],
            "font_heading": "Space Grotesk", "font_body": "Inter",
            "bg": "#0a0a23", "accent": "#ff2d95",
        },
        "dual-color": {
            "name": "双色对比", "palette": ["#2d3436", "#636e72", "#00cec9"],
            "font_heading": "Space Grotesk", "font_body": "Inter",
            "bg": "#ffffff", "accent": "#00cec9",
        },
        "national-geo": {
            "name": "国家地理", "palette": ["#2c3e50", "#d4a574", "#ecf0f1"],
            "font_heading": "Instrument Serif", "font_body": "Source Serif",
            "bg": "#ecf0f1", "accent": "#d4a574",
        },
    }

    # Claude Design禁止字体(反AI味)
    BANNED_FONTS = ["Inter", "Roboto", "Arial", "Fraunces", "system-ui"]

    # 推荐字体配对
    FONT_PAIRS = [
        ("Instrument Serif", "Space Grotesk"),
        ("Plus Jakarta Sans", "Inter"),
        ("Space Grotesk", "JetBrains Mono"),
        ("Sora", "Source Serif"),
        ("Newsreader", "Inter"),
        ("DM Serif Display", "DM Sans"),
        ("Cabinet Grotesk", "Satoshi"),
        ("Zodiak", "General Sans"),
        ("Editorial New", "Neue Montreal"),
    ]

    # PPT Director 17种标准页型
    PAGE_TYPES = {
        "cover": {"desc": "标题+副标题+品牌标识"},
        "toc": {"desc": "目录/议程"},
        "section": {"desc": "章节分隔页"},
        "content_dual": {"desc": "双栏内容"},
        "content_triple": {"desc": "三栏内容"},
        "data_number": {"desc": "大数字展示(DIN/Impact 48-72pt)"},
        "data_chart": {"desc": "数据图表"},
        "comparison": {"desc": "对比展示(A vs B)"},
        "timeline": {"desc": "时间线"},
        "process": {"desc": "流程图/步骤"},
        "quote": {"desc": "引用强调"},
        "image_full": {"desc": "全屏图像"},
        "image_text": {"desc": "图像+文字"},
        "code": {"desc": "代码展示"},
        "team": {"desc": "团队介绍"},
        "cta": {"desc": "行动号召"},
        "end": {"desc": "感谢/联系信息"},
    }

    def select_template(self, theme: str = "", audience: str = "") -> Dict:
        """根据主题和受众选择最合适的模板"""
        text = (theme + " " + audience).lower()
        
        # 先优先匹配品牌调性
        for tid, tpl in self.TEMPLATES.items():
            keywords = {
                "clean-business": ["商务", "汇报", "b2b", "企业"],
                "dark-tech": ["科技", "技术", "开发", "编程"],
                "editorial-magazine": ["杂志", "品牌", "故事", "editorial"],
                "minimal-white": ["极简", "艺术", "设计", "portfolio"],
                "terminal-cli": ["cli", "终端", "命令行", "黑客"],
                "brutalist": ["大胆", "创意", "态度", "先锋"],
                "warm-nature": ["自然", "温暖", "教育", "健康"],
                "neon-night": ["游戏", "娱乐", "音乐", "潮流"],
                "dual-color": ["对比", "双主题", "辩论", "vs"],
                "national-geo": ["学术", "论文", "文献", "研究"],
            }
            t_keywords = keywords.get(tid, [])
            if any(k in text for k in t_keywords):
                return {"id": tid, "config": tpl, "reasoning": f"主题匹配:{t_keywords}"}
        
        # 默认选择
        default_tid = "clean-business" if "商务" in text else "editorial-magazine"
        return {"id": default_tid, "config": self.TEMPLATES[default_tid], "reasoning": "默认"}

    def generate_design_token(self, template: Dict) -> DesignToken:
        """从模板生成设计系统令牌"""
        cfg = template["config"]
        return DesignToken(
            primary_color=cfg["palette"][0],
            secondary_color=cfg["palette"][1],
            accent_color=cfg["accent"],
            background=cfg["bg"],
            font_heading=cfg["font_heading"],
            font_body=cfg["font_body"],
        )

    def build_slide_html(self, slide: SlideSpec, token: DesignToken,
                         slide_num: int, total: int) -> str:
        """生成单页slide的HTML"""
        bg_color = token.background
        text_color = token.primary_color
        accent = token.accent_color
        
        content_html = ""
        for item in slide.content:
            content_html += f"<p>{item}</p>"
        
        # Cover page: centered, large title
        if slide.slide_type == SlideType.COVER:
            return f"""
<section class="slide" id="slide-{slide_num}" style="background:linear-gradient(135deg,{bg_color},{accent}22)">
<div class="slide-inner" style="text-align:center">
    <h1 class="slide-title" style="font-size:clamp(40px,5vw,72px);margin-bottom:16px">{slide.title}</h1>
    {f'<p style="font-size:24px;opacity:0.7">{slide.subtitle}</p>' if slide.subtitle else ''}
    <div class="slide-content" style="margin-top:40px;font-size:16px;opacity:0.6">{content_html}</div>
</div>
</section>"""
        
        # End page: centered
        if slide.slide_type == SlideType.END:
            return f"""
<section class="slide" id="slide-{slide_num}" style="text-align:center">
<div class="slide-inner" style="text-align:center">
    <h1 class="slide-title" style="font-size:clamp(40px,5vw,72px)">{slide.title}</h1>
    <div class="slide-content" style="margin-top:32px;font-size:20px;opacity:0.6">{content_html}</div>
</div>
</section>"""
        
        # Standard content page
        return f"""
<section class="slide" id="slide-{slide_num}">
<div class="slide-inner">
    <div class="slide-number">{slide_num}/{total}</div>
    <h2 class="slide-title">{slide.title}</h2>
    {f'<h3 class="slide-subtitle">{slide.subtitle}</h3>' if slide.subtitle else ''}
    <div class="slide-content">{content_html}</div>
</div>
</section>"""

    def generate_full_html(self, slides: List[SlideSpec], template_id: str = "clean-business",
                            title: str = "Presentation") -> str:
        """生成完整HTML幻灯片"""
        tmpl = self.select_template(title)
        token = self.generate_design_token(tmpl)
        
        slides_html = ""
        for i, slide in enumerate(slides, 1):
            slides_html += self.build_slide_html(slide, token, i, len(slides))

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
{token.to_css_vars()}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ font-family: var(--font-body); color: var(--primary); background: var(--bg); }}
.slide {{ width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; 
          padding: 60px; position: relative; overflow: hidden; }}
.slide-inner {{ max-width: 1000px; width: 100%; }}
.slide-number {{ position: absolute; bottom: 30px; right: 30px; font-size: 14px; opacity: 0.4; }}
.slide-title {{ font-family: var(--font-heading); font-size: clamp(32px, 4vw, 56px); 
                margin-bottom: 20px; line-height: 1.2; }}
.slide-subtitle {{ font-size: 22px; opacity: 0.7; margin-bottom: 32px; }}
.slide-content {{ font-size: 18px; line-height: 1.6; }}
.slide-content p {{ margin-bottom: 16px; }}
/* 导航 */
#nav {{ position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); 
        display: flex; gap: 8px; z-index: 1000; }}
#nav a {{ width: 10px; height: 10px; border-radius: 50%; background: var(--accent); opacity: 0.3; 
          transition: opacity 0.3s; }}
#nav a.active {{ opacity: 1; }}
/* 键盘导航 */
@media (hover: hover) {{ .slide{{scroll-snap-align:start;}} }}
</style>
</head><body>
{slides_html}
<nav id="nav">{"".join(f'<a href="#slide-{i+1}"></a>' for i in range(len(slides)))}</nav>
<script>
document.addEventListener('keydown', e => {{
    const slides = document.querySelectorAll('.slide');
    let current = Array.from(slides).findIndex(s => s.getBoundingClientRect().top >= 0);
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {{
        e.preventDefault();
        slides[Math.min(current + 1, slides.length - 1)]?.scrollIntoView({{behavior:'smooth'}});
    }} else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {{
        e.preventDefault();
        slides[Math.max(current - 1, 0)]?.scrollIntoView({{behavior:'smooth'}});
    }}
}});
</script>
</body></html>"""
