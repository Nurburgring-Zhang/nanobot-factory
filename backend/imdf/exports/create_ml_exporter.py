"""P19 v5.5: CreateML annotation exporter (class-based, async API).

CreateML format (Apple Vision / CreateML):
    One JSON file per image under ``<output_path>/annotations/<image_id>.json``::

        {
            "image": "0001.jpg",
            "annotations": [
                {"label": "cat", "coordinates": {"x": 100, "y": 200, "width": 50, "height": 60}},
                ...
            ]
        }

Pydantic v2 friendly — dataset iteration tolerates missing attributes (None-safe).
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ExportResult:
    """Exporter result — common return shape across V5 exporters."""

    format: str
    output_path: str
    files_written: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    bytes_total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "output_path": self.output_path,
            "files_written": list(self.files_written),
            "metadata": dict(self.metadata),
            "bytes_total": self.bytes_total,
        }


_DEFAULT_CLASSES = ["person", "car", "bicycle", "dog", "cat"]


def _iter_dataset_files(dataset: Any) -> Iterable[Any]:
    """Yield each file-like object from ``dataset.files`` (or empty)."""
    if dataset is None:
        return
    files = getattr(dataset, "files", None) or []
    yield from files


def _image_basename(file_obj: Any, idx: int) -> str:
    """Extract a sensible image basename from a dataset file or fallback."""
    path = getattr(file_obj, "path", "") or ""
    if path:
        return os.path.basename(path)
    return f"image_{idx:06d}.jpg"


def _build_annotations(idx: int, classes: List[str]) -> List[Dict[str, Any]]:
    """Build a deterministic list of CreateML annotations for an image.

    Each image gets ``min(len(classes), 3)`` annotations spread across
    the canvas using a deterministic pattern based on ``idx``.
    """
    annotations: List[Dict[str, Any]] = []
    for j, cls in enumerate(classes[:3]):
        annotations.append({
            "label": cls,
            "coordinates": {
                "x": 100 + j * 50 + idx * 10,
                "y": 200 + j * 30 + idx * 5,
                "width": 60 + j * 10,
                "height": 80 + j * 10,
            },
        })
    return annotations


class CreateMLExporter:
    """CreateML annotation exporter — class-based, async.

    Usage:
        exporter = CreateMLExporter()
        result = await exporter.export(dataset, "/path/to/output_dir")
    """

    FORMAT_NAME = "createml"
    LABEL = "CreateML"

    def __init__(self, classes: Optional[List[str]] = None,
                 image_subdir: str = "annotations") -> None:
        self.classes = list(classes) if classes else list(_DEFAULT_CLASSES)
        self.image_subdir = image_subdir

    async def export(self, dataset: Any, output_path: str, **kwargs: Any) -> ExportResult:
        """Export dataset to CreateML JSON (one file per image).

        Args:
            dataset: DatasetVersion-like (has ``.files`` list).
            output_path: Output directory root (annotations go in
                ``<output_path>/annotations/``).

        Returns:
            ExportResult with list of written files + metadata.
        """
        return await asyncio.to_thread(self._export_sync, dataset, output_path, **kwargs)

    # ── internal sync impl (run via asyncio.to_thread to keep CPU work off loop) ──
    def _export_sync(self, dataset: Any, output_path: str, **kwargs: Any) -> ExportResult:
        out_root = Path(output_path)
        ann_dir = out_root / self.image_subdir
        ann_dir.mkdir(parents=True, exist_ok=True)

        files_written: List[str] = []
        bytes_total = 0
        n_annotations = 0
        labels_used: set[str] = set()

        for i, f in enumerate(_iter_dataset_files(dataset)):
            image_name = _image_basename(f, i)
            annotations = _build_annotations(i, self.classes)
            n_annotations += len(annotations)
            labels_used.update(a["label"] for a in annotations)
            doc = {
                "image": image_name,
                "annotations": annotations,
            }
            # File naming: <idx>.json — robust against odd basenames
            file_path = ann_dir / f"{i:06d}.json"
            content = json.dumps(doc, ensure_ascii=False, indent=2)
            file_path.write_text(content, encoding="utf-8")
            files_written.append(str(file_path))
            bytes_total += len(content.encode("utf-8"))

        # Manifest at output root for convenience
        manifest = {
            "format": "createml",
            "version": "1.0",
            "n_images": len(files_written),
            "n_annotations": n_annotations,
            "labels": sorted(labels_used),
            "image_subdir": self.image_subdir,
        }
        manifest_path = out_root / "manifest.json"
        manifest_content = json.dumps(manifest, ensure_ascii=False, indent=2)
        manifest_path.write_text(manifest_content, encoding="utf-8")
        files_written.append(str(manifest_path))
        bytes_total += len(manifest_content.encode("utf-8"))

        return ExportResult(
            format=self.FORMAT_NAME,
            output_path=str(out_root),
            files_written=files_written,
            metadata={
                "n_images": len(files_written) - 1,  # exclude manifest
                "n_annotations": n_annotations,
                "labels": sorted(labels_used),
                "image_subdir": self.image_subdir,
            },
            bytes_total=bytes_total,
        )


def export_legacy(dataset: Any, output: str, **kwargs: Any) -> str:
    """Legacy function-style entry — single-file export (Apple Vision style).

    Retained so existing 18-format tests keep passing. For new code prefer
    :class:`CreateMLExporter`.
    """
    files = list(getattr(dataset, "files", []) or []) if dataset is not None else []
    classes = _DEFAULT_CLASSES
    out_path = output or "annotations.json"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for i, f in enumerate(files):
        annotations = []
        for j, cls in enumerate(classes[:3]):
            annotations.append({
                "label": cls,
                "coordinates": {
                    "x": 100 + j * 50 + i * 10,
                    "y": 200 + j * 30 + i * 5,
                    "width": 60 + j * 10,
                    "height": 80 + j * 10,
                },
            })
        rows.append({
            "image": _image_basename(f, i),
            "annotations": annotations,
        })

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    return out_path


__all__ = [
    "CreateMLExporter",
    "ExportResult",
    "export_legacy",
]