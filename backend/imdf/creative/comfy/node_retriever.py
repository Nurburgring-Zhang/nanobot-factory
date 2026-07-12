"""ComfyUI node catalogue for Comfy MCP (V5 ch.30).

Fifteen concrete node entries covering the most common building
blocks used by an SD/Flux/AnimateDiff pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .schemas import NodeMatch


class NodeEntry:
    """Catalogue row — kept as a plain class for speed."""

    __slots__ = ("class_type", "category", "inputs", "outputs", "tags", "description")

    def __init__(
        self,
        class_type: str,
        category: str,
        inputs: Tuple[str, ...],
        outputs: Tuple[str, ...],
        tags: Tuple[str, ...] = (),
        description: str = "",
    ) -> None:
        self.class_type = class_type
        self.category = category
        self.inputs = inputs
        self.outputs = outputs
        self.tags = tags
        self.description = description


class NodeRetriever:
    """Search the ComfyUI node catalogue."""

    NODES: Dict[str, NodeEntry] = {
        "LoadImage": NodeEntry(
            class_type="LoadImage",
            category="io",
            inputs=("image",),
            outputs=("IMAGE", "MASK"),
            tags=("input", "image"),
            description="Load a PNG/JPG from disk.",
        ),
        "CLIPTextEncode": NodeEntry(
            class_type="CLIPTextEncode",
            category="conditioning",
            inputs=("clip", "text"),
            outputs=("CONDITIONING",),
            tags=("text", "prompt"),
            description="Encode a text prompt with CLIP.",
        ),
        "KSampler": NodeEntry(
            class_type="KSampler",
            category="sampler",
            inputs=("model", "positive", "negative", "latent_image"),
            outputs=("LATENT",),
            tags=("denoise", "core"),
            description="Standard diffusion sampler.",
        ),
        "VAEDecode": NodeEntry(
            class_type="VAEDecode",
            category="latent",
            inputs=("samples", "vae"),
            outputs=("IMAGE",),
            tags=("decode", "vae"),
            description="Decode latent tensor to image.",
        ),
        "SaveImage": NodeEntry(
            class_type="SaveImage",
            category="io",
            inputs=("images",),
            outputs=(),
            tags=("output", "save"),
            description="Persist image to ComfyUI output folder.",
        ),
        "CheckpointLoaderSimple": NodeEntry(
            class_type="CheckpointLoaderSimple",
            category="loader",
            inputs=("ckpt_name",),
            outputs=("MODEL", "CLIP", "VAE"),
            tags=("loader", "checkpoint"),
            description="Load a single safetensors checkpoint.",
        ),
        "CLIPImageEncode": NodeEntry(
            class_type="CLIPImageEncode",
            category="conditioning",
            inputs=("clip", "image"),
            outputs=("CLIP_VISION_OUTPUT",),
            tags=("vision", "ip_adapter"),
            description="Encode an image to CLIP vision embedding.",
        ),
        "ControlNetLoader": NodeEntry(
            class_type="ControlNetLoader",
            category="loader",
            inputs=("control_net_name",),
            outputs=("CONTROL_NET",),
            tags=("controlnet", "loader"),
            description="Load a ControlNet model.",
        ),
        "IPAdapter": NodeEntry(
            class_type="IPAdapter",
            category="adapter",
            inputs=("model", "ipadapter", "image", "weight"),
            outputs=("MODEL",),
            tags=("ip_adapter", "reference"),
            description="Apply IPAdapter conditioning to a model.",
        ),
        "FaceDetailer": NodeEntry(
            class_type="FaceDetailer",
            category="postprocess",
            inputs=("image", "model", "clip", "vae", "guide_size"),
            outputs=("IMAGE",),
            tags=("face", "detail"),
            description="Detect & re-render faces at higher detail.",
        ),
        "LoraLoader": NodeEntry(
            class_type="LoraLoader",
            category="loader",
            inputs=("model", "clip", "lora_name", "strength_model", "strength_clip"),
            outputs=("MODEL", "CLIP"),
            tags=("lora", "loader"),
            description="Apply a LoRA to a checkpoint.",
        ),
        "ControlNetApply": NodeEntry(
            class_type="ControlNetApply",
            category="conditioning",
            inputs=("conditioning", "control_net", "image", "strength"),
            outputs=("CONDITIONING",),
            tags=("controlnet", "apply"),
            description="Apply ControlNet to a conditioning tensor.",
        ),
        "ImageScale": NodeEntry(
            class_type="ImageScale",
            category="preprocess",
            inputs=("image", "width", "height", "method"),
            outputs=("IMAGE",),
            tags=("resize", "preprocess"),
            description="Resize an image.",
        ),
        "ImageBatch": NodeEntry(
            class_type="ImageBatch",
            category="preprocess",
            inputs=("image1", "image2"),
            outputs=("IMAGE",),
            tags=("batch", "merge"),
            description="Combine two images into a batch.",
        ),
        "EmptyLatentImage": NodeEntry(
            class_type="EmptyLatentImage",
            category="latent",
            inputs=("width", "height", "batch_size"),
            outputs=("LATENT",),
            tags=("latent", "init"),
            description="Produce an empty latent tensor.",
        ),
    }

    async def search(self, requirements: Optional[Dict[str, Any]] = None) -> List[NodeMatch]:
        """Return node matches sorted by descending score.

        ``requirements`` keys:
            - ``category``: exact match.
            - ``output``:   node must produce this output type.
            - ``input``:    node must accept this input slot.
            - ``tag``:      any-of tag.
            - ``class_type``: substring match.
        """
        requirements = requirements or {}
        scored: List[NodeMatch] = []
        for entry in self.NODES.values():
            score, reason = self._score(entry, requirements)
            if score > 0.0:
                scored.append(NodeMatch(
                    class_type=entry.class_type,
                    score=round(score, 4),
                    reason=reason,
                    inputs=list(entry.inputs),
                    outputs=list(entry.outputs),
                ))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored

    async def get(self, class_type: str) -> Optional[NodeEntry]:
        return self.NODES.get(class_type)

    def list_nodes(self) -> List[str]:
        return sorted(self.NODES.keys())

    @staticmethod
    def _score(entry: NodeEntry, req: Dict[str, Any]) -> Tuple[float, str]:
        score = 0.0
        reasons: List[str] = []

        if req.get("category") and req["category"] != entry.category:
            return 0.0, f"category mismatch (want {req['category']!r}, got {entry.category!r})"
        if req.get("category"):
            score += 0.4
            reasons.append(f"category {entry.category!r}")

        if req.get("output"):
            if req["output"] not in entry.outputs:
                return 0.0, f"missing output {req['output']!r}"
            score += 0.6
            reasons.append(f"provides output {req['output']!r}")

        if req.get("input"):
            if req["input"] not in entry.inputs:
                return 0.0, f"missing input {req['input']!r}"
            score += 0.4
            reasons.append(f"accepts input {req['input']!r}")

        wanted_tags = req.get("tag")
        if wanted_tags:
            if isinstance(wanted_tags, str):
                wanted_tags = [wanted_tags]
            tag_hits = [t for t in wanted_tags if t in entry.tags]
            if tag_hits:
                score += 0.3 * len(tag_hits)
                reasons.append(f"tags {tag_hits}")
            else:
                return 0.0, f"no matching tags from {wanted_tags}"

        ct = req.get("class_type")
        if ct:
            if ct.lower() in entry.class_type.lower():
                score += 0.5
                reasons.append(f"name contains {ct!r}")
            else:
                return 0.0, f"class_type {ct!r} not in {entry.class_type!r}"

        if score == 0.0 and not req:
            score = 1.0
        return score, "; ".join(reasons) or "default match"


__all__ = ["NodeRetriever", "NodeEntry"]