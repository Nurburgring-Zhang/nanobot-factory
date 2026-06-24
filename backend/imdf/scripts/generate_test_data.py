#!/usr/bin/env python3
"""
IMDF P0 深度打磨 — 测试数据集生成器
=========================================
生成真实的测试fixtures:
  - 20张测试图片 (不同分辨率/格式: jpg/png/webp/gif)
  - 10个测试视频 (不同尺寸/时长)
  - 10个测试音频 (wav/mp3)
  - 10个测试文档 (txt/md/json)
输出到: data/test_fixtures/
"""
import os
import sys
import struct
import wave
import json
import random
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Add project root
PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

OUTPUT_DIR = PROJ_ROOT / "data" / "test_fixtures"

# Try importing Pillow
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

def _random_color() -> tuple:
    return (random.randint(20, 240), random.randint(20, 240), random.randint(20, 240))

def generate_images():
    """Generate 20 test images with varied resolutions and formats."""
    if not HAS_PILLOW:
        print("[SKIP] Pillow not available, generating minimal test images via raw bytes")
        _generate_fallback_images()
        return

    ensure_dir(OUTPUT_DIR)
    
    configs = [
        # (name, size, format, color_scheme)
        ("landscape_4k", (3840, 2160), "jpg", "warm"),
        ("portrait_hd", (1080, 1920), "jpg", "cool"),
        ("square_1k", (1024, 1024), "png", "vivid"),
        ("banner_wide", (1920, 640), "png", "pastel"),
        ("thumbnail_sm", (256, 256), "jpg", "bright"),
        ("poster_large", (2400, 3600), "jpg", "dark"),
        ("icon_tiny", (64, 64), "png", "mono"),
        ("web_banner", (1200, 628), "webp", "warm"),
        ("social_post", (1080, 1080), "jpg", "cool"),
        ("hero_image", (1920, 1080), "png", "vivid"),
        ("card_small", (400, 300), "jpg", "pastel"),
        ("panorama_wide", (4096, 1024), "jpg", "bright"),
        ("product_shot", (2000, 2000), "png", "neutral"),
        ("gradient_test", (800, 600), "png", "gradient"),
        ("noise_pattern", (640, 480), "jpg", "noise"),
        ("stripe_pattern", (1280, 720), "png", "mono"),
        ("checkerboard", (512, 512), "png", "contrast"),
        ("animated_simple", (320, 240), "gif", "bright"),
        ("gradient_radial", (1024, 1024), "webp", "gradient"),
        ("text_overlay", (1600, 900), "jpg", "dark"),
    ]

    for i, (name, (w, h), fmt, scheme) in enumerate(configs):
        out_path = OUTPUT_DIR / f"{name}.{fmt}"
        if out_path.exists():
            print(f"  [skip] {out_path.name} (exists)")
            continue

        img = Image.new("RGB", (w, h), _bg_color(scheme))
        draw = ImageDraw.Draw(img)
        
        # Draw some visual content
        for _ in range(random.randint(3, 8)):
            x1 = random.randint(0, w - 10)
            y1 = random.randint(0, h - 10)
            x2 = random.randint(x1 + 5, w)
            y2 = random.randint(y1 + 5, h)
            color = _random_color()
            if random.random() < 0.5:
                draw.rectangle([x1, y1, x2, y2], fill=color, outline=_random_color(), width=random.randint(1, 4))
            else:
                draw.ellipse([x1, y1, x2, y2], fill=color, outline=_random_color())

        # Label text
        label = f"IMDF Test: {name} ({w}x{h})"
        try:
            font = ImageFont.load_default()
            draw.text((10, 10), label, fill=(255, 255, 255))
            draw.text((10, h - 20), f"Format: {fmt.upper()}", fill=(200, 200, 200))
        except Exception as e:
            logger.error(f"Operation failed: {e}")

        save_kwargs = {}
        if fmt == "jpg":
            save_kwargs = {"quality": random.randint(50, 95)}
        elif fmt == "png":
            save_kwargs = {}
        elif fmt == "webp":
            save_kwargs = {"quality": random.randint(50, 90)}
        elif fmt == "gif":
            # Create a simple 2-frame animation
            frame2 = Image.new("RGB", (w, h), _bg_color("cool"))
            draw2 = ImageDraw.Draw(frame2)
            draw2.rectangle([w//4, h//4, 3*w//4, 3*h//4], fill=(255, 200, 100))
            img.save(out_path, save_all=True, append_images=[frame2], duration=500, loop=0)
            print(f"  [OK] {out_path.name} ({w}x{h}, {fmt}, animated)")
            continue

        img.save(out_path, **save_kwargs)
        print(f"  [OK] {out_path.name} ({w}x{h}, {fmt})")

def _bg_color(scheme: str) -> tuple:
    palettes = {
        "warm": (240, 180, 120),
        "cool": (100, 150, 220),
        "vivid": (80, 200, 100),
        "pastel": (220, 210, 240),
        "bright": (250, 250, 200),
        "dark": (30, 30, 50),
        "mono": (128, 128, 128),
        "neutral": (200, 200, 200),
        "gradient": (60, 60, 120),
        "noise": (100, 100, 100),
        "contrast": (255, 255, 255),
    }
    return palettes.get(scheme, (128, 128, 128))

def _generate_fallback_images():
    """Generate minimal valid image files without Pillow."""
    ensure_dir(OUTPUT_DIR)
    
    # Minimal valid JPEG (1x1 pixel)
    minimal_jpeg = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb0043000101010101010101"
        "0101010101010101010101010101010101010101010101010101010101010101"
        "0101010101010101010101010101010101010101010101010101ffc0000b0800"
        "01000101011100ffc4001410000000000000000000000000000000000008ffc4"
        "001a08000202030100000000000000000000000000050604070203ffda0008"
        "010100003f0078df6b5e00000000000000000000000000000000000000000000"
        "0000000000ffd9"
    )
    # Minimal valid PNG
    minimal_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010100000000376ef9"
        "240000000a49444154789c626000000002000188e0cb9f0000000049454e44ae"
        "426082"
    )
    # Minimal valid GIF
    minimal_gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    
    configs = [("test_fallback", "jpg"), ("test_fallback2", "png"), ("test_fallback3", "gif")]
    for name, fmt in configs:
        out_path = OUTPUT_DIR / f"{name}.{fmt}"
        if out_path.exists():
            continue
        data = {"jpg": minimal_jpeg, "png": minimal_png, "gif": minimal_gif}[fmt]
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"  [OK] {out_path.name} (fallback, {fmt})")


