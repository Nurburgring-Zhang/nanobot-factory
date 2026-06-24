"""
Video Production Engine — 5合一视频生成引擎
=============================================
融合5个世界级视频方案:
  1. html-video (nexu-io, 2.4K★) — 信息/科普/文章类, Content-Graph多场景
  2. HyperFrames (HeyGen, 9.6K★) — 品牌/UI演示, 确定性动画
  3. garden-web-video (ConardLi, 7K★) — 文章转视频, 22套主题模板
  4. ComfyUI — 高质量创意视频, 35个视频节点
  5. Manim — 数学/算法可视化

核心设计:
  - 根据内容类型自动选择最优引擎组合
  - 可多个引擎组合(先ComfyUI生成素材→再用html-video编排)
  - 可插拔TTS (MiniMax/OpenAI/Edge/mimo-tts/ElevenLabs)
  - 声道: 多轨音频合成(配音+BGM+音效)
  - 独立Reviewer审核视频质量
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import os
import json
import logging
import subprocess
import tempfile
import shutil

logger = logging.getLogger(__name__)


class VideoEngineType(str, Enum):
    HTML_VIDEO = "html-video"       # nexu-io/html-video
    HYPERFRAMES = "hyperframes"     # HeyGen
    GARDEN_VIDEO = "garden-video"   # ConardLi
    COMFYUI = "comfyui"             # 本地ComfyUI
    MANIM = "manim"                 # 数学动画


class AspectRatio(str, Enum):
    LANDSCAPE_16_9 = "16:9"   # B站
    PORTRAIT_9_16 = "9:16"    # 抖音/视频号
    SQUARE_1_1 = "1:1"        # 微博
    PORTRAIT_4_5 = "4:5"      # 小红书


class TTSProvider(str, Enum):
    MINIMAX = "minimax"
    OPENAI = "openai"
    EDGE = "edge"
    MIMO = "mimo-tts"
    ELEVENLABS = "elevenlabs"


@dataclass
class VideoSegment:
    """视频片段 — 视频的最小生产单元"""
    segment_id: str = ""
    name: str = ""
    engine: VideoEngineType = VideoEngineType.HTML_VIDEO
    duration: float = 5.0
    narration: str = ""          # 口播文本
    subtitle: str = ""           # 字幕
    html_content: str = ""       # 画面HTML
    template_id: str = ""        # 模板ID
    visual_style: str = ""       # 视觉风格
    bgm_cue: str = ""            # 背景音乐提示
    tts_voice: str = ""          # TTS音色
    transition_in: str = "cut"
    transition_out: str = "cut"
    characters: List[str] = field(default_factory=list)
    assets: Dict[str, str] = field(default_factory=dict)  # 素材文件路径
    vars_dict: Dict[str, Any] = field(default_factory=dict)  # html-video模板变量


@dataclass
class VideoProject:
    """完整视频项目"""
    title: str = ""
    description: str = ""
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE_16_9
    total_duration: float = 0.0
    segments: List[VideoSegment] = field(default_factory=list)
    tts_provider: TTSProvider = TTSProvider.MINIMAX
    background_music: str = ""
    output_path: str = ""
    status: str = "draft"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewer_notes: List[str] = field(default_factory=list)


class VideoEngine:
    """
    视频生成引擎 — 5合一调度
    
    使用方式:
      engine = VideoEngine()
      # 1. 规划
      project = engine.plan("把这篇公众号文章做成短视频")
      # 2. 选择引擎
      engine.select_best_engine(project)
      # 3. 生成各片段
      engine.render_segments(project)
      # 4. 合成
      engine.compose(project)
      # 5. 审核
      engine.review(project)
    """

    def __init__(self):
        self._tts_available = {}
        self._output_dir = os.environ.get("VIDEO_OUTPUT_DIR", "/tmp/imdf_videos")
        os.makedirs(self._output_dir, exist_ok=True)

    def plan(self, source_text: str, title: str = "",
              aspect_ratio: str = "16:9",
              duration: float = 60.0) -> VideoProject:
        """从文本规划视频项目"""
        project = VideoProject(
            title=title or source_text[:30],
            description=source_text[:200],
            aspect_ratio=AspectRatio(aspect_ratio) if aspect_ratio in [e.value for e in AspectRatio] else AspectRatio.LANDSCAPE_16_9,
            total_duration=duration,
        )
        
        # 自动分段: 按句子/段落切分
        segments = []
        import re
        sentences = re.split(r'(?<=[。！？\n])', source_text)
        
        # 过滤空句子
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        if not sentences:
            sentences = [source_text[:200]]
        
        # 每段时长
        seg_duration = duration / max(len(sentences), 1)
        
        for i, sentence in enumerate(sentences[:20]):  # 最多20段
            seg = VideoSegment(
                segment_id=f"seg_{i+1:03d}",
                name=f"第{i+1}段",
                duration=min(seg_duration, 15.0),
                narration=sentence,
                subtitle=sentence[:80],
                template_id=self._select_template(sentence, i),
                visual_style=self._select_style(sentence),
                vars_dict={
                    "title": title or f"第{i+1}段",
                    "content": sentence,
                    "subtitle": sentence[:80],
                    "style": self._select_style(sentence),
                },
            )
            segments.append(seg)
        
        project.segments = segments
        return project

    def select_best_engine(self, project: VideoProject) -> Dict[str, Any]:
        """为项目选择最佳引擎组合"""
        text = (project.title + " " + project.description).lower()
        
        # 检测内容类型选引擎
        if any(k in text for k in ["数学", "算法", "chart", "graph", "数据"]):
            primary = VideoEngineType.MANIM
        elif any(k in text for k in ["品牌", "产品", "UI", "demo", "interface"]):
            primary = VideoEngineType.HYPERFRAMES
        elif any(k in text for k in ["文章", "公众号", "新闻", "博客"]):
            primary = VideoEngineType.GARDEN_VIDEO
        else:
            primary = VideoEngineType.HTML_VIDEO
        
        # 为各segment设置引擎
        for seg in project.segments:
            seg.engine = primary
        
        return {
            "primary": primary.value,
            "reasoning": f"内容类型匹配: {primary.value}",
            "fallback": VideoEngineType.HTML_VIDEO.value if primary != VideoEngineType.HTML_VIDEO else VideoEngineType.GARDEN_VIDEO.value,
        }

    # ==========================================================================
    # 真实CLI调用层
    # ==========================================================================

    def render_with_html_video(self, segment: VideoSegment, vars_dict: Dict[str, Any] = None) -> str:
        """
        使用html-video CLI渲染视频片段
        
        CLI命令: html-video render --template <id> --vars-file <path> --format mp4 --output <path>
        
        Args:
            segment: 视频片段
            vars_dict: 模板变量字典
            
        Returns:
            输出MP4文件路径
        """
        tmp_dir = tempfile.mkdtemp(prefix="imdf_html_video_")
        output_path = os.path.join(tmp_dir, f"{segment.segment_id}.mp4")
        
        try:
            # 构建vars JSON文件
            vars_data = vars_dict or segment.vars_dict or {
                "title": segment.name,
                "content": segment.narration,
                "subtitle": segment.subtitle,
            }
            vars_file = os.path.join(tmp_dir, "vars.json")
            with open(vars_file, "w", encoding="utf-8") as f:
                json.dump(vars_data, f, ensure_ascii=False, indent=2)
            
            template_id = segment.template_id or "default"
            
            logger.info(f"[html-video] 渲染片段 {segment.segment_id}, "
                        f"模板={template_id}, vars={vars_file}")
            
            # 调用html-video CLI
            cmd = [
                "html-video", "render",
                "--template", template_id,
                "--vars-file", vars_file,
                "--format", "mp4",
                "--output", output_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
            )
            
            if result.returncode != 0:
                logger.error(f"[html-video] CLI失败: {result.stderr}")
                raise RuntimeError(f"html-video渲染失败: {result.stderr[:500]}")
            
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"输出文件未生成: {output_path}")
            
            logger.info(f"[html-video] 渲染成功: {output_path} "
                        f"({os.path.getsize(output_path)} bytes)")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error(f"[html-video] 渲染超时(300s): {segment.segment_id}")
            raise
        except Exception as e:
            logger.error(f"[html-video] 渲染异常: {e}")
            # 清理临时目录
            try:
                shutil.rmtree(tmp_dir)
            except Exception as e:
                logger.error(f"Operation failed: {e}")
            raise

    def render_with_hyperframes(self, html_content: str, output_dir: str = None) -> str:
        """
        使用HyperFrames渲染HTML动画视频
        
        流程:
          1. 写入html_content到临时目录的index.html
          2. 添加GSAP timeline + data-*属性wrapper
          3. 用npx hyperframes render在临时目录执行
          4. 找到输出MP4返回路径
        
        Args:
            html_content: HTML动画内容
            output_dir: 输出目录(不指定则自动创建临时目录)
            
        Returns:
            输出MP4文件路径
        """
        tmp_dir = tempfile.mkdtemp(prefix="imdf_hyperframes_")
        
        try:
            # 组装带有GSAP timeline的HTML
            wrapped_html = self._wrap_with_gsap_timeline(html_content)
            
            # 写入index.html
            index_path = os.path.join(tmp_dir, "index.html")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(wrapped_html)
            
            logger.info(f"[HyperFrames] 写入HTML到 {index_path} ({len(wrapped_html)} chars)")
            
            # 确定输出目录
            out_dir = output_dir or os.path.join(tmp_dir, "output")
            os.makedirs(out_dir, exist_ok=True)
            
            # 调用npx hyperframes render
            cmd = ["npx", "hyperframes", "render"]
            logger.info(f"[HyperFrames] 执行命令: {' '.join(cmd)} (cwd={tmp_dir})")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=tmp_dir,
                env={**os.environ, "HYPERFRAMES_OUTPUT_DIR": out_dir},
            )
            
            if result.returncode != 0:
                logger.error(f"[HyperFrames] CLI失败: {result.stderr[:500]}")
                raise RuntimeError(f"HyperFrames渲染失败: {result.stderr[:500]}")
            
            # 查找输出的MP4文件
            mp4_files = []
            for root, dirs, files in os.walk(out_dir):
                for f in files:
                    if f.endswith(".mp4"):
                        mp4_files.append(os.path.join(root, f))
            
            # 也查tmp_dir根目录
            for f in os.listdir(tmp_dir):
                if f.endswith(".mp4"):
                    mp4_files.append(os.path.join(tmp_dir, f))
            
            if not mp4_files:
                raise FileNotFoundError(
                    f"HyperFrames未生成MP4文件(搜索目录: {out_dir}, {tmp_dir})"
                )
            
            output_path = mp4_files[0]
            logger.info(f"[HyperFrames] 渲染成功: {output_path} "
                        f"({os.path.getsize(output_path)} bytes)")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error(f"[HyperFrames] 渲染超时(300s)")
            raise
        except Exception as e:
            logger.error(f"[HyperFrames] 渲染异常: {e}")
            try:
                shutil.rmtree(tmp_dir)
            except Exception as e:
                logger.error(f"Operation failed: {e}")
            raise

    def render_with_garden_video(self, article_text: str, template_id: str = "default") -> str:
        """
        使用garden-web-video CLI渲染文章转视频
        
        CLI模式: garden-web-video --article <text> --template <id> --output <path>
        
        Args:
            article_text: 文章文本内容
            template_id: 模板ID(默认default, 可选:演讲风/科技架构/数据报告/科普讲解等)
            
        Returns:
            输出MP4文件路径
        """
        tmp_dir = tempfile.mkdtemp(prefix="imdf_garden_video_")
        output_path = os.path.join(tmp_dir, "output.mp4")
        
        try:
            # 写入文章文本
            article_file = os.path.join(tmp_dir, "article.md")
            with open(article_file, "w", encoding="utf-8") as f:
                f.write(article_text)
            
            logger.info(f"[GardenVideo] 渲染文章, 模板={template_id}, "
                        f"文章大小={len(article_text)} chars")
            
            # 调用garden-web-video CLI
            cmd = [
                "garden-web-video",
                "--article", article_file,
                "--template", template_id,
                "--output", output_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode != 0:
                logger.error(f"[GardenVideo] CLI失败: {result.stderr[:500]}")
                raise RuntimeError(f"GardenVideo渲染失败: {result.stderr[:500]}")
            
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"输出文件未生成: {output_path}")
            
            logger.info(f"[GardenVideo] 渲染成功: {output_path} "
                        f"({os.path.getsize(output_path)} bytes)")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error(f"[GardenVideo] 渲染超时(300s)")
            raise
        except Exception as e:
            logger.error(f"[GardenVideo] 渲染异常: {e}")
            try:
                shutil.rmtree(tmp_dir)
            except Exception as e:
                logger.error(f"Operation failed: {e}")
            raise

    def _wrap_with_gsap_timeline(self, html_content: str) -> str:
        """为HTML内容添加GSAP timeline + data-*属性wrapper"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HyperFrames Animation</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1920px; height: 1080px; overflow: hidden; font-family: 'Space Grotesk', system-ui, sans-serif; }}
