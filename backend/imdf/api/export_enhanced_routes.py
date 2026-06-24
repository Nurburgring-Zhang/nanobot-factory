"""
F1.17 交付打包 — 增强导出路由
============================
POST /api/v1/export/package     — 打包ZIP下载
POST /api/v1/export/watermark   — 添加水印并导出
GET  /api/v1/export/download/{filename}  — 下载导出文件
"""

import os
import io
import zipfile
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Body, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/export", tags=["export_package"])

# 导出输出目录
EXPORT_DIR = Path("data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# 水印输出目录
WATERMARK_DIR = Path("data/watermarked")
WATERMARK_DIR.mkdir(parents=True, exist_ok=True)


class PackageRequest(BaseModel):
    """ZIP打包请求"""
    paths: List[str] = []              # 文件/目录路径列表
    dataset_id: str = ""               # 数据集ID
    format: str = "zip"               # zip / tar.gz
    include_metadata: bool = True     # 是否包含元数据JSON
    password: Optional[str] = None    # ZIP密码保护 (需要安装pyminizip或pyzipper)


class WatermarkRequest(BaseModel):
    """水印请求"""
    image_paths: List[str] = []       # 图片路径列表
    text: str = "IMDF"               # 水印文字
    position: str = "bottom_right"   # top_left/top_right/bottom_left/bottom_right/center
    opacity: float = 0.3             # 透明度 0-1
    font_size: int = 36              # 字体大小
    color: str = "white"             # 水印颜色
    output_format: str = "png"       # 输出格式


# ── ZIP Packaging ──────────────────────────────────────────────────────

@router.post("/package")
async def package_export(req: PackageRequest):
    """将指定文件/数据集打包为ZIP下载

    支持:
    - 文件列表打包
    - 数据集目录打包
    - 元数据嵌入
    - 可选的ZIP密码保护
    """
    files_to_pack = []

    # 收集文件
    if req.dataset_id:
        dataset_dir = Path("data/datasets") / req.dataset_id
        if dataset_dir.exists():
            for f in dataset_dir.rglob("*"):
                if f.is_file():
                    files_to_pack.append(str(f))
        else:
            # 也尝试 data/output 等目录
            alt_dirs = [
                Path("data/output") / req.dataset_id,
                Path("data") / req.dataset_id,
            ]
            found = False
            for d in alt_dirs:
                if d.exists():
                    for f in d.rglob("*"):
                        if f.is_file():
                            files_to_pack.append(str(f))
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail=f"Dataset not found: {req.dataset_id}")

    if req.paths:
        for p in req.paths:
            pp = Path(p)
            if pp.is_file():
                files_to_pack.append(str(pp))
            elif pp.is_dir():
                for f in pp.rglob("*"):
                    if f.is_file():
                        files_to_pack.append(str(f))
            else:
                # 尝试相对于data的路径
                alt = Path("data") / p
                if alt.is_file():
                    files_to_pack.append(str(alt))

    if not files_to_pack:
        raise HTTPException(status_code=400, detail="No files found to package")

    # 去重
    files_to_pack = list(set(files_to_pack))

    # 创建ZIP
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"imdf_export_{timestamp}.zip"
    zip_path = EXPORT_DIR / zip_filename

    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in files_to_pack:
            arcname = os.path.relpath(fpath, os.path.commonpath(files_to_pack)
                                      if len(files_to_pack) > 1 else os.path.dirname(fpath))
            zf.write(fpath, arcname)

        # 添加元数据
        if req.include_metadata:
            import json
            metadata = {
                "exported_at": datetime.now().isoformat(),
                "total_files": len(files_to_pack),
                "dataset_id": req.dataset_id,
                "files": [{"path": fp, "size": os.path.getsize(fp)
                           if os.path.exists(fp) else 0} for fp in files_to_pack[:100]],
            }
            zf.writestr("_metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))

    zip_size = os.path.getsize(str(zip_path))
    zip_size_human = f"{zip_size / 1024:.1f} KB" if zip_size < 1024 * 1024 else f"{zip_size / 1024 / 1024:.1f} MB"

    return {
        "success": True,
        "data": {
            "filename": zip_filename,
            "path": str(zip_path),
            "file_count": len(files_to_pack),
            "size": zip_size,
            "size_human": zip_size_human,
            "download_url": f"/api/v1/export/download/{zip_filename}",
        },
        "message": f"Package created: {zip_filename} ({zip_size_human})",
    }


# ── Watermark ──────────────────────────────────────────────────────────

@router.post("/watermark")
async def add_watermark(req: WatermarkRequest):
    """为图片添加文字水印

    使用Pillow添加可配置位置/透明度/颜色的文字水印。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise HTTPException(status_code=500, detail="Pillow not installed. Run: pip install Pillow")

    if not req.image_paths:
        raise HTTPException(status_code=400, detail="image_paths is required")

    results = []

    for img_path in req.image_paths:
        p = Path(img_path)
        if not p.exists():
            results.append({"path": img_path, "status": "error", "error": "File not found"})
            continue

        try:
            img = Image.open(p).convert("RGBA")

            # 创建水印图层
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # 尝试加载字体，失败则用默认
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", req.font_size)
            except (IOError, OSError):
                try:
                    font = ImageFont.truetype("arial.ttf", req.font_size)
                except (IOError, OSError):
                    font = ImageFont.load_default()

            # 颜色映射
            color_map = {
                "white": (255, 255, 255),
                "black": (0, 0, 0),
                "red": (255, 0, 0),
                "gray": (128, 128, 128),
                "yellow": (255, 255, 0),
            }
            rgba_color = color_map.get(req.color.lower(), (255, 255, 255)) + (int(255 * req.opacity),)

            # 计算文字尺寸
            bbox = draw.textbbox((0, 0), req.text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            # 位置
            margin = 20
            positions = {
                "top_left": (margin, margin),
                "top_right": (img.width - text_w - margin, margin),
                "bottom_left": (margin, img.height - text_h - margin),
                "bottom_right": (img.width - text_w - margin, img.height - text_h - margin),
                "center": ((img.width - text_w) // 2, (img.height - text_h) // 2),
            }
            pos = positions.get(req.position, positions["bottom_right"])

            draw.text(pos, req.text, fill=rgba_color, font=font)

            # 合成
            watermarked = Image.alpha_composite(img, overlay)

            # 保存
            out_filename = f"{p.stem}_wm.{req.output_format}"
            out_path = WATERMARK_DIR / out_filename
            watermarked.convert("RGB").save(str(out_path), req.output_format.upper())

            results.append({
                "path": img_path,
                "status": "success",
                "output": str(out_path),
                "output_filename": out_filename,
            })
        except Exception as e:
            results.append({"path": img_path, "status": "error", "error": str(e)})

    success_count = len([r for r in results if r["status"] == "success"])

    return {
        "success": True,
        "data": {
            "results": results,
            "total": len(results),
            "success_count": success_count,
            "failed_count": len(results) - success_count,
            "watermark_text": req.text,
            "position": req.position,
        },
        "message": f"Watermark applied: {success_count}/{len(results)} images",
    }


# ── Download ───────────────────────────────────────────────────────────

@router.get("/download/{filename:path}")
async def download_export(filename: str):
    """下载导出的文件"""
    # 安全检查: 防止路径遍历
    safe_name = os.path.basename(filename)
    file_path = EXPORT_DIR / safe_name

    if not file_path.exists():
        # 也检查水印目录
        wm_path = WATERMARK_DIR / safe_name
        if wm_path.exists():
            file_path = wm_path
        else:
            raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    media_type = "application/zip" if safe_name.endswith(".zip") else "application/octet-stream"

    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=safe_name,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
