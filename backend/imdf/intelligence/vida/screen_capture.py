"""P19-V53: Vida screen_capture — 多平台屏幕抓拍.

V5 第 26 章 § 26.2 屏幕抓拍:
  * Windows  — win32gui GetForegroundWindow
  * macOS    — pyautogui + AppKit
  * Linux    — scrot subprocess
  * Mock     — deterministic fake ScreenData (测试用)

所有 platform-specific 路径都用 try/except 软降级到 mock; 测试不依赖
真实的桌面环境。
"""
from __future__ import annotations

import asyncio
import logging
import platform as _platform_mod
import sys
from typing import Any, Dict, Optional

from .schemas import ScreenData

logger = logging.getLogger(__name__)


class ScreenCapture:
    """屏幕抓拍 — 跨平台抽象.

    用法:
        cap = ScreenCapture(mode="mock")  # 测试
        cap = ScreenCapture()             # 真实抓拍 (含 mock 降级)
        data = await cap.capture()
    """

    MOCK_IMG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
    )

    def __init__(self, mode: str = "auto", *, mock_app: str = "vscode",
                 mock_window: str = "main.py - nanobot-factory") -> None:
        """mode: auto | mock | real.

        * auto: 尝试真实抓拍,失败则降级到 mock
        * mock: 直接返回 mock ScreenData (测试用)
        * real: 强制真实抓拍 (失败抛 RuntimeError)
        """
        self.mode = mode
        self.mock_app = mock_app
        self.mock_window = mock_window
        self._capture_count = 0

    async def capture(self) -> ScreenData:
        """抓拍当前屏幕 — auto 模式会按平台分发."""
        self._capture_count += 1
        platform_name = sys.platform  # "win32" / "darwin" / "linux"

        if self.mode == "mock":
            return self._make_mock(platform_name)

        if self.mode == "real":
            if platform_name == "win32":
                return await self._capture_windows()
            if platform_name == "darwin":
                return await self._capture_macos()
            return await self._capture_linux()

        # auto: try real, fallback to mock
        try:
            if platform_name == "win32":
                return await self._capture_windows()
            if platform_name == "darwin":
                return await self._capture_macos()
            return await self._capture_linux()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vida screen capture real failed (%s); using mock", exc)
            return self._make_mock(platform_name)

    # ── Platform-specific ─────────────────────────────────────────────
    async def _capture_windows(self) -> ScreenData:
        """Windows — win32gui GetForegroundWindow."""
        # import 在函数内 (避免 import-time hard dep on pywin32)
        try:
            import win32gui  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(f"pywin32 not available: {exc}") from exc

        # win32gui 是阻塞同步 API — 用 to_thread 包装
        def _get_focus() -> Dict[str, Any]:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return {"hwnd": int(hwnd), "title": title}

        info = await asyncio.to_thread(_get_focus)
        title = info["title"] or "Unknown"
        return ScreenData(
            image=b"",
            image_b64=self.MOCK_IMG_B64,
            width=1920,
            height=1080,
            active_app=title.split(" - ")[0] if " - " in title else title,
            active_window_title=title,
            platform="windows",
            extra={"hwnd": info["hwnd"]},
        )

    async def _capture_macos(self) -> ScreenData:
        """macOS — pyautogui + AppKit."""
        try:
            import pyautogui  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(f"pyautogui not available: {exc}") from exc

        def _snap() -> Dict[str, Any]:
            screenshot = pyautogui.screenshot()
            try:
                from AppKit import NSWorkspace  # type: ignore[import-not-found]
                active = NSWorkspace.sharedWorkspace().activeApplication()
                app_name = str(active.get("NSApplicationName") or "Unknown")
            except Exception:  # noqa: BLE001
                app_name = "Unknown"
            return {
                "image": screenshot.tobytes() if hasattr(screenshot, "tobytes") else b"",
                "size": screenshot.size,
                "app": app_name,
            }

        info = await asyncio.to_thread(_snap)
        return ScreenData(
            image=info["image"],
            image_b64="",
            width=int(getattr(info["size"], "width", 1920) if hasattr(info["size"], "width") else 1920),
            height=int(getattr(info["size"], "height", 1080) if hasattr(info["size"], "height") else 1080),
            active_app=str(info["app"]),
            active_window_title=str(info["app"]),
            platform="macos",
        )

    async def _capture_linux(self) -> ScreenData:
        """Linux — subprocess scrot (no in-process Python lib)."""
        import shutil
        import tempfile
        import os

        if not shutil.which("scrot"):
            raise RuntimeError("scrot not on PATH")

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            proc = await asyncio.create_subprocess_exec(
                "scrot", tmp.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            with open(tmp.name, "rb") as f:
                img_bytes = f.read()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        return ScreenData(
            image=img_bytes,
            image_b64="",
            width=1920,
            height=1080,
            active_app="linux-desktop",
            active_window_title="linux-desktop",
            platform="linux",
        )

    # ── Mock helper ─────────────────────────────────────────────────
    def _make_mock(self, platform_name: str = "mock") -> ScreenData:
        """生成 deterministic mock ScreenData — 用于测试 + 真实抓拍失败降级."""
        import uuid

        return ScreenData(
            screen_id=f"sc_{uuid.uuid4().hex[:8]}",
            image=b"",
            image_b64=self.MOCK_IMG_B64,
            width=1920,
            height=1080,
            active_app=self.mock_app,
            active_window_title=f"{self.mock_app} — {self.mock_window}",
            platform=f"mock-{platform_name}",
            extra={"capture_count": self._capture_count},
        )

    # ── Test helpers ────────────────────────────────────────────────
    def set_mock_target(self, app: str, window: str) -> None:
        """覆盖 mock 输出 (test-only)."""
        self.mock_app = app
        self.mock_window = window


__all__ = ["ScreenCapture"]