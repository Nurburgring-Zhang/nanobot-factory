"""P19 v5.1-D3: Export Engine — 18-format central dispatch.

提供:
- ``ExportEngine``: 主类, 用 format string 触发对应 exporter
- ``export(format, dataset, output, **kwargs)``: 模块级快捷入口
- ``list_supported_formats()``: 列出所有 18 格式

设计:
- 每个 exporter 接收 ``dataset`` (DatasetVersion-like) 和 ``output: str``
- exporter 负责写出文件, 返回写入路径
- 错误时返回 ``""`` 或 raise (由 caller 决定)

历史兼容:
- ``engines.dataset_manager`` 的 export_coco / webdataset / jsonl / parquet /
  llava / internvl 接受 (version, output), 由 manager 实例触发.
- 新 12 个 exporter 接受 (dataset, output, **kwargs) (DatasetVersion-like).
- 本 engine 把 ``dataset`` 视为 DatasetVersion-like; 当遇到 DatasetManager-bound
  method 时, 由 caller 显式传 manager (通过 ``export_with_manager``).
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import (
    REGISTRY,
    SUPPORTED_FORMATS,
    get_format_info,
    list_formats,
)


def _resolve_exporter(spec: str) -> Callable[..., str]:
    """解析 'exports.glb:export' 形式, 返回 callable."""
    mod_path, _, attr = spec.partition(":")
    if not attr:
        attr = "export"
    try:
        mod = importlib.import_module(mod_path)
    except Exception as exc:
        raise ImportError(f"cannot import {mod_path}: {exc}")
    fn = getattr(mod, attr, None)
    if fn is None:
        raise AttributeError(f"{mod_path}.{attr} not found")
    return fn


@dataclass
class ExportRequest:
    format: str
    dataset: Any = None
    output: str = ""
    options: Optional[Dict[str, Any]] = None


class ExportEngine:
    """18-format export engine + P19 v5.5 class-based exporters."""

    # P19 v5.5: class-based async exporters (V5 FR-3.2 second wave)
    EXPORTERS: Dict[str, object] = {}
    """format name → exporter class instance (NOT instantiated yet by default).

    Each entry maps a format key to the exporter CLASS itself (not an instance)
    so callers can do ``ExportEngine.EXPORTERS['createml']().export(...)``.
    Populated at module import time (see end of file).
    """

    def __init__(self, data_dir: str = "data/exports"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._executor_cache: Dict[str, Callable[..., str]] = {}

    def list_formats(self) -> List[str]:
        return list(SUPPORTED_FORMATS)

    def list_by_category(self, category: str) -> List[str]:
        return list_formats(category)

    def supports(self, fmt: str) -> bool:
        return fmt in REGISTRY

    def list_class_exporters(self) -> List[str]:
        """P19 v5.5: list format names that have a class-based exporter registered."""
        return list(self.EXPORTERS.keys())

    def run_class_exporter(self, fmt: str, dataset: Any,
                           output: str, **kwargs) -> "object":
        """P19 v5.5: dispatch a class-based exporter and return its ExportResult.

        Returns whatever the exporter's ``export(...)`` returns (typically an
        :class:`ExportResult` dataclass).
        """
        if fmt not in self.EXPORTERS:
            raise ValueError(
                f"no class-based exporter registered for format {fmt!r}; "
                f"available: {sorted(self.EXPORTERS.keys())}"
            )
        cls = self.EXPORTERS[fmt]
        instance = cls(**{k: v for k, v in kwargs.items()
                          if k in getattr(cls, "__init__", object.__init__).__code__.co_varnames
                          or k == "data_dir"})
        # If the class accepts dataset+output as kwargs, pass them; else use positional.
        import inspect as _inspect
        try:
            sig = _inspect.signature(cls.export)
            params = list(sig.parameters.keys())
            if "dataset" in params and "output_path" in params:
                return instance.export(dataset=dataset, output_path=output, **kwargs)
            if "dataset" in params and "output" in params:
                return instance.export(dataset, output, **kwargs)
        except (TypeError, ValueError):
            pass
        return instance.export(dataset, output, **kwargs)

    def export(self, fmt: str, dataset, output: str = "",
               manager=None, **kwargs) -> str:
        """导出 dataset 为指定 format. Returns write path.

        Args:
            fmt: format id (e.g. "glb", "coco", "wav")
            dataset: DatasetVersion-like (有 .files list + .version 属性)
                     或者 DatasetManager 实例 (有 .export_X method).
                     当 manager=None 时, 若 dataset 是 DatasetVersion-like, 走 registry path.
                     当 manager 不为 None, 通过 export_with_manager 走 (manager 有 export_coco 等).
            manager: 可选, DatasetManager 实例. 当 manager 指定, 即使是 jsonl/coco/webdataset 等
                     bound method 也通过 manager 触发.
            output: 输出路径. 空时用 ``data_dir/<version>_<label><ext>``.

        Returns:
            写入文件路径.
        """
        if fmt not in REGISTRY:
            raise ValueError(f"unsupported format: {fmt!r}")
        info = REGISTRY[fmt]
        spec = info["exporter"]
        # Default output path
        if not output:
            ext = info["ext"]
            label = info["label"].lower().replace(" ", "_")
            if dataset is not None and hasattr(dataset, "version"):
                ds_name = dataset.version
            else:
                ds_name = "dataset"
            output = str(self.data_dir / f"{ds_name}_{label}{ext}")

        # 路径 1: 显式 manager → bound method (DatasetManager.export_X)
        if manager is not None:
            # Normalize the version argument: callers may pass either a
            # DatasetVersion-like (with .version str) or a bare version id
            # string.  export_with_manager expects a string version id.
            if isinstance(dataset, str):
                version_id = dataset
            else:
                version_id = getattr(dataset, "version", None) or ""
            return self.export_with_manager(fmt, manager, version_id, output, **kwargs)

        # 路径 2: unbound function (exports.X:export)
        # 即使 spec 是 engines.dataset_manager:... 形式, 若 caller 没传 manager,
        # 我们尝试用 dataset 上的同名 method (若有, 则 dataset 自己就是 manager).
        if spec.startswith("engines.dataset_manager:"):
            _, _, method_path = spec.partition(":")
            method_name = method_path.split(".")[-1]
            if dataset is not None and hasattr(dataset, method_name):
                method = getattr(dataset, method_name)
                version = getattr(dataset, "version", None)
                if version is not None:
                    return method(version, output)
                # 无 version 时, 尝试 (dataset, output)
                try:
                    return method(dataset, output)
                except TypeError:
                    return method(output)

            # P21 P2 P3R (R2 data #4) fix: when no manager is passed and the
            # dataset does not implement the manager-bound export itself,
            # lazily instantiate a default DatasetManager so that the 18-format
            # export registry works end-to-end without callers having to wire
            # a manager manually.  This must NOT change behavior when a manager
            # is explicitly passed (the explicit-manager branch above is hit
            # first and we never reach this code).
            from ..engines.dataset_manager import DatasetManager
            base_dir = os.path.dirname(output) or "."
            lazy_manager = DatasetManager(data_dir=base_dir)
            if dataset is None:
                raise ValueError(
                    f"format {fmt!r} requires a DatasetManager + version. "
                    f"Call export_with_manager(fmt, manager, version, output)."
                )
            # Auto-register a dataset-like object as a version so the manager
            # can look it up via get_version(version).  We accept any object
            # exposing both ``.version`` (str) and ``.files`` (Iterable).
            version_str = getattr(dataset, "version", None)
            if not version_str or not isinstance(version_str, str):
                raise ValueError(
                    f"format {fmt!r} requires a DatasetManager + version. "
                    f"Dataset must expose a string .version attribute; "
                    f"got {type(dataset).__name__}."
                )
            if not lazy_manager.get_version(version_str):
                lazy_manager._versions[version_str] = dataset
            return self.export_with_manager(fmt, lazy_manager, version_str, output, **kwargs)

        # unbound function path
        if spec not in self._executor_cache:
            self._executor_cache[spec] = _resolve_exporter(spec)
        fn = self._executor_cache[spec]
        return fn(dataset, output, **kwargs)

    def export_with_manager(self, fmt: str, manager, version: str,
                            output: str = "", **kwargs) -> str:
        """通过 DatasetManager 触发现有 export_coco / webdataset / jsonl / parquet
        / llava / internvl 等 bound method.

        Args:
            fmt: 格式 id
            manager: DatasetManager 实例
            version: dataset version string
            output: 输出路径
        """
        if fmt not in REGISTRY:
            raise ValueError(f"unsupported format: {fmt!r}")
        info = REGISTRY[fmt]
        spec = info["exporter"]
        if not spec.startswith("engines.dataset_manager:"):
            # 非 manager-bound — 退回到 export() 路径
            ver = manager.get_version(version)
            return self.export(fmt, ver, output, **kwargs)
        # 解析 method name
        _, _, method_path = spec.partition(":")
        method_name = method_path.split(".")[-1]
        if not hasattr(manager, method_name):
            raise AttributeError(f"manager has no method {method_name}")
        method = getattr(manager, method_name)
        # Default output path
        if not output:
            ext = info["ext"]
            label = info["label"].lower().replace(" ", "_")
            output = str(self.data_dir / f"{version}_{label}{ext}")
        return method(version, output)


_engine: Optional[ExportEngine] = None


def get_engine() -> ExportEngine:
    global _engine
    if _engine is None:
        _engine = ExportEngine()
    return _engine


def export(format: str, dataset, output: str = "", **kwargs) -> str:
    """模块级快捷入口."""
    return get_engine().export(format, dataset, output, **kwargs)


def list_supported_formats() -> List[str]:
    return list(SUPPORTED_FORMATS)


__all__ = [
    "ExportEngine",
    "ExportRequest",
    "export",
    "get_engine",
    "list_supported_formats",
]


# ============================================================================
# P19 v5.5 — Class-based exporter registry (V5 FR-3.2 second wave)
# ============================================================================
# Register ``CreateMLExporter`` and ``CSVExporter`` class-based async exporters
# in ``ExportEngine.EXPORTERS``. Function-based paths in REGISTRY remain
# untouched so the 18-format export regression test stays green.
def _populate_class_exporters() -> None:
    """Populate ``ExportEngine.EXPORTERS`` with class-based exporter classes.

    Lazy-imported so importing this module doesn't pull pydantic transitively
    in paths that only need REGISTRY lookup.
    """
    try:
        from .create_ml_exporter import CreateMLExporter  # noqa: WPS433
        ExportEngine.EXPORTERS["createml"] = CreateMLExporter
    except ImportError as exc:  # pragma: no cover
        import warnings
        warnings.warn(f"CreateMLExporter not registered: {exc}", ImportWarning)
    try:
        from .csv_exporter import CSVExporter  # noqa: WPS433
        ExportEngine.EXPORTERS["csv"] = CSVExporter
    except ImportError as exc:  # pragma: no cover
        import warnings
        warnings.warn(f"CSVExporter not registered: {exc}", ImportWarning)


_populate_class_exporters()