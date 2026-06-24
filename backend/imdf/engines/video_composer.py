"""
Video Composition Engine
========================
FFmpeg-based video processing engine for clip concatenation, audio mixing,
frame extraction, and image-sequence-to-video compositing.

All operations use subprocess to call ffmpeg with timeout handling.

Usage:
    composer = VideoComposer()
    composer.concat_clips(["clip1.mp4", "clip2.mp4"], "output.mp4")
    composer.add_audio("video.mp4", "audio.mp3", "output.mp4")
    frames = composer.extract_frames("video.mp4", "frames/", fps=24)
    composer.compose_from_images("frames/", "output.mp4", fps=24)
"""

import os
import subprocess
import logging
import tempfile
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_FFMPEG_PATH = "ffmpeg"
DEFAULT_FFPROBE_PATH = "ffprobe"
DEFAULT_TIMEOUT = 300  # 5 minutes


class VideoComposerError(Exception):
    """Base exception for video composition errors"""
    pass


class VideoComposer:
    """
    FFmpeg-based video composition engine.

    All methods use subprocess to invoke ffmpeg with configurable timeout.
    """

    def __init__(self, ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
                 ffprobe_path: str = DEFAULT_FFPROBE_PATH,
                 timeout: int = DEFAULT_TIMEOUT):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.timeout = timeout

    # ── Video Probe ───────────────────────────────────────────────────────

    def probe(self, video_path: str) -> dict:
        """
        Get video metadata using ffprobe.

        Returns dict with duration, width, height, codec, fps, etc.
        """
        cmd = [
            self.ffprobe_path, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=30)
            if result.returncode != 0:
                raise VideoComposerError(
                    f"ffprobe failed: {result.stderr[:500]}"
                )
            import json
            data = json.loads(result.stdout)
            info = {"file": video_path, "format": data.get("format", {})}
            for stream in data.get("streams", []):
                codec_type = stream.get("codec_type", "")
                if codec_type == "video":
                    info["video"] = {
                        "codec": stream.get("codec_name", ""),
                        "width": stream.get("width", 0),
                        "height": stream.get("height", 0),
                        "fps": self._parse_fps(stream.get("r_frame_rate", "0/1")),
                        "duration": float(stream.get("duration", 0) or 0),
                    }
                elif codec_type == "audio":
                    info["audio"] = {
                        "codec": stream.get("codec_name", ""),
                        "sample_rate": stream.get("sample_rate", ""),
                        "channels": stream.get("channels", 0),
                    }
            return info
        except subprocess.TimeoutExpired:
            raise VideoComposerError(f"ffprobe timed out for {video_path}")
        except FileNotFoundError:
            raise VideoComposerError(
                f"ffprobe not found at '{self.ffprobe_path}'. "
                "Install ffmpeg and ensure it's in PATH."
            )

    def _parse_fps(self, r_frame_rate: str) -> float:
        """Parse '24/1' or '30000/1001' style framerate strings"""
        try:
            parts = r_frame_rate.split("/")
            if len(parts) == 2:
                return float(parts[0]) / float(parts[1])
            return float(parts[0])
        except (ValueError, ZeroDivisionError, IndexError):
            return 0.0

    # ── Clip Concatenation ────────────────────────────────────────────────

    def concat_clips(self, inputs: List[str], output: str) -> str:
        """
        Concatenate multiple video clips into one.

        Uses ffmpeg's concat demuxer for seamless joining.
        All clips must have the same resolution and codec.

        Args:
            inputs: List of video file paths
            output: Output video file path

        Returns:
            Absolute path to the output file
        """
        if not inputs:
            raise VideoComposerError("No input clips provided")

        output = os.path.abspath(output)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        # Create concat file list
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, encoding="utf-8") as f:
            concat_file = f.name
            for video in inputs:
                abs_path = os.path.abspath(video)
                if not os.path.exists(abs_path):
                    raise VideoComposerError(f"Input file not found: {abs_path}")
                f.write(f"file '{abs_path}'\n")

        try:
            cmd = [
                self.ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",  # Copy streams without re-encoding
                output,
            ]
            logger.info(f"Concatenating {len(inputs)} clips → {output}")
            logger.debug(f"CMD: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode != 0:
                raise VideoComposerError(
                    f"concat failed (code {result.returncode}): "
                    f"{result.stderr[:500]}"
                )
            logger.info(f"Concatenation complete: {output}")
            return output

        except subprocess.TimeoutExpired:
            raise VideoComposerError(
                f"concat timed out after {self.timeout}s"
            )
        finally:
            try:
                os.unlink(concat_file)
            except OSError:
                pass

    # ── Audio Mixing ──────────────────────────────────────────────────────

    def add_audio(self, video_path: str, audio_path: str,
                  output: str) -> str:
        """
        Add/replace audio track on a video.

        Args:
            video_path: Input video file
            audio_path: Input audio file
            output: Output video file path

        Returns:
            Absolute path to the output file
        """
        video_path = os.path.abspath(video_path)
        audio_path = os.path.abspath(audio_path)
        output = os.path.abspath(output)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        if not os.path.exists(video_path):
            raise VideoComposerError(f"Video not found: {video_path}")
        if not os.path.exists(audio_path):
            raise VideoComposerError(f"Audio not found: {audio_path}")

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",         # Copy video stream (no re-encode)
            "-c:a", "aac",          # Re-encode audio to AAC
            "-shortest",            # Match shortest stream duration
            "-map", "0:v:0",        # Video from first input
            "-map", "1:a:0",        # Audio from second input
            output,
        ]
        logger.info(f"Adding audio {audio_path} → {video_path} → {output}")
        logger.debug(f"CMD: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode != 0:
                raise VideoComposerError(
                    f"add_audio failed (code {result.returncode}): "
                    f"{result.stderr[:500]}"
                )
            logger.info(f"Audio added: {output}")
            return output

        except subprocess.TimeoutExpired:
            raise VideoComposerError(
                f"add_audio timed out after {self.timeout}s"
            )

    # ── Frame Extraction ──────────────────────────────────────────────────

    def extract_frames(self, video_path: str, output_dir: str,
                       fps: float = 24, quality: int = 2) -> List[str]:
        """
        Extract frames from a video as image files.

        Args:
            video_path: Input video file
            output_dir: Directory to save frames
            fps: Frames per second to extract (default: 24)
            quality: JPEG quality (2=best, 31=worst)

        Returns:
            List of extracted frame file paths (sorted)
        """
        video_path = os.path.abspath(video_path)
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        if not os.path.exists(video_path):
            raise VideoComposerError(f"Video not found: {video_path}")

        pattern = os.path.join(output_dir, "frame_%06d.jpg")

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vf", f"fps={fps}",
            "-q:v", str(quality),
            pattern,
        ]
        logger.info(f"Extracting frames at {fps}fps from {video_path} → {output_dir}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode != 0:
                raise VideoComposerError(
                    f"extract_frames failed (code {result.returncode}): "
                    f"{result.stderr[:500]}"
                )

            # Collect extracted frames
            frames = sorted([
                str(p) for p in Path(output_dir).glob("frame_*.jpg")
            ])
            logger.info(f"Extracted {len(frames)} frames to {output_dir}")
            return frames

        except subprocess.TimeoutExpired:
            raise VideoComposerError(
                f"extract_frames timed out after {self.timeout}s"
            )

    # ── Image Sequence to Video ───────────────────────────────────────────

    def compose_from_images(self, image_dir: str, output: str,
                            fps: float = 24,
                            codec: str = "libx264") -> str:
        """
        Compose a video from an image sequence.

        Args:
            image_dir: Directory containing images (sorted by name)
            output: Output video file path
            fps: Output framerate
            codec: Video codec (default: libx264)

        Returns:
            Absolute path to the output file
        """
        image_dir = os.path.abspath(image_dir)
        output = os.path.abspath(output)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        if not os.path.isdir(image_dir):
            raise VideoComposerError(f"Image directory not found: {image_dir}")

        # Use image sequence pattern
        input_pattern = os.path.join(image_dir, "frame_%06d.jpg")

        cmd = [
            self.ffmpeg_path, "-y",
            "-framerate", str(fps),
            "-i", input_pattern,
            "-c:v", codec,
            "-pix_fmt", "yuv420p",   # Wide compatibility
            "-preset", "medium",
            "-crf", "18",            # High quality
            output,
        ]

        # If no frame_%06d files, try a glob-based approach
        frames = sorted(Path(image_dir).glob("*.jpg"))
        if not frames:
            frames = sorted(Path(image_dir).glob("*.png"))

        if not frames:
            raise VideoComposerError(
                f"No image files found in {image_dir}"
            )

        # Check if we have numbered frames or need concat
        if len(frames) == 1:
            # Single image — create a still video
            cmd = [
                self.ffmpeg_path, "-y",
                "-loop", "1",
                "-i", str(frames[0]),
                "-c:v", codec,
                "-t", "5",           # 5 seconds default
                "-pix_fmt", "yuv420p",
                "-preset", "medium",
                "-crf", "18",
                output,
            ]
        else:
            # Check if frames follow %06d pattern
            has_numbered = any(
                p.stem.startswith("frame_") and p.stem[6:].isdigit()
                for p in frames[:5]
            )
            if not has_numbered:
                # Use concat with file list instead
                input_pattern = os.path.join(image_dir, "%06d.jpg")
                # Check actual extensions
                ext = ".jpg"
                if frames[0].suffix.lower() == ".png":
                    ext = ".png"
                # Build a concat demuxer file
                with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                                 delete=False,
                                                 encoding="utf-8") as f:
                    concat_file = f.name
                    for frame in frames:
                        dur = 1.0 / fps
                        f.write(f"file '{frame}'\n")
                        f.write(f"duration {dur}\n")

                cmd = [
                    self.ffmpeg_path, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:v", codec,
                    "-pix_fmt", "yuv420p",
                    "-preset", "medium",
                    "-crf", "18",
                    output,
                ]

        logger.info(f"Composing video from {len(frames)} images → {output}")
        logger.debug(f"CMD: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode != 0:
                raise VideoComposerError(
                    f"compose_from_images failed (code {result.returncode}): "
                    f"{result.stderr[:500]}"
                )
            # Clean up temp concat file if created
            concat_file_local = locals().get("concat_file")
            if concat_file_local:
                try:
                    os.unlink(concat_file_local)
                except OSError:
                    pass

            logger.info(f"Video composed: {output}")
            return output

        except subprocess.TimeoutExpired:
            raise VideoComposerError(
                f"compose_from_images timed out after {self.timeout}s"
            )
        except Exception as e:
            # Clean up on error too
            concat_file_local = locals().get("concat_file")
            if concat_file_local:
                try:
                    os.unlink(concat_file_local)
                except OSError:
                    pass
            raise

    # ── Utility ───────────────────────────────────────────────────────────

    def check_ffmpeg(self) -> bool:
        """Verify ffmpeg is available"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
