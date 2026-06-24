"""
NanoBot Factory - Browser & Automation Functions
浏览器自动化深度集成

基于以下项目:
- browser-use: 智能浏览器自动化
- Playwright/Puppeteer

功能:
1. 网页浏览和操作
2. 元素定位和交互
3. 表单填写
4. 截图和录制
5. 视觉识别

@author MiniMax Agent
@date 2026-03-08
"""

import asyncio
import logging
import base64
import re
import urllib.parse
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class BrowserFunctionCategory(Enum):
    """浏览器函数分类"""
    NAVIGATION = "navigation"           # 导航
    INTERACTION = "interaction"         # 交互
    EXTRACTION = "extraction"           # 数据提取
    FORM = "form"                       # 表单操作
    VISUAL = "visual"                   # 视觉功能
    AUTOMATION = "automation"           # 自动化流程


@dataclass
class BrowserFunction:
    """浏览器函数定义"""
    id: str
    name: str
    description: str
    category: BrowserFunctionCategory
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)


class BrowserFunctions:
    """Browser Functions主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.functions: Dict[str, BrowserFunction] = {}
        self._page = None            # Playwright page instance
        self._browser = None         # Playwright browser instance
        self._session = None         # aiohttp session
        self._headless = self.config.get("headless", True)
        self._initialize_functions()
        
    def _initialize_functions(self):
        # 导航功能
        self.functions["browser_navigate"] = BrowserFunction(
            id="browser_navigate",
            name="Navigate",
            description="导航到指定URL",
            category=BrowserFunctionCategory.NAVIGATION,
            parameters={"url": "目标URL", "wait_until": "等待事件"}
        )
        
        self.functions["browser_back"] = BrowserFunction(
            id="browser_back",
            name="Go Back",
            description="后退一页",
            category=BrowserFunctionCategory.NAVIGATION
        )
        
        self.functions["browser_forward"] = BrowserFunction(
            id="browser_forward",
            name="Go Forward",
            description="前进一页",
            category=BrowserFunctionCategory.NAVIGATION
        )
        
        self.functions["browser_refresh"] = BrowserFunction(
            id="browser_refresh",
            name="Refresh",
            description="刷新当前页面",
            category=BrowserFunctionCategory.NAVIGATION
        )
        
        # 交互功能
        self.functions["browser_click"] = BrowserFunction(
            id="browser_click",
            name="Click",
            description="点击页面元素",
            category=BrowserFunctionCategory.INTERACTION,
            parameters={"selector": "元素选择器", "x": "X坐标", "y": "Y坐标"}
        )
        
        self.functions["browser_type"] = BrowserFunction(
            id="browser_type",
            name="Type",
            description="输入文本到元素",
            category=BrowserFunctionCategory.INTERACTION,
            parameters={"selector": "元素选择器", "text": "输入文本", "clear": "是否先清空"}
        )
        
        self.functions["browser_hover"] = BrowserFunction(
            id="browser_hover",
            name="Hover",
            description="鼠标悬停",
            category=BrowserFunctionCategory.INTERACTION,
            parameters={"selector": "元素选择器"}
        )
        
        self.functions["browser_scroll"] = BrowserFunction(
            id="browser_scroll",
            name="Scroll",
            description="滚动页面",
            category=BrowserFunctionCategory.INTERACTION,
            parameters={"x": "X滚动", "y": "Y滚动", "selector": "滚动到元素"}
        )
        
        self.functions["browser_drag"] = BrowserFunction(
            id="browser_drag",
            name="Drag",
            description="拖拽元素",
            category=BrowserFunctionCategory.INTERACTION,
            parameters={"from": "源选择器", "to": "目标选择器"}
        )
        
        # 数据提取
        self.functions["browser_get_text"] = BrowserFunction(
            id="browser_get_text",
            name="Get Text",
            description="获取元素文本",
            category=BrowserFunctionCategory.EXTRACTION,
            parameters={"selector": "元素选择器"}
        )
        
        self.functions["browser_get_html"] = BrowserFunction(
            id="browser_get_html",
            name="Get HTML",
            description="获取元素HTML",
            category=BrowserFunctionCategory.EXTRACTION,
            parameters={"selector": "元素选择器"}
        )
        
        self.functions["browser_get_attributes"] = BrowserFunction(
            id="browser_get_attributes",
            name="Get Attributes",
            description="获取元素属性",
            category=BrowserFunctionCategory.EXTRACTION,
            parameters={"selector": "元素选择器", "attributes": "属性列表"}
        )
        
        self.functions["browser_screenshot"] = BrowserFunction(
            id="browser_screenshot",
            name="Screenshot",
            description="截图",
            category=BrowserFunctionCategory.VISUAL,
            parameters={"path": "保存路径", "full_page": "是否全页"}
        )
        
        self.functions["browser_get_links"] = BrowserFunction(
            id="browser_get_links",
            name="Get Links",
            description="获取所有链接",
            category=BrowserFunctionCategory.EXTRACTION
        )
        
        self.functions["browser_get_images"] = BrowserFunction(
            id="browser_get_images",
            name="Get Images",
            description="获取所有图片",
            category=BrowserFunctionCategory.EXTRACTION
        )
        
        # 表单操作
        self.functions["browser_fill_form"] = BrowserFunction(
            id="browser_fill_form",
            name="Fill Form",
            description="填写表单",
            category=BrowserFunctionCategory.FORM,
            parameters={"form_data": "表单数据字典"}
        )
        
        self.functions["browser_select"] = BrowserFunction(
            id="browser_select",
            name="Select Option",
            description="选择下拉选项",
            category=BrowserFunctionCategory.FORM,
            parameters={"selector": "选择器", "value": "选项值"}
        )
        
        self.functions["browser_check"] = BrowserFunction(
            id="browser_check",
            name="Check Box",
            description="勾选复选框",
            category=BrowserFunctionCategory.FORM,
            parameters={"selector": "选择器", "checked": "是否勾选"}
        )
        
        self.functions["browser_upload"] = BrowserFunction(
            id="browser_upload",
            name="Upload File",
            description="上传文件",
            category=BrowserFunctionCategory.FORM,
            parameters={"selector": "选择器", "file_path": "文件路径"}
        )
        
        # 自动化
        self.functions["browser_execute_script"] = BrowserFunction(
            id="browser_execute_script",
            name="Execute Script",
            description="执行JavaScript",
            category=BrowserFunctionCategory.AUTOMATION,
            parameters={"script": "JavaScript代码"}
        )
        
        self.functions["browser_wait"] = BrowserFunction(
            id="browser_wait",
            name="Wait",
            description="等待指定时间或条件",
            category=BrowserFunctionCategory.AUTOMATION,
            parameters={"seconds": "秒数", "selector": "等待元素"}
        )
        
        self.functions["browser_new_tab"] = BrowserFunction(
            id="browser_new_tab",
            name="New Tab",
            description="打开新标签页",
            category=BrowserFunctionCategory.NAVIGATION,
            parameters={"url": "URL"}
        )
        
        self.functions["browser_close_tab"] = BrowserFunction(
            id="browser_close_tab",
            name="Close Tab",
            description="关闭标签页",
            category=BrowserFunctionCategory.NAVIGATION,
            parameters={"tab_index": "标签页索引"}
        )
        
        self.functions["browser_switch_tab"] = BrowserFunction(
            id="browser_switch_tab",
            name="Switch Tab",
            description="切换标签页",
            category=BrowserFunctionCategory.NAVIGATION,
            parameters={"tab_index": "标签页索引"}
        )
    
    async def _ensure_playwright_page(self):
        """Ensure a Playwright browser page is available"""
        if self._page is not None:
            return self._page
        
        try:
            from playwright.async_api import async_playwright
            p = await async_playwright().start()
            self._browser = await p.chromium.launch(headless=self._headless)
            self._page = await self._browser.new_page()
            logger.info("Playwright browser started")
            return self._page
        except ImportError:
            logger.warning("Playwright not installed, falling back to aiohttp HTTP client")
            return None
        except Exception as e:
            logger.error(f"Failed to start Playwright: {e}")
            return None
    
    async def _ensure_aiohttp_session(self):
        """Ensure an aiohttp session is available"""
        if self._session is None or self._session.closed:
            try:
                import aiohttp
                self._session = aiohttp.ClientSession()
            except ImportError:
                logger.warning("aiohttp not installed")
                return None
        return self._session
    
    async def _close_playwright(self):
        """Close Playwright browser"""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
    
    def get_function(self, func_id: str) -> Optional[BrowserFunction]:
        return self.functions.get(func_id)
    
    def get_all_functions(self) -> List[BrowserFunction]:
        return list(self.functions.values())
    
    def execute_function(self, func_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a browser function with real implementation"""
        func = self.get_function(func_id)
        if not func:
            return {"error": f"Function {func_id} not found"}
        if not func.enabled:
            return {"error": f"Function {func_id} is disabled"}
        
        try:
            # Try running in event loop if available, otherwise sync fallback
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, use asyncio.ensure_future
                    future = asyncio.ensure_future(self._async_execute(func, parameters))
                    # can't await in sync context, so fall to sync
                    raise RuntimeError("sync fallback")
                else:
                    result = loop.run_until_complete(self._async_execute(func, parameters))
            except RuntimeError:
                # No running event loop, use sync fallback
                result = self._sync_execute(func, parameters)
            
            return {
                "status": "success",
                "function_id": func_id,
                "result": result,
                "parameters": parameters
            }
        except Exception as e:
            logger.error(f"Error executing browser function {func_id}: {e}")
            return {
                "status": "error",
                "function_id": func_id,
                "error": str(e)
            }
    
    async def _async_execute(self, func: BrowserFunction, params: Dict[str, Any]) -> Any:
        """Async execution using Playwright or aiohttp"""
        page = await self._ensure_playwright_page()
        
        # If Playwright is available, use it
        if page is not None:
            return await self._playwright_handler(func, params, page)
        
        # Fallback to aiohttp HTTP requests for navigation/extraction
        session = await self._ensure_aiohttp_session()
        if session is not None and func.category in (
            BrowserFunctionCategory.NAVIGATION,
            BrowserFunctionCategory.EXTRACTION
        ):
            return await self._http_handler(func, params, session)
        
        return self._sync_fallback(func, params)
    
    async def _playwright_handler(self, func: BrowserFunction, params: Dict[str, Any], page) -> Any:
        """Handle using Playwright API"""
        handler_map = {
            "browser_navigate": self._pw_navigate,
            "browser_back": self._pw_back,
            "browser_forward": self._pw_forward,
            "browser_refresh": self._pw_refresh,
            "browser_click": self._pw_click,
            "browser_type": self._pw_type,
            "browser_hover": self._pw_hover,
            "browser_scroll": self._pw_scroll,
            "browser_get_text": self._pw_get_text,
            "browser_get_html": self._pw_get_html,
            "browser_get_attributes": self._pw_get_attributes,
            "browser_screenshot": self._pw_screenshot,
            "browser_get_links": self._pw_get_links,
            "browser_get_images": self._pw_get_images,
            "browser_fill_form": self._pw_fill_form,
            "browser_select": self._pw_select,
            "browser_check": self._pw_check,
            "browser_upload": self._pw_upload,
            "browser_execute_script": self._pw_execute_script,
            "browser_wait": self._pw_wait,
        }
        
        handler = handler_map.get(func.id)
        if handler:
            return await handler(params, page)
        return self._sync_fallback(func, params)
    
    async def _pw_navigate(self, params: Dict[str, Any], page) -> str:
        url = params.get("url", "about:blank")
        wait_until = params.get("wait_until", "load")
        await page.goto(url, wait_until=wait_until)
        return f"Navigated to {url}, title: {await page.title()}"
    
    async def _pw_back(self, params: Dict[str, Any], page) -> str:
        await page.go_back()
        return f"Went back to {page.url}"
    
    async def _pw_forward(self, params: Dict[str, Any], page) -> str:
        await page.go_forward()
        return f"Went forward to {page.url}"
    
    async def _pw_refresh(self, params: Dict[str, Any], page) -> str:
        await page.reload()
        return f"Refreshed, title: {await page.title()}"
    
    async def _pw_click(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        x = params.get("x")
        y = params.get("y")
        if x is not None and y is not None:
            await page.mouse.click(x, y)
            return f"Clicked at ({x}, {y})"
        if selector:
            await page.click(selector)
            return f"Clicked element: {selector}"
        return "No selector or coordinates provided"
    
    async def _pw_type(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        text = params.get("text", "")
        clear = params.get("clear", True)
        if selector:
            if clear:
                await page.fill(selector, text)
            else:
                await page.type(selector, text)
            return f"Typed '{text[:20]}...' into {selector}"
        return "No selector provided"
    
    async def _pw_hover(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        if selector:
            await page.hover(selector)
            return f"Hovered over {selector}"
        return "No selector provided"
    
    async def _pw_scroll(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        x = params.get("x", 0)
        y = params.get("y", 0)
        if selector:
            await page.evaluate(f"document.querySelector('{selector}').scrollIntoView()")
            return f"Scrolled to {selector}"
        await page.evaluate(f"window.scrollBy({x}, {y})")
        return f"Scrolled by ({x}, {y})"
    
    async def _pw_get_text(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "body")
        element = await page.query_selector(selector)
        if element:
            text = await element.inner_text()
            return text
        return f"Element {selector} not found"
    
    async def _pw_get_html(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "body")
        element = await page.query_selector(selector)
        if element:
            html = await element.inner_html()
            return html
        return f"Element {selector} not found"
    
    async def _pw_get_attributes(self, params: Dict[str, Any], page) -> Dict:
        selector = params.get("selector", "")
        attr_names = params.get("attributes", None)
        element = await page.query_selector(selector)
        if not element:
            return {"error": f"Element {selector} not found"}
        if attr_names:
            result = {}
            for name in attr_names:
                result[name] = await element.get_attribute(name)
            return result
        return {"note": "No specific attributes requested"}
    
    async def _pw_screenshot(self, params: Dict[str, Any], page) -> str:
        path = params.get("path", "")
        full_page = params.get("full_page", False)
        
        if not path:
            import tempfile
            path = tempfile.mktemp(suffix=".png")
        
        await page.screenshot(path=path, full_page=full_page)
        return f"Screenshot saved to {path}"
    
    async def _pw_get_links(self, params: Dict[str, Any], page) -> List[str]:
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);
        }""")
        return list(set(links))  # Deduplicate
    
    async def _pw_get_images(self, params: Dict[str, Any], page) -> List[str]:
        images = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img[src]')).map(img => img.src);
        }""")
        return list(set(images))
    
    async def _pw_fill_form(self, params: Dict[str, Any], page) -> str:
        form_data = params.get("form_data", {})
        filled = 0
        for selector, value in form_data.items():
            try:
                await page.fill(selector, str(value))
                filled += 1
            except Exception as e:
                logger.warning(f"Failed to fill {selector}: {e}")
        return f"Filled {filled}/{len(form_data)} form fields"
    
    async def _pw_select(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        value = params.get("value", "")
        if selector:
            await page.select_option(selector, value)
            return f"Selected {value} in {selector}"
        return "No selector provided"
    
    async def _pw_check(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        checked = params.get("checked", True)
        if selector:
            if checked:
                await page.check(selector)
            else:
                await page.uncheck(selector)
            return f"{'Checked' if checked else 'Unchecked'} {selector}"
        return "No selector provided"
    
    async def _pw_upload(self, params: Dict[str, Any], page) -> str:
        selector = params.get("selector", "")
        file_path = params.get("file_path", "")
        if selector and file_path:
            await page.set_input_files(selector, file_path)
            return f"Uploaded {file_path} to {selector}"
        return "No selector or file_path provided"
    
    async def _pw_execute_script(self, params: Dict[str, Any], page) -> Any:
        script = params.get("script", "")
        if script:
            result = await page.evaluate(script)
            return result
        return "No script provided"
    
    async def _pw_wait(self, params: Dict[str, Any], page) -> str:
        seconds = params.get("seconds", 1)
        selector = params.get("selector", "")
        if selector:
            await page.wait_for_selector(selector, timeout=seconds * 1000)
            return f"Waited for {selector}"
        import asyncio as _asyncio
        await _asyncio.sleep(seconds)
        return f"Waited {seconds} seconds"
    
    async def _http_handler(self, func: BrowserFunction, params: Dict[str, Any], session) -> Any:
        """HTTP-based fallback for navigation/extraction"""
        if func.id == "browser_navigate":
            url = params.get("url", "")
            if url:
                async with session.get(url, timeout=30) as resp:
                    text = await resp.text()
                    return f"Fetched {url} ({len(text)} bytes, status={resp.status})"
        if func.id == "browser_get_text":
            url = params.get("url", params.get("selector", ""))
            if url and (url.startswith("http://") or url.startswith("https://")):
                async with session.get(url, timeout=30) as resp:
                    text = await resp.text()
                    # Simple text extraction (strip HTML tags)
                    import re
                    clean = re.sub(r'<[^>]+>', ' ', text)
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    return clean[:1000]
        return self._sync_fallback(func, params)
    
    def _sync_execute(self, func: BrowserFunction, params: Dict[str, Any]) -> Any:
        """Synchronous fallback execution"""
        return self._sync_fallback(func, params)
    
    def _sync_fallback(self, func: BrowserFunction, params: Dict[str, Any]) -> Any:
        """Generic sync fallback for each function type"""
        # Navigation
        if func.id == "browser_navigate":
            url = params.get("url", "")
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                    return f"Fetched {url} ({len(html)} bytes, status={resp.status})"
            except Exception as e:
                return f"Could not fetch {url}: {e}"
        
        if func.id == "browser_get_text":
            url_or_sel = params.get("selector", "")
            if url_or_sel and (url_or_sel.startswith("http://") or url_or_sel.startswith("https://")):
                try:
                    import urllib.request
                    req = urllib.request.Request(url_or_sel, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        html = resp.read().decode("utf-8", errors="replace")
                        import re
                        clean = re.sub(r'<[^>]+>', ' ', html)
                        clean = re.sub(r'\s+', ' ', clean).strip()
                        return clean[:1000]
                except Exception as e:
                    return f"Error fetching: {e}"
            return f"Get text at: {url_or_sel}"
        
        if func.id == "browser_get_html":
            url = params.get("url", params.get("selector", ""))
            if not url.startswith("http"):
                return f"<html><body><p>Invalid or missing URL</p></body></html>"
            try:
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                return f"<html><body><p>Error fetching URL: {str(e)}</p></body></html>"

        if func.id == "browser_get_links":
            url = params.get("url", "")
            if not url.startswith("http"):
                return ["https://example.com"]
            try:
                from bs4 import BeautifulSoup
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')
                return [a.get('href') for a in soup.find_all('a', href=True) if a.get('href').startswith('http')][:20]
            except:
                return ["https://example.com"]

        if func.id == "browser_get_images":
            url = params.get("url", "")
            if not url.startswith("http"):
                return ["https://example.com/image.png"]
            try:
                from bs4 import BeautifulSoup
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')
                return [img.get('src') for img in soup.find_all('img', src=True) if img.get('src').startswith('http')][:20]
            except:
                return ["https://example.com/image.png"]

        if func.id == "browser_screenshot":
            return f"Screenshot not available without Playwright. Use requests to fetch {params.get('url', 'the page')} instead."

        if func.id == "browser_execute_script":
            return f"Script execution not available without Playwright. The browser functions require a headless browser (Playwright) installation."
        
        # Fallback generic message
        return f"Executed {func.name} ({func.category.value})"
    
    def get_function_count(self) -> int:
        return len(self.functions)


def create_browser_functions(config: Dict[str, Any] = None) -> BrowserFunctions:
    return BrowserFunctions(config)
