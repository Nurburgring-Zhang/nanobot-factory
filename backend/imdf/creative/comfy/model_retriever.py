"""Model catalogue for Comfy MCP (V5 ch.30).

Eight concrete model entries covering SD1.5 / SDXL / SD3 / Flux /
AnimateDiff / IP-Adapter / ControlNet. Each entry lists:

- ``name``: display name used by the LLM
- ``type``: ``base`` / ``refiner`` / ``motion`` / ``adapter`` / ``control``
- ``checkpoint``: the .safetensors filename on disk
- ``resolution``: native width / height tuple
- ``capabilities``: capability tokens (txt2img, lora, ip_adapter, ...)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .schemas import ModelMatch


class ModelEntry:
    """Catalogue row — intentionally NOT a Pydantic model so we can
    keep ``capabilities`` as a tuple for fast intersection."""

    __slots__ = ("name", "type", "checkpoint", "resolution",
                 "capabilities", "tags", "description")

    def __init__(
        self,
        name: str,
        type: str,
        checkpoint: str,
        resolution: Tuple[int, int],
        capabilities: Tuple[str, ...],
        tags: Tuple[str, ...] = (),
        description: str = "",
    ) -> None:
        self.name = name
        self.type = type
        self.checkpoint = checkpoint
        self.resolution = resolution
        self.capabilities = capabilities
        self.tags = tags
        self.description = description

    def has_capability(self, cap: str) -> bool:
        return cap in self.capabilities


class ModelRetriever:
    """Search the model catalogue by capability / tag.

    Public API:
        :meth:`search` returns a list of :class:`ModelMatch` scored by
        capability overlap. Empty ``requirements`` returns every entry
        ordered by name.
    """

    MODELS: Dict[str, ModelEntry] = {
        "sdxl": ModelEntry(
            name="sdxl",
            type="base",
            checkpoint="sd_xl_base_1.0.safetensors",
            resolution=(1024, 1024),
            capabilities=("txt2img", "img2img", "lora", "inpaint", "controlnet"),
            tags=("photoreal", "general"),
            description="SDXL base — high-resolution general purpose.",
        ),
        "sdxl_turbo": ModelEntry(
            name="sdxl_turbo",
            type="base",
            checkpoint="sdxl_turbo_1step.safetensors",
            resolution=(1024, 1024),
            capabilities=("txt2img", "fast", "lcm"),
            tags=("photoreal", "fast"),
            description="SDXL Turbo — single-step distilled for speed.",
        ),
        "sd_15": ModelEntry(
            name="sd_15",
            type="base",
            checkpoint="v1-5-pruned-emaonly.safetensors",
            resolution=(512, 512),
            capabilities=("txt2img", "img2img", "lora", "inpaint", "controlnet"),
            tags=("legacy", "fast"),
            description="SD 1.5 — classic, vast ecosystem.",
        ),
        "sd_3": ModelEntry(
            name="sd_3",
            type="base",
            checkpoint="sd3_medium_incl_clips.safetensors",
            resolution=(1024, 1024),
            capabilities=("txt2img", "img2img", "lora"),
            tags=("photoreal", "typography"),
            description="Stable Diffusion 3 — better typography, MMDiT.",
        ),
        "flux": ModelEntry(
            name="flux",
            type="base",
            checkpoint="flux1-dev.safetensors",
            resolution=(1024, 1024),
            capabilities=("txt2img", "img2img", "guidance_distill"),
            tags=("photoreal", "artistic"),
            description="Flux.1-dev — state-of-the-art open model.",
        ),
        "animate_diff": ModelEntry(
            name="animate_diff",
            type="motion",
            checkpoint="mm_sd15_v15_animate.ckpt",
            resolution=(512, 512),
            capabilities=("txt2video", "motion_module"),
            tags=("video", "animation"),
            description="AnimateDiff — turn SD1.5 into a video model.",
        ),
        "ip_adapter": ModelEntry(
            name="ip_adapter",
            type="adapter",
            checkpoint="ip-adapter-plus_sdxl_vit-h.safetensors",
            resolution=(1024, 1024),
            capabilities=("image_prompt", "style_transfer", "face"),
            tags=("adapter", "reference"),
            description="IPAdapter Plus — image-as-prompt conditioning.",
        ),
        "controlnet": ModelEntry(
            name="controlnet",
            type="control",
            checkpoint="controlnet-canny-sdxl.safetensors",
            resolution=(1024, 1024),
            capabilities=("canny", "depth", "openpose", "lineart"),
            tags=("control", "structural"),
            description="ControlNet SDXL — structural guidance (canny/depth/...).",
        ),
    }

    # ── Public API ─────────────────────────────────────────────────────
    async def search(self, requirements: Optional[Dict[str, Any]] = None) -> List[ModelMatch]:
        """Return model matches sorted by descending score.

        ``requirements`` keys:
            - ``capability``: required capability token, e.g. ``"txt2img"``.
            - ``type``:       required type, e.g. ``"base"``.
            - ``tags``:       any-of match against :attr:`ModelEntry.tags`.
            - ``name``:       substring match against :attr:`ModelEntry.name`.
            - ``min_resolution``: minimum (width, height).
        """
        requirements = requirements or {}
        scored: List[ModelMatch] = []
        for entry in self.MODELS.values():
            score, reason = self._score(entry, requirements)
            if score > 0.0:
                scored.append(ModelMatch(
                    name=entry.name,
                    type=entry.type,
                    score=round(score, 4),
                    reason=reason,
                    capabilities=list(entry.capabilities),
                ))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored

    async def get(self, name: str) -> Optional[ModelEntry]:
        """Return a catalogue entry by exact name (case-insensitive)."""
        return self.MODELS.get(name.lower())

    def list_models(self) -> List[str]:
        """Return the names of every model in the catalogue."""
        return sorted(self.MODELS.keys())

    # ── Internal ───────────────────────────────────────────────────────
    @staticmethod
    def _score(entry: ModelEntry, req: Dict[str, Any]) -> Tuple[float, str]:
        score = 0.0
        reasons: List[str] = []

        # Capability match — hard requirement; score 0 means filtered out.
        cap = req.get("capability")
        if cap:
            if entry.has_capability(cap):
                score += 1.0
                reasons.append(f"has capability {cap!r}")
            else:
                return 0.0, f"missing required capability {cap!r}"

        # Type match — soft bonus.
        if req.get("type") and req["type"] == entry.type:
            score += 0.5
            reasons.append(f"type match {entry.type!r}")

        # Tag any-of — bonus per matched tag.
        wanted_tags = req.get("tags") or []
        if isinstance(wanted_tags, str):
            wanted_tags = [wanted_tags]
        tag_hits = [t for t in wanted_tags if t in entry.tags]
        score += 0.2 * len(tag_hits)
        if tag_hits:
            reasons.append(f"tags {tag_hits}")

        # Name substring match.
        name_q = req.get("name")
        if name_q:
            if name_q.lower() in entry.name.lower():
                score += 0.3
                reasons.append(f"name contains {name_q!r}")
            else:
                # If name was given, treat as hard filter.
                return 0.0, f"name {name_q!r} not in {entry.name!r}"

        # Minimum resolution.
        min_res = req.get("min_resolution")
        if isinstance(min_res, (list, tuple)) and len(min_res) == 2:
            if (entry.resolution[0] >= min_res[0]
                    and entry.resolution[1] >= min_res[1]):
                score += 0.2
                reasons.append(f"resolution >= {tuple(min_res)}")
            else:
                return 0.0, f"resolution {entry.resolution} < {tuple(min_res)}"

        # Default score for unconstrained search.
        if score == 0.0 and not req:
            score = 1.0
        return score, "; ".join(reasons) or "default match"


__all__ = ["ModelRetriever", "ModelEntry"]