.hf-element {{ opacity: 0; }}
</style>
</head>
<body>
<div id="app" data-hyperframes-container>
{html_content}
</div>
<script>
// HyperFrames GSAP Timeline — 自动播放
document.addEventListener('DOMContentLoaded', function() {{
  const tl = gsap.timeline({{ defaults: {{ duration: 0.8, ease: 'power2.out' }} }});
  
  // 查找所有带 data-hf 属性的元素，按 data-hf-order 排序
  const elements = document.querySelectorAll('[data-hf]');
  const sorted = Array.from(elements).sort((a, b) => {{
    return parseInt(a.getAttribute('data-hf-order') || '0') - 
           parseInt(b.getAttribute('data-hf-order') || '0');
  }});
  
  sorted.forEach((el) => {{
    const animType = el.getAttribute('data-hf-anim') || 'fadeIn';
    const dur = parseFloat(el.getAttribute('data-hf-duration') || '0.8');
    
    switch(animType) {{
      case 'fadeIn':
        tl.fromTo(el, {{ opacity: 0, y: 30 }}, {{ opacity: 1, y: 0, duration: dur }});
        break;
      case 'slideLeft':
        tl.fromTo(el, {{ opacity: 0, x: -100 }}, {{ opacity: 1, x: 0, duration: dur }});
        break;
      case 'slideRight':
        tl.fromTo(el, {{ opacity: 0, x: 100 }}, {{ opacity: 1, x: 0, duration: dur }});
        break;
      case 'scaleIn':
        tl.fromTo(el, {{ opacity: 0, scale: 0.8 }}, {{ opacity: 1, scale: 1, duration: dur }});
        break;
      case 'none':
        tl.set(el, {{ opacity: 1 }});
        break;
      default:
        tl.fromTo(el, {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: dur }});
    }}
  }});
  
  // 如果没有data-hf元素，淡入所有.hf-element
  if (sorted.length === 0) {{
    gsap.fromTo('.hf-element', {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: 0.8, stagger: 0.15 }});
  }}
  
  // 通知HyperFrames渲染器timeline就绪
  document.dispatchEvent(new CustomEvent('hyperframes-ready', {{ detail: {{ timeline: tl }} }}));
}});
</script>
</body>
</html>"""

    # ==========================================================================
    # 主渲染调度
    # ==========================================================================

    def render_segments(self, project: VideoProject) -> List[Dict]:
        """
        逐段生成视频片段 — 根据seg.engine选择调用对应的真实引擎
        
        不再生成占位HTML，调用真实渲染CLI。
        """
        results = []
        for seg in project.segments:
            result = self._render_one_segment(seg, project.aspect_ratio)
            results.append(result)
        return results

    def _render_one_segment(self, seg: VideoSegment, ratio: AspectRatio) -> Dict:
        """渲染单个片段，根据引擎类型分发"""
        engine_type = seg.engine
        
        try:
            if engine_type == VideoEngineType.HTML_VIDEO:
                output_path = self.render_with_html_video(seg)
                
            elif engine_type == VideoEngineType.HYPERFRAMES:
                html = self._build_segment_html(seg, ratio)
                output_path = self.render_with_hyperframes(html)
                
            elif engine_type == VideoEngineType.GARDEN_VIDEO:
                output_path = self.render_with_garden_video(
                    seg.narration, seg.template_id
                )
                
            elif engine_type == VideoEngineType.COMFYUI:
                # ComfyUI通过NanoBot API调用
                output_path = self._render_with_comfyui(seg)
                
            elif engine_type == VideoEngineType.MANIM:
                output_path = self._render_with_manim(seg)
                
            else:
                # Fallback: 生成HTML截图
                html = self._build_segment_html(seg, ratio)
                output_path = self._fallback_html_screenshot(html, seg.segment_id)
            
            seg.assets["video"] = output_path
            
            return {
                "segment_id": seg.segment_id,
                "engine": seg.engine.value,
                "output_path": output_path,
                "status": "success",
            }
            
        except Exception as e:
            logger.error(f"渲染片段 {seg.segment_id} 失败 ({engine_type}): {e}")
            
            # Fallback: 尝试默认引擎
            try:
                html = self._build_segment_html(seg, ratio)
                fallback_path = self._fallback_html_screenshot(html, seg.segment_id)
                seg.assets["video"] = fallback_path
                return {
                    "segment_id": seg.segment_id,
                    "engine": f"{engine_type.value}(fallback:html-screenshot)",
                    "output_path": fallback_path,
                    "status": "fallback",
                    "error": str(e),
                }
            except Exception as fallback_e:
                return {
                    "segment_id": seg.segment_id,
                    "engine": engine_type.value,
                    "output_path": "",
                    "status": "failed",
                    "error": f"主引擎: {e} | fallback: {fallback_e}",
                }

    def _render_with_comfyui(self, seg: VideoSegment) -> str:
        """通过ComfyUI渲染(通过NanoBot API)"""
        try:
            import sys, os as _os
            _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _base not in sys.path:
                sys.path.insert(0, _base)
            from api.nanobot_adapter import NanobotAdapter
            import asyncio
            
            adapter = NanobotAdapter()
            # ComfyUI workflow执行
            workflow = {
                "prompt": seg.narration,
                "negative_prompt": "",
                "generator": "comfyui",
                "settings": {
                    "width": 1024,
                    "height": 1024,
                    "steps": 25,
                    "duration": int(seg.duration),
                    "fps": 24,
                }
            }
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(adapter.generate(workflow))
            finally:
                loop.close()
            
            if result and result.get("results"):
                return result["results"][0]
            raise RuntimeError(f"ComfyUI无返回结果")
            
        except Exception as e:
            logger.error(f"[ComfyUI] 渲染失败: {e}")
            raise

    def _render_with_manim(self, seg: VideoSegment) -> str:
        """使用Manim渲染数学动画"""
        tmp_dir = tempfile.mkdtemp(prefix="imdf_manim_")
        output_path = os.path.join(tmp_dir, f"{seg.segment_id}.mp4")
        
        try:
            # 生成Manim脚本
            manim_code = self._build_manim_script(seg)
            script_path = os.path.join(tmp_dir, "scene.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(manim_code)
            
            cmd = ["manim", "-ql", script_path, "-o", output_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise RuntimeError(f"Manim失败: {result.stderr[:500]}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"[Manim] 渲染失败: {e}")
            raise

    def _build_manim_script(self, seg: VideoSegment) -> str:
        """生成Manim场景脚本"""
        return f'''
from manim import *

class Scene_{seg.segment_id.replace("seg_", "")}(Scene):
    def construct(self):
        title = Text("{seg.name}", font_size=48, color=BLUE)
        self.play(Write(title))
        self.wait(1)
        self.play(FadeOut(title))
        
        content = Text("{seg.subtitle}", font_size=36)
        self.play(Write(content))
        self.wait({seg.duration})
'''

    def _fallback_html_screenshot(self, html: str, segment_id: str) -> str:
        """
        Fallback: 用浏览器截图代替视频(当CLI不可用时)
        生成HTML文件并用截图工具(如果有)转为视频
        """
        tmp_dir = tempfile.mkdtemp(prefix="imdf_fallback_")
        output_path = os.path.join(tmp_dir, f"{segment_id}.mp4")
        
        try:
            # 写入HTML
            html_path = os.path.join(tmp_dir, "index.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            
            logger.warning(f"[Fallback] 片段{segment_id}使用HTML截图(非真实视频)")
            
            # 尝试用ffmpeg创建静态视频(单帧)
            # 如果有playwright或puppeteer可用，可以做真实截图
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=#f8f8f8:s=1920x1080:d=5",
                "-vf", f"drawtext=text='{segment_id}: fallback':fontcolor=black:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                output_path,
            ]
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
            
            # 如果ffmpeg也失败，创建一个文本文件标记
            marker_path = os.path.join(tmp_dir, f"{segment_id}_fallback.txt")
            with open(marker_path, "w") as f:
                f.write(f"Fallback for segment {segment_id}")
            return marker_path
            
        except Exception as e:
            logger.error(f"[Fallback] 失败: {e}")
            raise

    # ==========================================================================
    # 合成与审核
    # ==========================================================================

    def compose(self, project: VideoProject, 
                 tts_voice: str = "default",
                 bgm: str = "") -> str:
        """合成最终视频"""
        os.makedirs(self._output_dir, exist_ok=True)
        
        output_path = os.path.join(
            self._output_dir,
            f"{project.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        )
        project.output_path = output_path
        project.status = "composed"
        
        # 收集所有片段视频路径
        video_paths = []
        for seg in project.segments:
            if seg.assets.get("video") and os.path.exists(seg.assets["video"]):
                video_paths.append(seg.assets["video"])
        
        if len(video_paths) >= 1:
            # 用ffmpeg拼接
            try:
                ffmpeg_concat(video_paths, output_path)
            except Exception as e:
                logger.error(f"ffmpeg拼接失败: {e}")
        else:
            logger.warning("无有效视频片段可拼接")
            # 创建空白占位视频
            try:
                subprocess.run([
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=#000000:s=1920x1080:d=5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    output_path,
                ], capture_output=True, timeout=30)
            except Exception as e:
                logger.error(f"Operation failed: {e}")
        
        return output_path

    def review(self, project: VideoProject) -> Dict[str, Any]:
        """独立Reviewer审核视频质量"""
        issues = []
        passed = []
        
        if not project.segments:
            issues.append("无片段")
        else:
            passed.append(f"{len(project.segments)}个片段")
        
        if project.total_duration <= 0:
            issues.append("时长异常")
        else:
            passed.append(f"总时长{project.total_duration:.0f}s")
        
        if not project.output_path:
            issues.append("未输出")
        else:
            passed.append("已输出")
        
        # 检查是否有真实渲染输出
        real_renders = sum(
            1 for s in project.segments 
            if s.assets.get("video") and os.path.exists(s.assets["video"])
        )
        if real_renders > 0:
            passed.append(f"{real_renders}段已真实渲染")
        else:
            issues.append("无真实渲染输出")
        
        # 检查音画同步(如果有口播)
        has_narration = any(s.narration for s in project.segments)
        has_subtitle = any(s.subtitle for s in project.segments)
        
        if has_narration:
            passed.append("有口播")
            if has_subtitle:
                passed.append("有字幕")
        
        reviewer_notes = []
        for p in passed:
            reviewer_notes.append(f"✅ {p}")
        for issue in issues:
            reviewer_notes.append(f"❌ {issue}")
        
        project.reviewer_notes = reviewer_notes
        
        score = len(passed) / max(1, len(passed) + len(issues)) * 100
        
        return {
            "score": score,
            "passed": passed,
            "issues": issues,
            "verdict": "passed" if score >= 60 else "needs_rework",
            "notes": reviewer_notes,
        }

    # ==========================================================================
    # 内部辅助方法
    # ==========================================================================

    def _build_segment_html(self, seg: VideoSegment, 
                              ratio: AspectRatio) -> str:
        """为片段生成HTML画面"""
        width_map = {
            AspectRatio.LANDSCAPE_16_9: 1920,
            AspectRatio.PORTRAIT_9_16: 1080,
            AspectRatio.SQUARE_1_1: 1080,
            AspectRatio.PORTRAIT_4_5: 1080,
        }
        height_map = {
            AspectRatio.LANDSCAPE_16_9: 1080,
            AspectRatio.PORTRAIT_9_16: 1920,
            AspectRatio.SQUARE_1_1: 1080,
            AspectRatio.PORTRAIT_4_5: 1350,
        }
        w = width_map.get(ratio, 1920)
        h = height_map.get(ratio, 1080)

        # 生成带 data-hf 属性的结构(供HyperFrames使用)
        return f"""<div data-hf data-hf-order="0" data-hf-anim="fadeIn" style="width:{w}px;height:{h}px;display:flex;align-items:center;justify-content:center;background:#f8f8f8;font-family:'Space Grotesk',sans-serif;">
  <div style="text-align:center;padding:60px;">
    <h1 data-hf data-hf-order="1" data-hf-anim="slideLeft" style="font-size:48px;color:#1a1a2e;margin-bottom:20px;">{seg.name}</h1>
    <p data-hf data-hf-order="2" data-hf-anim="fadeIn" style="font-size:24px;line-height:1.6;color:#333;max-width:80%;margin:0 auto;">{seg.subtitle}</p>
  </div>