def generate_videos():
    """Generate 10 test video files using ffmpeg if available."""
    ensure_dir(OUTPUT_DIR)
    
    ffmpeg_available = os.system("which ffmpeg > /dev/null 2>&1") == 0
    
    video_configs = [
        ("demo_1080p", "1920x1080", 3),
        ("demo_720p", "1280x720", 5),
        ("demo_480p", "854x480", 4),
        ("demo_360p", "640x360", 2),
        ("demo_4k", "3840x2160", 1),
        ("social_vertical", "1080x1920", 3),
        ("square_video", "1080x1080", 4),
        ("short_clip", "640x480", 2),
        ("tiny_video", "320x240", 1),
        ("medium_30fps", "1280x720", 3),
    ]
    
    for name, res, duration in video_configs:
        out_path = OUTPUT_DIR / f"{name}.mp4"
        if out_path.exists():
            print(f"  [skip] {out_path.name} (exists)")
            continue
        
        if ffmpeg_available:
            w, h = res.split("x")
            color = f"0x{random.randint(0,255):02x}{random.randint(0,255):02x}{random.randint(0,255):02x}"
            cmd = (
                f'ffmpeg -y -f lavfi -i "color=c={color}:s={w}x{h}:d={duration}" '
                f'-vf "drawtext=text=\'IMDF Test Video: {name} {w}x{h}\':'
                f'fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2" '
                f'-c:v libx264 -preset ultrafast -pix_fmt yuv420p "{out_path}" '
                f'2>/dev/null'
            )
            ret = os.system(cmd)
            if ret == 0:
                sz = out_path.stat().st_size
                print(f"  [OK] {out_path.name} ({res}, {duration}s, {sz} bytes)")
            else:
                print(f"  [FAIL] {out_path.name} - ffmpeg error")
        else:
            # Generate a minimal MP4 stub
            _generate_video_stub(out_path, w, h)
            print(f"  [STUB] {out_path.name} ({res}, {duration}s)")

