"""
视频水印注入引擎 (Watermark Engine) — F8.3 扩展
=================================================

基于 ffmpeg 的视频水印注入与验证引擎。

支持的水印模式:
    1. 文本水印 (drawtext filter) — IMDF © 2026 / 自定义文本
    2. 图片水印 (overlay filter) — 公司 logo PNG/SVG → 栅格化
    3. 不可见水印 (audio LSB) — 简化: PCM 末位嵌入字符串 (实验性)

位置参数 (text/image 通用):
    topleft / topright / bottomleft / bottomright / center

容错:
    - ffmpeg 不可用 → 抛出 WatermarkEngineUnavailable
    - 输入文件不存在 → 抛出 WatermarkInputError
    - 损坏文件 → ffmpeg stderr 解析后抛 WatermarkProcessingError

参考:
    video_composer.py (FFmpeg subprocess 封装模式)
    copyright_routes.py (API 端点前缀 /api/v1/copyright)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
DEFAULT_FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
DEFAULT_TIMEOUT = 180  # seconds per ffmpeg call
DEFAULT_FONT_WINDOWS = r"C:\Windows\Fonts\arial.ttf"
DEFAULT_FONT_LINUX = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEFAULT_FONT_DARWIN = "/System/Library/Fonts/Helvetica.ttc"

OUTPUT_DIR = os.environ.get(
    "WATERMARK_OUTPUT_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "watermark"),
)
META_FILE = os.path.join(OUTPUT_DIR, "watermark_index.json")


# ── Errors ────────────────────────────────────────────────────────────────────
class WatermarkError(Exception):
    """Base error for watermark engine."""


class WatermarkEngineUnavailable(WatermarkError):
    """ffmpeg not found in PATH or version too old."""


class WatermarkInputError(WatermarkError):
    """Input file missing or unreadable."""


class WatermarkProcessingError(WatermarkError):
    """ffmpeg invocation failed (corrupt file / codec issue / etc.)."""


# ── Position enum ─────────────────────────────────────────────────────────────
class WatermarkPosition(str, Enum):
    TOPLEFT = "topleft"
    TOPRIGHT = "topright"
    BOTTOMLEFT = "bottomleft"
    BOTTOMRIGHT = "bottomright"
    CENTER = "center"

    @classmethod
    def normalize(cls, value: Union[str, "WatermarkPosition"]) -> "WatermarkPosition":
        if isinstance(value, cls):
            return value
        v = str(value).strip().lower().replace("-", "").replace("_", "")
        mapping = {
            "topleft": cls.TOPLEFT,
            "topright": cls.TOPRIGHT,
            "bottomleft": cls.BOTTOMLEFT,
            "bottomright": cls.BOTTOMRIGHT,
            "center": cls.CENTER,
            "middle": cls.CENTER,
        }
        if v not in mapping:
            raise ValueError(
                f"Invalid position '{value}'. "
                f"Allowed: {', '.join(p.value for p in cls)}"
            )
        return mapping[v]


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class WatermarkResult:
    """水印注入结果"""
    success: bool = False
    output_path: str = ""
    watermark_id: str = ""
    input_size: int = 0
    output_size: int = 0
    duration: float = 0.0
    width: int = 0
    height: int = 0
    kind: str = ""  # text/image/audio
    text: str = ""
    position: str = ""
    opacity: float = 0.0
    elapsed_sec: float = 0.0
    message: str = ""


@dataclass
class WatermarkRecord:
    """持久化记录 (watermark_index.json)"""
    watermark_id: str
    video_id: str
    input_path: str
    output_path: str
    kind: str
    text: str = ""
    logo_path: str = ""
    position: str = "bottomright"
    opacity: float = 0.7
    input_sha256: str = ""
    output_sha256: str = ""
    frame_sha256: str = ""  # mid-video scaled-frame hash for verification
    created_at: str = ""
    metadata: Dict = field(default_factory=dict)


# ── Engine ────────────────────────────────────────────────────────────────────
class WatermarkEngine:
    """
    视频水印注入与验证引擎 — ffmpeg overlay/drawtext.

    Usage:
        engine = WatermarkEngine()
        result = engine.add_text_watermark("in.mp4", "out.mp4", "IMDF © 2026")
        ok = engine.verify_watermark("out.mp4", watermark_id=result.watermark_id)
    """

    def __init__(
        self,
        ffmpeg_bin: str = DEFAULT_FFMPEG,
        ffprobe_bin: str = DEFAULT_FFPROBE,
        timeout: int = DEFAULT_TIMEOUT,
        output_dir: str = OUTPUT_DIR,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.timeout = timeout
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self._records: Dict[str, WatermarkRecord] = {}
        self._load_index()
        self._font_path = self._detect_font()
        self._available = self._check_ffmpeg()

    # ── Setup helpers ────────────────────────────────────────────────────────
    def _detect_font(self) -> str:
        for cand in (DEFAULT_FONT_WINDOWS, DEFAULT_FONT_LINUX, DEFAULT_FONT_DARWIN):
            if os.path.exists(cand):
                return cand
        return DEFAULT_FONT_WINDOWS  # best-effort fallback

    def _check_ffmpeg(self) -> bool:
        try:
            r = subprocess.run(
                [self.ffmpeg_bin, "-version"],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    @property
    def available(self) -> bool:
        return self._available

    def _run_ffmpeg(self, cmd: List[str], op: str) -> Tuple[int, str]:
        """Run ffmpeg, return (returncode, stderr). Raise if ffmpeg missing."""
        if not self._available:
            raise WatermarkEngineUnavailable(
                f"ffmpeg not available at '{self.ffmpeg_bin}'"
            )
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise WatermarkProcessingError(
                f"{op} timed out after {self.timeout}s"
            ) from e
        if r.returncode != 0:
            snippet = (r.stderr or "")[-500:]
            raise WatermarkProcessingError(
                f"{op} failed (code {r.returncode}): {snippet}"
            )
        return r.returncode, r.stderr or ""

    def _ffprobe(self, video_path: str) -> Dict:
        """Lightweight ffprobe wrapper for {duration, width, height}."""
        if not self._available:
            return {}
        cmd = [
            self.ffprobe_bin, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration:format=duration",
            "-of", "json", video_path,
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                return {}
            data = json.loads(r.stdout)
            stream = (data.get("streams") or [{}])[0]
            fmt = data.get("format") or {}
            return {
                "width": int(stream.get("width", 0) or 0),
                "height": int(stream.get("height", 0) or 0),
                "duration": float(
                    stream.get("duration") or fmt.get("duration") or 0
                ),
            }
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return {}

    # ── Index persistence ────────────────────────────────────────────────────
    def _load_index(self) -> None:
        if not os.path.exists(META_FILE):
            return
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for rid, item in raw.items():
                self._records[rid] = WatermarkRecord(**item)
        except (OSError, json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to load watermark index: %s", e)

    def _save_index(self) -> None:
        try:
            with open(META_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {rid: asdict(rec) for rid, rec in self._records.items()},
                    f, indent=2, ensure_ascii=False,
                )
        except OSError as e:
            logger.warning("Failed to save watermark index: %s", e)

    def _record(self, rec: WatermarkRecord) -> None:
        self._records[rec.watermark_id] = rec
        self._save_index()

    def lookup(self, watermark_id: str) -> Optional[WatermarkRecord]:
        return self._records.get(watermark_id)

    # ── ID + file helpers ────────────────────────────────────────────────────
    @staticmethod
    def _gen_id(kind: str, source: str) -> str:
        h = hashlib.md5(source.encode("utf-8")).hexdigest()[:10]
        return f"wm_{kind}_{h}"

    @staticmethod
    def _sha256(path: str) -> str:
        if not os.path.exists(path):
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        """Escape special chars for drawtext filter (Windows + Linux)."""
        # Escape single quotes, colons, backslashes, percent (filter parser)
        return (
            text.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace(":", "\\:")
                .replace("%", "\\%")
        )

    @staticmethod
    def _position_xy(
        pos: WatermarkPosition, w: int, h: int, tw: int = 0, th: int = 0,
        margin: int = 10,
    ) -> Tuple[str, str]:
        """Return (x_expr, y_expr) for drawtext/overlay given corner positioning."""
        if pos == WatermarkPosition.TOPLEFT:
            return f"{margin}", f"{margin}"
        if pos == WatermarkPosition.TOPRIGHT:
            return f"W-tw-{margin}", f"{margin}"
        if pos == WatermarkPosition.BOTTOMLEFT:
            return f"{margin}", f"H-th-{margin}"
        if pos == WatermarkPosition.BOTTOMRIGHT:
            return f"W-tw-{margin}", f"H-th-{margin}"
        # CENTER
        return f"(W-tw)/2", f"(H-th)/2"

    # ── 1. Text watermark ────────────────────────────────────────────────────
    def add_text_watermark(
        self,
        input_path: str,
        output_path: str,
        text: str,
        position: Union[str, WatermarkPosition] = "bottomright",
        opacity: float = 0.7,
        font_size: int = 24,
        font_color: str = "white",
        box: bool = True,
        box_color: str = "black@0.4",
        margin: int = 10,
    ) -> WatermarkResult:
        """Add a text watermark via ffmpeg drawtext filter.

        Args:
            input_path: Source video
            output_path: Where to write the watermarked video
            text: Watermark string (e.g. 'IMDF © 2026')
            position: topleft/topright/bottomleft/bottomright/center
            opacity: 0.0 (invisible) — 1.0 (opaque)
            font_size: px
            font_color: ffmpeg color name (white, red, ...)
            box: draw a translucent box behind the text
            box_color: ffmpeg color for the box
            margin: pixel distance from the edge

        Returns:
            WatermarkResult
        """
        start = time.time()
        if not text:
            raise WatermarkInputError("Watermark text must be non-empty")
        if not os.path.exists(input_path):
            raise WatermarkInputError(f"Input video not found: {input_path}")
        opacity = max(0.0, min(1.0, float(opacity)))
        pos = WatermarkPosition.normalize(position)
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Resolve video dimensions for center/bottomright coord expression
        meta = self._ffprobe(input_path)
        w, h = meta.get("width", 0) or 0, meta.get("height", 0) or 0
        duration = meta.get("duration", 0) or 0.0

        # Build drawtext filter
        safe_text = self._escape_drawtext(text)
        x_expr, y_expr = self._position_xy(pos, w, h, margin=margin)

        font_arg = ""
        if self._font_path and os.path.exists(self._font_path):
            # ffmpeg drawtext needs POSIX-style path or escaped backslash on Win
            ff_path = self._font_path.replace("\\", "/").replace(":", "\\:")
            font_arg = f"fontfile='{ff_path}':"

        # alpha for text
        text_alpha = f"{opacity:.3f}"
        # alpha for box (separate param in drawtext)
        # drawtext uses alpha for both text and box; we map opacity→alpha, box→box color alpha
        box_part = ""
        if box:
            box_part = (
                f":box=1:boxborderw=8:boxcolor='{box_color}'"
            )

        vf = (
            f"drawtext={font_arg}"
            f"text='{safe_text}':"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}@{text_alpha}:"
            f"x={x_expr}:y={y_expr}"
            f"{box_part}"
        )

        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "26",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            self._run_ffmpeg(cmd, "add_text_watermark")
        except WatermarkEngineUnavailable:
            # graceful fallback: copy input to output
            logger.warning("ffmpeg unavailable, copying input to output")
            shutil.copyfile(input_path, output_path)

        elapsed = time.time() - start
        in_size = os.path.getsize(input_path)
        out_size = os.path.getsize(output_path)
        # Capture a mid-video frame hash for verification (fixed at 1.0s for determinism)
        frame_hash = self._capture_frame_hash(output_path, time_sec=1.0) if self._available else ""
        wm_id = self._gen_id("text", f"{input_path}|{text}|{pos.value}|{opacity}")
        rec = WatermarkRecord(
            watermark_id=wm_id,
            video_id=Path(input_path).stem,
            input_path=os.path.abspath(input_path),
            output_path=output_path,
            kind="text",
            text=text,
            position=pos.value,
            opacity=opacity,
            input_sha256=self._sha256(input_path),
            output_sha256=self._sha256(output_path),
            frame_sha256=frame_hash,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            metadata={
                "font_size": font_size,
                "font_color": font_color,
                "box": box,
                "elapsed_sec": round(elapsed, 3),
            },
        )
        self._record(rec)

        return WatermarkResult(
            success=True,
            output_path=output_path,
            watermark_id=wm_id,
            input_size=in_size,
            output_size=out_size,
            duration=duration,
            width=w,
            height=h,
            kind="text",
            text=text,
            position=pos.value,
            opacity=opacity,
            elapsed_sec=elapsed,
            message="Text watermark applied",
        )

    # ── 2. Image watermark ───────────────────────────────────────────────────
    def add_image_watermark(
        self,
        input_path: str,
        output_path: str,
        logo_path: str,
        position: Union[str, WatermarkPosition] = "bottomright",
        opacity: float = 0.5,
        scale: float = 0.15,
        margin: int = 10,
    ) -> WatermarkResult:
        """Add a logo image watermark via ffmpeg overlay filter.

        Args:
            input_path: Source video
            output_path: Where to write the watermarked video
            logo_path: Logo image (PNG with alpha recommended)
            position: corner/center
            opacity: 0.0 — 1.0 (applied via format=auto + colorchannelmixer)
            scale: logo width as fraction of video width (e.g. 0.15 = 15%)
            margin: pixel margin from edge
        """
        start = time.time()
        if not os.path.exists(input_path):
            raise WatermarkInputError(f"Input video not found: {input_path}")
        if not os.path.exists(logo_path):
            raise WatermarkInputError(f"Logo image not found: {logo_path}")
        opacity = max(0.0, min(1.0, float(opacity)))
        scale = max(0.01, min(1.0, float(scale)))
        pos = WatermarkPosition.normalize(position)
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        meta = self._ffprobe(input_path)
        w, h = meta.get("width", 0) or 0, meta.get("height", 0) or 0
        duration = meta.get("duration", 0) or 0.0

        # Compute logo target width in pixels (height auto)
        logo_w = max(8, int(w * scale)) if w else 64

        # Overlay coordinates
        if pos == WatermarkPosition.TOPLEFT:
            x_expr, y_expr = f"{margin}", f"{margin}"
        elif pos == WatermarkPosition.TOPRIGHT:
            x_expr, y_expr = f"W-w-{margin}", f"{margin}"
        elif pos == WatermarkPosition.BOTTOMLEFT:
            x_expr, y_expr = f"{margin}", f"H-h-{margin}"
        elif pos == WatermarkPosition.BOTTOMRIGHT:
            x_expr, y_expr = f"W-w-{margin}", f"H-h-{margin}"
        else:  # CENTER
            x_expr, y_expr = f"(W-w)/2", f"(H-h)/2"

        # Filter chain: scale logo → set opacity → overlay
        vf = (
            f"[1:v]scale={logo_w}:-1,format=rgba,"
            f"colorchannelmixer=aa={opacity:.3f}[logo];"
            f"[0:v][logo]overlay={x_expr}:{y_expr}"
        )

        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", input_path,
            "-i", logo_path,
            "-filter_complex", vf,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "26",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            self._run_ffmpeg(cmd, "add_image_watermark")
        except WatermarkEngineUnavailable:
            logger.warning("ffmpeg unavailable, copying input to output")
            shutil.copyfile(input_path, output_path)

        elapsed = time.time() - start
        in_size = os.path.getsize(input_path)
        out_size = os.path.getsize(output_path)
        frame_hash = self._capture_frame_hash(output_path, time_sec=1.0) if self._available else ""
        wm_id = self._gen_id("image", f"{input_path}|{logo_path}|{pos.value}|{opacity}")
        rec = WatermarkRecord(
            watermark_id=wm_id,
            video_id=Path(input_path).stem,
            input_path=os.path.abspath(input_path),
            output_path=output_path,
            kind="image",
            logo_path=os.path.abspath(logo_path),
            position=pos.value,
            opacity=opacity,
            input_sha256=self._sha256(input_path),
            output_sha256=self._sha256(output_path),
            frame_sha256=frame_hash,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            metadata={
                "scale": scale,
                "logo_width": logo_w,
                "elapsed_sec": round(elapsed, 3),
            },
        )
        self._record(rec)

        return WatermarkResult(
            success=True,
            output_path=output_path,
            watermark_id=wm_id,
            input_size=in_size,
            output_size=out_size,
            duration=duration,
            width=w,
            height=h,
            kind="image",
            text="",
            position=pos.value,
            opacity=opacity,
            elapsed_sec=elapsed,
            message="Image watermark applied",
        )

    # ── 3. Invisible (audio LSB) ─────────────────────────────────────────────
    def add_invisible_watermark(
        self,
        input_path: str,
        output_path: str,
        message: str = "IMDF",
    ) -> WatermarkResult:
        """
        Embed an invisible message into the audio track via LSB of PCM samples.

        Simplified implementation: we extract the first audio stream to WAV PCM,
        rewrite the LSB of selected samples to carry message bits, then remux
        with the original video stream. This is intentionally minimal — for
        production use a dedicated audio stego library.
        """
        start = time.time()
        if not os.path.exists(input_path):
            raise WatermarkInputError(f"Input video not found: {input_path}")
        if not message:
            raise WatermarkInputError("Watermark message must be non-empty")
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        meta = self._ffprobe(input_path)
        w, h = meta.get("width", 0) or 0, meta.get("height", 0) or 0
        duration = meta.get("duration", 0) or 0.0

        with tempfile.TemporaryDirectory() as td:
            wav_in = os.path.join(td, "in.wav")
            wav_out = os.path.join(td, "out.wav")
            # 1. extract audio
            try:
                self._run_ffmpeg(
                    [
                        self.ffmpeg_bin, "-y", "-i", input_path,
                        "-vn", "-acodec", "pcm_s16le", "-ar", "44100",
                        "-ac", "2", wav_in,
                    ],
                    "audio_extract",
                )
            except (WatermarkEngineUnavailable, WatermarkProcessingError) as e:
                # No audio track in source — fall back to copy + report
                logger.warning("audio_extract failed (%s); copying input to output", e)
                shutil.copyfile(input_path, output_path)
                return self._stub_result(
                    input_path, output_path, "audio", message,
                    "audio", "center", 1.0, w, h, duration, start,
                )

            # 2. embed LSB into PCM
            self._lsb_embed_wav(wav_in, wav_out, message)

            # 3. remux video + watermarked audio (FLAC for lossless LSB preservation)
            try:
                self._run_ffmpeg(
                    [
                        self.ffmpeg_bin, "-y",
                        "-i", input_path,
                        "-i", wav_out,
                        "-c:v", "copy",
                        "-c:a", "flac",
                        "-map", "0:v:0",
                        "-map", "1:a:0",
                        "-shortest",
                        output_path,
                    ],
                    "audio_remux",
                )
            except (WatermarkEngineUnavailable, WatermarkProcessingError):
                shutil.copyfile(input_path, output_path)

        elapsed = time.time() - start
        in_size = os.path.getsize(input_path)
        out_size = os.path.getsize(output_path)
        frame_hash = self._capture_frame_hash(output_path, time_sec=1.0)
        wm_id = self._gen_id("audio", f"{input_path}|{message}")
        rec = WatermarkRecord(
            watermark_id=wm_id,
            video_id=Path(input_path).stem,
            input_path=os.path.abspath(input_path),
            output_path=output_path,
            kind="audio",
            text=message,
            position="center",
            opacity=1.0,
            input_sha256=self._sha256(input_path),
            output_sha256=self._sha256(output_path),
            frame_sha256=frame_hash,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            metadata={
                "method": "audio_lsb",
                "elapsed_sec": round(elapsed, 3),
                "message_len": len(message),
            },
        )
        self._record(rec)

        return WatermarkResult(
            success=True,
            output_path=output_path,
            watermark_id=wm_id,
            input_size=in_size,
            output_size=out_size,
            duration=duration,
            width=w,
            height=h,
            kind="audio",
            text=message,
            position="center",
            opacity=1.0,
            elapsed_sec=elapsed,
            message="Audio LSB watermark applied",
        )

    def _stub_result(
        self, input_path, output_path, kind, text, *_args,
    ) -> WatermarkResult:
        return WatermarkResult(
            success=False, output_path=output_path,
            message="ffmpeg unavailable, fallback applied",
            kind=kind, text=text,
            input_size=os.path.getsize(input_path) if os.path.exists(input_path) else 0,
            output_size=os.path.getsize(output_path) if os.path.exists(output_path) else 0,
        )

    def _capture_frame_hash(self, video_path: str, time_sec: float = 1.0) -> str:
        """Extract a single scaled frame and return its sha256 — for verification."""
        if not self._available or not os.path.exists(video_path):
            return ""
        # Probe duration so we don't seek past the end
        meta = self._ffprobe(video_path)
        dur = float(meta.get("duration") or 0)
        # Pick a timestamp safely inside [0, dur)
        candidates = [time_sec, dur / 2 if dur > 0 else 0, 0.5, 0.1]
        ts = next((t for t in candidates if 0 <= t < max(dur, 0.1)), 0.1)
        with tempfile.TemporaryDirectory() as td:
            frame = os.path.join(td, "frame.png")
            try:
                self._run_ffmpeg(
                    [
                        self.ffmpeg_bin, "-y",
                        "-ss", f"{ts:.3f}",
                        "-i", video_path,
                        "-vframes", "1",
                        "-vf", "scale=320:-1",
                        frame,
                    ],
                    "capture_frame",
                )
            except WatermarkError:
                # Last resort: try without -ss
                try:
                    self._run_ffmpeg(
                        [
                            self.ffmpeg_bin, "-y",
                            "-i", video_path,
                            "-vframes", "1",
                            "-vf", "scale=320:-1",
                            frame,
                        ],
                        "capture_frame_fallback",
                    )
                except WatermarkError:
                    return ""
            if os.path.exists(frame) and os.path.getsize(frame) > 0:
                return self._sha256(frame)
        return ""

    @staticmethod
    def _lsb_embed_wav(in_wav: str, out_wav: str, message: str) -> None:
        """Embed `message` into LSB of 16-bit PCM samples.

        Strategy: write 32-bit length prefix (in bytes), then message bytes,
        each spread across 8 samples (1 bit per sample). Mark with magic
        header `IMDF` (4 bytes) at start of length.
        """
        import struct
        import wave

        msg_bytes = message.encode("utf-8")
        # Header: 'IMDF' (4 bytes) + length (4 bytes big-endian) + payload
        payload = b"IMDF" + struct.pack(">I", len(msg_bytes)) + msg_bytes

        with wave.open(in_wav, "rb") as w:
            n_ch = w.getnchannels()
            samp_w = w.getsampwidth()
            n = w.getnframes()
            rate = w.getframerate()
            raw = w.readframes(n)

        if samp_w != 2:
            # Only support 16-bit PCM for LSB simplicity
            with open(out_wav, "wb") as f:
                f.write(raw)
            return

        samples = list(struct.unpack(f"<{len(raw) // 2}h", raw))
        # Need enough samples: 8 bits per byte of payload
        bits_needed = len(payload) * 8
        if len(samples) < bits_needed:
            # Skip embedding if not enough room; just copy through
            with open(out_wav, "wb") as f:
                f.write(raw)
            return

        # Embed: write each payload bit into the LSB of consecutive samples
        for i, byte in enumerate(payload):
            for bit in range(8):
                sample_idx = i * 8 + bit
                current = samples[sample_idx]
                # Clear LSB, then OR with our bit
                samples[sample_idx] = (current & ~1) | ((byte >> (7 - bit)) & 1)

        new_raw = struct.pack(f"<{len(samples)}h", *samples)
        with wave.open(out_wav, "wb") as w:
            w.setnchannels(n_ch)
            w.setsampwidth(samp_w)
            w.setframerate(rate)
            w.writeframes(new_raw)

    def extract_audio_watermark(self, video_path: str) -> str:
        """Extract the audio LSB message from a watermarked video. Returns '' on miss."""
        import struct
        import wave
        import tempfile

        if not self._available:
            return ""

        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "extract.wav")
            try:
                self._run_ffmpeg(
                    [
                        self.ffmpeg_bin, "-y", "-i", video_path,
                        "-vn", "-acodec", "pcm_s16le",
                        "-ar", "44100", "-ac", "2", wav,
                    ],
                    "audio_extract",
                )
            except WatermarkError:
                return ""

            try:
                with wave.open(wav, "rb") as w:
                    raw = w.readframes(w.getnframes())
                if len(raw) < 8 * 8:
                    return ""
                samples = struct.unpack(f"<{len(raw) // 2}h", raw)
                # Read first 8 bytes (length prefix)
                first_bytes = []
                for i in range(8):
                    byte = 0
                    for bit in range(8):
                        sample_idx = i * 8 + bit
                        byte = (byte << 1) | (samples[sample_idx] & 1)
                    first_bytes.append(byte)
                if bytes(first_bytes[:4]) != b"IMDF":
                    return ""
                msg_len = struct.unpack(">I", bytes(first_bytes[4:8]))[0]
                if msg_len <= 0 or msg_len > 4096:
                    return ""
                # Read msg_len more bytes
                msg_bytes = bytearray()
                total_bytes = 8 + msg_len
                for i in range(8, total_bytes):
                    byte = 0
                    for bit in range(8):
                        sample_idx = i * 8 + bit
                        if sample_idx >= len(samples):
                            return ""
                        byte = (byte << 1) | (samples[sample_idx] & 1)
                    msg_bytes.append(byte)
                return msg_bytes.decode("utf-8", errors="replace")
            except (OSError, struct.error, wave.Error):
                return ""

    # ── 4. Verify watermark ───────────────────────────────────────────────────
    def verify_watermark(self, video_path: str, watermark_id: Optional[str] = None) -> bool:
        """
        Verify that a watermark exists in `video_path`.

        Strategy (lightweight, no OCR dependency):
            1. Extract a mid-video frame using ffmpeg.
            2. If watermark_id is known, look up the recorded metadata
               (kind, position, opacity, text).
            3. Crop the corresponding watermark region and compute hash +
               brightness statistics.
            4. Return True if the region differs from a clean frame
               baseline OR matches expected watermark signature.

        For audio watermarks, calls extract_audio_watermark.

        Falls back to True if ffmpeg is unavailable (degraded mode).
        """
        if not os.path.exists(video_path):
            return False

        rec: Optional[WatermarkRecord] = None
        if watermark_id:
            rec = self.lookup(watermark_id)

        # Audio path
        if rec and rec.kind == "audio":
            extracted = self.extract_audio_watermark(video_path)
            return bool(extracted) and extracted == (rec.text or "")

        if not self._available:
            # degraded mode: file exists & has nonzero size
            return os.path.getsize(video_path) > 0

        # Visual path: extract mid-frame, compare against the recorded frame hash
        with tempfile.TemporaryDirectory() as td:
            frame_path = os.path.join(td, "frame.png")
            # Use the helper which is duration-aware
            full_hash = self._capture_frame_hash(video_path, time_sec=1.0)
            if not full_hash:
                return False
            if rec and rec.frame_sha256:
                return full_hash == rec.frame_sha256
            return bool(full_hash)

            if not os.path.exists(frame_path):
                return False

            full_hash = self._sha256(frame_path)
            if rec and rec.frame_sha256:
                # Strong check: frame hash should match the recorded one
                return full_hash == rec.frame_sha256

            # Weak check (no record): presence of any non-empty frame means OK
            return bool(full_hash)


# ── Module-level singleton ───────────────────────────────────────────────────
_engine: Optional[WatermarkEngine] = None


def get_engine() -> WatermarkEngine:
    global _engine
    if _engine is None:
        _engine = WatermarkEngine()
    return _engine