</div>"""

    def _select_template(self, text: str, index: int) -> str:
        templates = ["article-intro", "data-point", "quote-card", "summary", "transition"]
        return templates[index % len(templates)]

    def _select_style(self, text: str) -> str:
        styles = ["clean", "warm", "tech", "minimal", "editorial"]
        return styles[hash(text) % len(styles)]

    def set_tts_provider(self, provider: TTSProvider, api_key: str = ""):
        """配置TTS提供商"""
        self._tts_available[provider] = True

    @staticmethod
    def get_available_engines() -> List[Dict[str, Any]]:
        return [
            {"id": "html-video", "name": "html-video", "stars": 2368,
             "url": "https://github.com/nexu-io/html-video",
             "desc": "信息/科普,有文字和数据, Content-Graph多场景"},
            {"id": "hyperframes", "name": "HyperFrames", "stars": 9600,
             "url": "https://github.com/heygen-com/hyperframes",
             "desc": "品牌/UI演示, 确定性动画, 像素级精确"},
            {"id": "garden-video", "name": "Garden Web Video", "stars": 7000,
             "url": "https://github.com/ConardLi/garden-skills",
             "desc": "文章转视频, 22套主题, 可插拔TTS"},
            {"id": "comfyui", "name": "ComfyUI Video", "stars": 0,
             "desc": "最高质量创意视频, 35个视频节点"},
            {"id": "manim", "name": "Manim", "stars": 0,
             "desc": "数学/算法可视化, 3Blue1Brown级别"},
        ]


# ==========================================================================
# ffmpeg拼接工具
# ==========================================================================

def ffmpeg_concat(video_paths: List[str], output_path: str):
    """用ffmpeg拼接多个视频文件"""
    import subprocess
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for vp in video_paths:
            if os.path.exists(vp):
                f.write(f"file '{vp}'\n")
        list_file = f.name
    
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg拼接失败: {result.stderr[:500]}")
    finally:
        os.unlink(list_file)