def _generate_video_stub(out_path: Path, w: str, h: str):
    """Generate a minimal valid MP4 file stub."""
    # Minimal ISOBMFF/MP4 structure
    stub = b"\x00\x00\x00\x1cftypmp42\x00\x00\x00\x00mp42mp41\x00\x00\x00\x08free"
    with open(out_path, "wb") as f:
        f.write(stub)


def generate_audio():
    """Generate 10 test audio files (WAV and MP3)."""
    ensure_dir(OUTPUT_DIR)
    
    ffmpeg_available = os.system("which ffmpeg > /dev/null 2>&1") == 0
    
    audio_configs = [
        ("test_tone_440hz", 2, 440),
        ("test_tone_880hz", 3, 880),
        ("test_tone_220hz", 1, 220),
        ("test_sweep", 5, None),  # frequency sweep
        ("test_silence", 1, 0),
    ]
    
    for name, duration, freq in audio_configs:
        # WAV
        wav_path = OUTPUT_DIR / f"{name}.wav"
        if not wav_path.exists() and not ffmpeg_available:
            _generate_wav_stub(wav_path, duration, freq)
            print(f"  [STUB] {wav_path.name} ({duration}s)")
        elif not wav_path.exists():
            freq_part = f":frequency={freq}" if freq else ":frequency=440:sweep=t"
            cmd = (
                f'ffmpeg -y -f lavfi -i "sine{freq_part}:duration={duration}" '
                f'-ac 2 -ar 44100 "{wav_path}" 2>/dev/null'
            )
            ret = os.system(cmd)
            if ret == 0:
                print(f"  [OK] {wav_path.name} ({duration}s)")
            else:
                _generate_wav_stub(wav_path, duration, freq)
                print(f"  [STUB] {wav_path.name} ({duration}s)")
        
        # MP3
        mp3_path = OUTPUT_DIR / f"{name}.mp3"
        if not mp3_path.exists():
            if ffmpeg_available and wav_path.exists():
                cmd = f'ffmpeg -y -i "{wav_path}" -codec:a libmp3lame -b:a 128k "{mp3_path}" 2>/dev/null'
                os.system(cmd)
                if mp3_path.exists():
                    print(f"  [OK] {mp3_path.name}")
                else:
                    _generate_mp3_stub(mp3_path)
                    print(f"  [STUB] {mp3_path.name}")
            else:
                _generate_mp3_stub(mp3_path)
                print(f"  [STUB] {mp3_path.name}")


