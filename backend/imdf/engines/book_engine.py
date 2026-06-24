"""
绘本一键成书引擎 (Book Engine)
================================
核心管线：书名/故事/Style → LLM生成逐页插图描述 → 图片生成API → 排版组装(HTML/PDF)

Usage:
    engine = BookEngine()
    result = await engine.generate_book(title, story, style, num_pages)
    html = await engine.render_html(book_id)
    pdf = await engine.render_pdf(book_id)
"""

import os
import uuid
import json
import logging
import asyncio
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class BookPage:
    """单页绘本数据"""
    page_num: int
    text: str                          # 页面文案
    illustration_prompt: str = ""      # LLM生成的插图提示词
    image_url: str = ""                # 生成的图片URL
    image_base64: str = ""             # base64图片(用于HTML嵌入)
    image_path: str = ""               # 本地图片路径

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_num": self.page_num,
            "text": self.text,
            "illustration_prompt": self.illustration_prompt,
            "image_url": self.image_url,
            "image_path": self.image_path,
        }


@dataclass
class Book:
    """绘本对象"""
    id: str
    title: str
    story: str
    style: str
    audience: str = "3-6"
    pages: List[BookPage] = field(default_factory=list)
    status: str = "draft"              # draft / generating / illustrations_ready / complete / error
    created_at: str = ""
    updated_at: str = ""
    cover_url: str = ""
    export_formats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "story": self.story,
            "style": self.style,
            "audience": self.audience,
            "pages": [p.to_dict() for p in self.pages],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cover_url": self.cover_url,
            "export_formats": self.export_formats,
            "page_count": len(self.pages),
        }


# ============================================================================
# Book Engine
# ============================================================================