def _generate_wav_stub(out_path: Path, duration: float, freq: int):
    """Generate a minimal valid WAV file."""
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    num_channels = 1
    bits_per_sample = 16
    
    data = bytearray()
    for i in range(num_samples):
        if freq and freq > 0:
            import math
            t = i / sample_rate
            value = int(16000 * math.sin(2 * math.pi * freq * t))
        else:
            value = 0
        data.extend(struct.pack('<h', max(-32768, min(32767, value))))
    
    with wave.open(str(out_path), 'w') as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(bits_per_sample // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(data)


def _generate_mp3_stub(out_path: Path):
    """Generate a minimal MP3 file stub."""
    # MPEG Audio frame header + minimal silence
    stub = bytes([
        0xff, 0xfb, 0x90, 0x00,  # MPEG1 Layer3 128kbps 44100Hz stereo
    ])
    with open(out_path, "wb") as f:
        f.write(stub + b"\x00" * 200)


def generate_documents():
    """Generate 10 test document files (txt, md, json)."""
    ensure_dir(OUTPUT_DIR)
    
    docs = [
        ("readme", "md", "# IMDF Test Document\n\n## Overview\nThis is a **test** document for IMDF P0 verification.\n\n### Features\n- Feature A: Automated tagging\n- Feature B: Preview generation\n- Feature C: Aesthetic scoring\n\n> This is a blockquote\n\n```python\nprint('Hello IMDF')\n```\n"),
        ("config_sample", "json", json.dumps({
            "project": "IMDF P0 Test",
            "version": "1.0.0",
            "settings": {
                "resolution": "1920x1080",
                "format": "RGB",
                "quality": 95
            },
            "tags": ["test", "verification", "p0"],
            "enabled_features": ["dam", "aesthetic", "template", "event"]
        }, indent=2)),
        ("sample_data", "json", json.dumps({
            "data_points": [
                {"id": 1, "value": 42.5, "label": "alpha"},
                {"id": 2, "value": 73.1, "label": "beta"},
                {"id": 3, "value": 18.9, "label": "gamma"}
            ]
        }, indent=2)),
        ("log_sample", "txt", (
            "2025-06-15 10:00:00 [INFO] Server started\n"
            "2025-06-15 10:00:01 [INFO] DAM engine initialized\n"
            "2025-06-15 10:00:02 [INFO] Scanning data directories\n"
            "2025-06-15 10:00:03 [INFO] Found 58 files\n"
            "2025-06-15 10:00:04 [WARN] ffmpeg not found - video previews disabled\n"
            "2025-06-15 10:00:05 [INFO] Aesthetic engine ready\n"
            "2025-06-15 10:00:06 [INFO] Template market loaded (6 templates)\n"
        )),
        ("notes", "md", "# Meeting Notes\n\n## 2025-06-15\n- P0 code polishing in progress\n- DAM engine needs preview verification\n- Aesthetic scoring: 6 dimensions tested\n\n## Action Items\n- [ ] Generate test fixtures\n- [ ] Run verification suite\n- [ ] Write report\n"),
        ("api_response", "json", json.dumps({
            "success": True,
            "data": {
                "total": 3,
                "items": [
                    {"name": "landscape_4k.jpg", "category": "image", "size": 2048576},
                    {"name": "demo_1080p.mp4", "category": "video", "size": 52428800},
                    {"name": "test_tone_440hz.wav", "category": "audio", "size": 352800}
                ]
            }
        }, indent=2)),
        ("empty_doc", "txt", ""),
        ("unicode_test", "txt", "Unicode测试: 中文日本語한국어🎉🎨🎬"),
        ("multi_line", "txt", "\n".join([f"Line {i}: This is a long text line for testing text preview capabilities of the IMDF DAM engine." for i in range(50)])),
        ("yaml_style", "md", "key1: value1\nkey2:\n  subkey: value2\n  list:\n    - item1\n    - item2\n"),
    ]
    
    for name, ext, content in docs:
        out_path = OUTPUT_DIR / f"{name}.{ext}"
        if out_path.exists():
            print(f"  [skip] {out_path.name} (exists)")
            continue
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [OK] {out_path.name} ({len(content)} chars)")


def main():
    print("=" * 60)
    print("IMDF P0 测试数据集生成器")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    ensure_dir(OUTPUT_DIR)
    
    print("\n[1/4] Generating 20 test images...")
    generate_images()
    
    print("\n[2/4] Generating 10 test videos...")
    generate_videos()
    
    print("\n[3/4] Generating 10 test audio files...")
    generate_audio()
    
    print("\n[4/4] Generating 10 test documents...")
    generate_documents()
    
    # Count results
    files = list(OUTPUT_DIR.rglob("*"))
    print(f"\n{'='*60}")
    print(f"Total files generated: {len(files)}")
    for f in sorted(files):
        if f.is_file():
            print(f"  {f.name} ({f.stat().st_size} bytes)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