class BookEngine:
    """
    绘本生成引擎 — 通过LLM+图片生成API完成逐页绘本创建。

    Config (from .env):
        IMDF_BOOK_IMAGE_API_URL   — 图片生成API地址 (e.g. http://localhost:7860/sdapi/v1/txt2img)
        IMDF_BOOK_IMAGE_API_KEY   — 可选: API Key
        IMDF_BOOK_IMAGE_API_TYPE  — API类型: 'sdwebui' | 'comfyui' | 'openai' | 'generic'
        IMDF_BOOK_OUTPUT_DIR      — 输出目录 (default: data/books/)
    """

    OUTPUT_DIR = os.environ.get("IMDF_BOOK_OUTPUT_DIR", "data/books")
    IMAGE_API_URL = os.environ.get("IMDF_BOOK_IMAGE_API_URL", "http://localhost:7860/sdapi/v1/txt2img")
    IMAGE_API_KEY = os.environ.get("IMDF_BOOK_IMAGE_API_KEY", "")
    IMAGE_API_TYPE = os.environ.get("IMDF_BOOK_IMAGE_API_TYPE", "sdwebui")

    def __init__(self):
        self._books: Dict[str, Book] = {}
        self._load_books()
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
        os.makedirs(os.path.join(self.OUTPUT_DIR, "images"), exist_ok=True)

    def _load_books(self):
        """从磁盘恢复已保存的绘本"""
        meta_path = os.path.join(self.OUTPUT_DIR, "books_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for book_data in data:
                    pages = []
                    for p in book_data.get("pages", []):
                        pages.append(BookPage(
                            page_num=p.get("page_num", 0),
                            text=p.get("text", ""),
                            illustration_prompt=p.get("illustration_prompt", ""),
                            image_url=p.get("image_url", ""),
                            image_path=p.get("image_path", ""),
                        ))
                    book = Book(
                        id=book_data["id"],
                        title=book_data.get("title", ""),
                        story=book_data.get("story", ""),
                        style=book_data.get("style", "storybook"),
                        audience=book_data.get("audience", "3-6"),
                        pages=pages,
                        status=book_data.get("status", "draft"),
                        created_at=book_data.get("created_at", ""),
                        updated_at=book_data.get("updated_at", ""),
                        cover_url=book_data.get("cover_url", ""),
                        export_formats=book_data.get("export_formats", []),
                    )
                    self._books[book.id] = book
                logger.info(f"Loaded {len(self._books)} books from disk")
            except Exception as e:
                logger.warning(f"Failed to load books: {e}")

    def _save_books(self):
        """持久化绘本元数据"""
        meta_path = os.path.join(self.OUTPUT_DIR, "books_meta.json")
        try:
            data = [b.to_dict() for b in self._books.values()]
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save books: {e}")

    # ─── Story Parsing ──────────────────────────────────────────────────────

    def _parse_story_to_pages(self, story: str, num_pages: int) -> List[str]:
        """将故事段落拆分为逐页文案"""
        # Split by sentence separators
        import re
        sentences = re.split(r'[。.!！?\n]+', story)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

        if len(sentences) <= num_pages:
            # Pad with empty if not enough sentences
            while len(sentences) < num_pages:
                sentences.append("")
            return sentences[:num_pages]

        # Evenly distribute sentences into pages
        result = []
        per_page = len(sentences) / num_pages
        for i in range(num_pages):
            start = int(i * per_page)
            end = int((i + 1) * per_page) if i < num_pages - 1 else len(sentences)
            page_text = "。".join(sentences[start:end]) + "。"
            result.append(page_text)
        return result

    # ─── LLM Illustration Description Generation ────────────────────────────

    async def _generate_illustration_prompt(
        self, page_text: str, page_num: int, total_pages: int,
        book_title: str, style: str, audience: str
    ) -> str:
        """调用ModelGateway生成单页插图描述提示词"""
        try:
            from engines.model_gateway import get_gateway

            if style == "storybook":
                style_desc = "温馨可爱的儿童故事绘本风格，色彩明亮，线条柔和，适合小朋友阅读"
            elif style == "watercolor":
                style_desc = "柔和的水彩画风格，色彩清透，笔触自然，有手绘质感"
            elif style == "cartoon":
                style_desc = "活泼的卡通风格，夸张的表情和动作，鲜艳的色彩"
            elif style == "realistic":
                style_desc = "写实绘画风格，细节丰富，光影真实，画面精致"
            elif style == "anime":
                style_desc = "日系动漫风格，细腻的人物表情，清新的色彩搭配，电影感构图"
            else:
                style_desc = "温馨可爱的儿童绘本风格"

            prompt = f"""你是一位专业的绘本插画师。请为以下绘本页面生成一个详细的插图描述(英文prompt)，用于AI图片生成。

绘本信息:
- 书名: {book_title}
- 风格: {style_desc}
- 目标读者: {audience}岁
- 当前页: 第{page_num}/{total_pages}页

页面文案:
{page_text}

请生成一个英文插图描述(prompt)，要求：
1. 描述画面主体、动作、场景、光线
2. 符合{style_desc}
3. 添加画质关键词(如: children's book illustration, high quality, vibrant colors, cute style)
4. 只输出prompt本身，不要解释
5. 长度控制在100词以内"""

            gateway = get_gateway()
            messages = [{"role": "user", "content": prompt}]
            response = await gateway.chat(messages, model="auto", temperature=0.7, max_tokens=300)

            if response.success:
                return response.content.strip()
            else:
                logger.warning(f"LLM prompt generation failed: {response.error}")
                # Fallback: build a simple prompt
                return self._build_simple_prompt(page_text, style_desc)
        except Exception as e:
            logger.error(f"LLM prompt generation error: {e}")
            return self._build_simple_prompt(page_text, style_desc)

    def _build_simple_prompt(self, page_text: str, style_desc: str) -> str:
        """Fallback: 简单构造插图prompt"""
        return f"children's book illustration, {style_desc}, {page_text[:80]}, high quality, vibrant colors, cute style"

    # ─── Image Generation ───────────────────────────────────────────────────

    async def _generate_image(self, prompt: str, page_num: int, book_id: str) -> Dict[str, str]:
        """调用图片生成API，返回 {url, path, base64}"""
        image_dir = os.path.join(self.OUTPUT_DIR, "images", book_id)
        os.makedirs(image_dir, exist_ok=True)

        output_path = os.path.join(image_dir, f"page_{page_num:03d}.png")

        try:
            if self.IMAGE_API_TYPE == "sdwebui":
                result = await self._call_sdwebui(prompt, output_path)
            elif self.IMAGE_API_TYPE == "comfyui":
                result = await self._call_comfyui(prompt, output_path)
            elif self.IMAGE_API_TYPE == "openai":
                result = await self._call_openai_image(prompt, output_path)
            else:
                result = await self._call_generic_api(prompt, output_path)
            return result
        except Exception as e:
            logger.error(f"Image generation failed for page {page_num}: {e}")
            return {"url": "", "path": "", "base64": "", "error": str(e)}

    async def _call_sdwebui(self, prompt: str, output_path: str) -> Dict[str, str]:
        """Stable Diffusion WebUI API (txt2img)"""
        payload = {
            "prompt": prompt + ", children's book illustration, high quality, vibrant colors",
            "negative_prompt": "ugly, deformed, blurry, low quality, text, watermark",
            "steps": 20,
            "width": 768,
            "height": 1024,
            "cfg_scale": 7,
            "sampler_name": "Euler a",
            "seed": -1,
        }
        headers = {"Content-Type": "application/json"}
        if self.IMAGE_API_KEY:
            headers["Authorization"] = f"Bearer {self.IMAGE_API_KEY}"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.IMAGE_API_URL.rstrip('/')}/txt2img",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                images = data.get("images", [])
                if images:
                    img_base64 = images[0]
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(img_base64))
                    return {
                        "url": f"/api/book/images/{os.path.basename(output_path)}",
                        "path": output_path,
                        "base64": img_base64,
                    }
            raise ValueError(f"SD WebUI API error: {resp.status_code} {resp.text[:200]}")

    async def _call_comfyui(self, prompt: str, output_path: str) -> Dict[str, str]:
        """ComfyUI API — simplified workflow"""
        raise NotImplementedError("ComfyUI image generation not yet implemented")

    async def _call_openai_image(self, prompt: str, output_path: str) -> Dict[str, str]:
        """OpenAI DALL-E API"""
        headers = {"Content-Type": "application/json"}
        if self.IMAGE_API_KEY:
            headers["Authorization"] = f"Bearer {self.IMAGE_API_KEY}"

        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "size": "1024x1024",
            "quality": "standard",
            "n": 1,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.IMAGE_API_URL.rstrip("/"),
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                img_url = data.get("data", [{}])[0].get("url", "")
                if img_url:
                    # Download the image
                    img_resp = await client.get(img_url)
                    if img_resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(img_resp.content)
                        with open(output_path, "rb") as f:
                            img_base64 = base64.b64encode(f.read()).decode()
                        return {"url": img_url, "path": output_path, "base64": img_base64}
            raise ValueError(f"OpenAI Image API error: {resp.status_code} {resp.text[:200]}")

    async def _call_generic_api(self, prompt: str, output_path: str) -> Dict[str, str]:
        """Generic image generation API — POST {prompt} → returns {url, base64}"""
        headers = {"Content-Type": "application/json"}
        if self.IMAGE_API_KEY:
            headers["Authorization"] = f"Bearer {self.IMAGE_API_KEY}"

        payload = {"prompt": prompt, "width": 768, "height": 1024}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.IMAGE_API_URL.rstrip("/"),
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                img_base64 = data.get("base64") or data.get("image") or ""
                img_url = data.get("url", "")
                if img_base64:
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(img_base64))
                return {"url": img_url, "path": output_path, "base64": img_base64}
            raise ValueError(f"Image API error: {resp.status_code} {resp.text[:200]}")

    # ─── Main Pipeline ──────────────────────────────────────────────────────

    async def generate_book(
        self,
        title: str,
        story: str,
        style: str = "storybook",
        num_pages: int = 8,
        audience: str = "3-6",
        generate_images: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> Book:
        """
        一键生成绘本。

        Args:
            title: 书名
            story: 故事文本
            style: 画风 (storybook/watercolor/cartoon/realistic/anime)
            num_pages: 页数
            audience: 目标读者年龄
            generate_images: 是否生成插图
            progress_callback: async callback(current_step, total, message)

        Returns:
            Book 对象
        """
        book_id = f"book_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        book = Book(
            id=book_id,
            title=title,
            story=story,
            style=style,
            audience=audience,
            pages=[],
            status="generating",
            created_at=now,
            updated_at=now,
        )
        self._books[book_id] = book

        # Step 1: Parse story into pages
        page_texts = self._parse_story_to_pages(story, num_pages)
        total_pages = len(page_texts)

        if progress_callback:
            await progress_callback(1, total_pages + 2, f"📝 解析故事，共{total_pages}页")

        # Step 2: Generate illustration prompts via LLM
        for i, page_text in enumerate(page_texts):
            page_num = i + 1
            illustration_prompt = await self._generate_illustration_prompt(
                page_text, page_num, total_pages, title, style, audience
            )
            book.pages.append(BookPage(
                page_num=page_num,
                text=page_text if page_text else f"第{page_num}页",
                illustration_prompt=illustration_prompt,
            ))
            if progress_callback:
                await progress_callback(1 + i, total_pages + 2,
                                        f"🎨 生成第{page_num}/{total_pages}页插图描述")

        # Step 3: Generate images
        if generate_images:
            for i, page in enumerate(book.pages):
                image_result = await self._generate_image(
                    page.illustration_prompt, page.page_num, book_id
                )
                page.image_url = image_result.get("url", "")
                page.image_path = image_result.get("path", "")
                page.image_base64 = image_result.get("base64", "")
                if progress_callback:
                    await progress_callback(total_pages + i, total_pages * 2 + 2,
                                            f"🖼️ 渲染第{page.page_num}/{total_pages}页插图")
            book.status = "illustrations_ready"
        else:
            book.status = "complete"

        if progress_callback:
            await progress_callback(total_pages * 2 + 2, total_pages * 2 + 2,
                                    f"📖 绘本《{title}》生成完成!")

        book.updated_at = datetime.now().isoformat()
        self._save_books()
        return book

    # ─── Query ──────────────────────────────────────────────────────────────

    def get_book(self, book_id: str) -> Optional[Book]:
        """获取绘本"""
        return self._books.get(book_id)

    def list_books(self) -> List[Book]:
        """获取所有绘本列表"""
        return sorted(self._books.values(), key=lambda b: b.created_at, reverse=True)

    def delete_book(self, book_id: str) -> bool:
        """删除绘本"""
        if book_id in self._books:
            del self._books[book_id]
            self._save_books()
            # Clean up images
            import shutil
            img_dir = os.path.join(self.OUTPUT_DIR, "images", book_id)
            if os.path.exists(img_dir):
                shutil.rmtree(img_dir, ignore_errors=True)
            return True
        return False

    # ─── Export ─────────────────────────────────────────────────────────────

    def render_html(self, book_id: str) -> Optional[str]:
        """将绘本渲染为HTML"""
        book = self._books.get(book_id)
        if not book:
            return None

        style_bg = {
            "storybook": "#FFF8E7",
            "watercolor": "#F0F4FF",
            "cartoon": "#FFFDF0",
            "realistic": "#F5F0EB",
            "anime": "#FFF0F5",
        }.get(book.style, "#FFF8E7")

        pages_html = []
        for page in book.pages:
            img_tag = ""
            if page.image_base64:
                img_tag = f'<img src="data:image/png;base64,{page.image_base64}" style="max-width:100%;max-height:60vh;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.15)">'
            elif page.image_url:
                img_tag = f'<img src="{page.image_url}" style="max-width:100%;max-height:60vh;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.15)">'
            else:
                # Placeholder if no image
                colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F"]
                bg = colors[(page.page_num - 1) % len(colors)]
                img_tag = f'<div style="width:600px;height:400px;background:{bg};border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:80px;opacity:0.6">📖</div>'

            pages_html.append(f"""
            <div class="page" style="page-break-after:always;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:40px">
                {img_tag}
                <div style="margin-top:24px;max-width:600px;text-align:center;font-size:20px;line-height:1.6;color:#444">
                    {page.text}
                </div>
                <div style="margin-top:16px;font-size:14px;color:#999">— {page.page_num} —</div>
            </div>
            """)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{book.title} — IMDF绘本工坊</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Noto Serif SC', 'SimSun', serif; background: {style_bg}; }}
    .cover {{ display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 40px; }}
    .cover h1 {{ font-size: 48px; color: #333; margin-bottom: 16px; }}
    .cover .subtitle {{ font-size: 18px; color: #888; }}
    @media print {{ .page {{ page-break-after: always; }} }}
</style>
</head>
<body>
    <div class="cover">
        <div style="font-size:100px;margin-bottom:24px">📚</div>
        <h1>{book.title}</h1>
        <div class="subtitle">风格: {book.style} · 共{len(book.pages)}页 · IMDF绘本工坊</div>
        <div class="subtitle" style="margin-top:8px">{book.created_at[:10]}</div>
    </div>
    {''.join(pages_html)}
</body>
</html>"""

    def render_html_path(self, book_id: str) -> Optional[str]:
        """渲染HTML并保存到文件，返回路径"""
        html = self.render_html(book_id)
        if not html:
            return None
        output_path = os.path.join(self.OUTPUT_DIR, f"{book_id}.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

    def get_image_path(self, book_id: str, filename: str) -> Optional[str]:
        """获取绘本图片路径"""
        img_path = os.path.join(self.OUTPUT_DIR, "images", book_id, filename)
        if os.path.exists(img_path):
            return img_path
        return None


# ============================================================================
# Singleton
# ============================================================================

_engine: Optional[BookEngine] = None


def get_book_engine() -> BookEngine:
    """获取或创建全局BookEngine单例"""
    global _engine
    if _engine is None:
        _engine = BookEngine()
    return _engine
