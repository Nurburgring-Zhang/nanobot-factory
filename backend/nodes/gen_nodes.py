"""
生成节点 — 封装 production_workbench 的 Provider 为生成节点。

每个节点包装对应的 Provider，调用其 generate() 方法。
"""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseNode, NodeDefinition, NodePort, NodeParam
from .registry import registry

logger = logging.getLogger(__name__)


# =============================================================================
# Gen: Text-to-Image
# =============================================================================

class TextToImageNode(BaseNode):
    definition = NodeDefinition(
        node_id="gen.text_to_image",
        name="文生图",
        category="generate",
        description="使用文本提示生成图像",
        inputs=[NodePort(name="prompt", type="text", required=True)],
        outputs=[NodePort(name="images", type="image[]")],
        params=[
            NodeParam(name="provider", type="string", default="local"),
            NodeParam(name="model", type="string", default=""),
            NodeParam(name="negative_prompt", type="string", default=""),
            NodeParam(name="width", type="int", default=1024),
            NodeParam(name="height", type="int", default=1024),
            NodeParam(name="steps", type="int", default=30),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from production_workbench import (
                ProviderFactory,
                ProviderType,
                ProviderConfig,
                GenerationRequest,
            )

            prompt = inputs.get("prompt", "")
            if not prompt:
                return {"images": [], "error": "Empty prompt"}

            provider_type_str = params.get("provider", "local")
            provider_type = self._resolve_provider_type(provider_type_str)

            config = ProviderConfig(
                provider_type=provider_type,
                name=provider_type.value,
            )
            provider = ProviderFactory.create_provider(config)

            import uuid
            req = GenerationRequest(
                request_id=f"t2i-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                negative_prompt=params.get("negative_prompt", ""),
                settings={
                    "width": params.get("width", 1024),
                    "height": params.get("height", 1024),
                    "steps": params.get("steps", 30),
                    "model": params.get("model", ""),
                },
            )
            result = await provider.generate(req)
            return {
                "images": result.outputs if hasattr(result, "outputs") else [],
                "request_id": result.request_id,
                "status": result.status,
            }
        except Exception as e:
            logger.error(f"TextToImageNode failed: {e}")
            return {"images": [], "error": str(e)}

    def _resolve_provider_type(self, name: str):
        from production_workbench import ProviderType
        mapping = {
            "local": ProviderType.OMNI_GEN_LOCAL,
            "comfyui_local": ProviderType.COMFYUI_LOCAL,
            "comfyui_cloud": ProviderType.COMFYUI_CLOUD,
            "seedream5": ProviderType.SEEDREAM5,
            "qwen_image": ProviderType.QWEN_IMAGE,
            "z_image": ProviderType.Z_IMAGE,
            "nanobanana": ProviderType.NANOBANANA,
            "flux2_klein": ProviderType.FLUX2_KLEIN,
        }
        for pt in ProviderType:
            if pt.value == name or pt.name.lower() == name.lower():
                return pt
        return mapping.get(name, ProviderType.OMNI_GEN_LOCAL)


class TextToVideoNode(BaseNode):
    definition = NodeDefinition(
        node_id="gen.text_to_video",
        name="文生视频",
        category="generate",
        description="使用文本提示生成视频",
        inputs=[NodePort(name="prompt", type="text", required=True)],
        outputs=[NodePort(name="videos", type="video[]")],
        params=[
            NodeParam(name="provider", type="string", default="local"),
            NodeParam(name="duration", type="int", default=5),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from production_workbench import (
                ProviderFactory,
                ProviderType,
                ProviderConfig,
                GenerationRequest,
            )

            prompt = inputs.get("prompt", "")
            if not prompt:
                return {"videos": [], "error": "Empty prompt"}

            provider_type = self._resolve_video_provider(params.get("provider", "local"))
            config = ProviderConfig(
                provider_type=provider_type,
                name=provider_type.value,
            )
            provider = ProviderFactory.create_provider(config)

            import uuid
            req = GenerationRequest(
                request_id=f"t2v-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                settings={"duration": params.get("duration", 5)},
            )
            result = await provider.generate(req)
            return {
                "videos": result.outputs if hasattr(result, "outputs") else [],
                "request_id": result.request_id,
                "status": result.status,
            }
        except Exception as e:
            logger.error(f"TextToVideoNode failed: {e}")
            return {"videos": [], "error": str(e)}

    def _resolve_video_provider(self, name: str):
        from production_workbench import ProviderType
        mapping = {
            "local": ProviderType.OMNI_GEN_LOCAL,
            "kling": ProviderType.KLING,
            "wan2_x": ProviderType.WAN2_X,
            "ltvx_2": ProviderType.LTVX_2,
            "seedance2": ProviderType.SEEDANCE2,
            "voe3_1": ProviderType.VOE3_1,
        }
        for pt in ProviderType:
            if pt.value == name or pt.name.lower() == name.lower():
                return pt
        return mapping.get(name, ProviderType.KLING)


class ImageEditNode(BaseNode):
    definition = NodeDefinition(
        node_id="gen.image_edit",
        name="图像编辑",
        category="generate",
        description="编辑/修改已有图像",
        inputs=[
            NodePort(name="image", type="image", required=True),
            NodePort(name="prompt", type="text", required=True),
        ],
        outputs=[NodePort(name="edited_image", type="image")],
        params=[NodeParam(name="provider", type="string", default="local")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from production_workbench import (
                ProviderFactory,
                ProviderType,
                ProviderConfig,
                GenerationRequest,
            )
            provider_type = ProviderType.QWEN_IMAGE_EDIT
            config = ProviderConfig(
                provider_type=provider_type,
                name=provider_type.value,
            )
            provider = ProviderFactory.create_provider(config)
            import uuid
            req = GenerationRequest(
                request_id=f"edit-{uuid.uuid4().hex[:8]}",
                prompt=inputs.get("prompt", ""),
                settings={"input_image": inputs.get("image", "")},
            )
            result = await provider.generate(req)
            return {
                "edited_image": result.outputs[0] if (hasattr(result, "outputs") and result.outputs) else "",
                "request_id": result.request_id,
                "status": result.status,
            }
        except Exception as e:
            logger.error(f"ImageEditNode failed: {e}")
            return {"edited_image": "", "error": str(e)}


class ImageUpscaleNode(BaseNode):
    definition = NodeDefinition(
        node_id="gen.image_upscale",
        name="图像放大",
        category="generate",
        description="放大图像分辨率",
        inputs=[NodePort(name="image", type="image", required=True)],
        outputs=[NodePort(name="upscaled_image", type="image")],
        params=[
            NodeParam(name="scale", type="int", default=2, min=1, max=4),
            NodeParam(name="provider", type="string", default="local"),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from production_workbench import (
                ProviderFactory,
                ProviderType,
                ProviderConfig,
                GenerationRequest,
            )
            provider_type = ProviderType.IMAGE_UPSCALE
            config = ProviderConfig(
                provider_type=provider_type,
                name=provider_type.value,
            )
            provider = ProviderFactory.create_provider(config)
            import uuid
            req = GenerationRequest(
                request_id=f"up-{uuid.uuid4().hex[:8]}",
                prompt="upscale",
                settings={
                    "input_image": inputs.get("image", ""),
                    "scale": params.get("scale", 2),
                },
            )
            result = await provider.generate(req)
            return {
                "upscaled_image": result.outputs[0] if (hasattr(result, "outputs") and result.outputs) else "",
                "request_id": result.request_id,
                "status": result.status,
            }
        except Exception as e:
            logger.error(f"ImageUpscaleNode failed: {e}")
            return {"upscaled_image": "", "error": str(e)}


class TextTo3DNode(BaseNode):
    definition = NodeDefinition(
        node_id="gen.text_to_3d",
        name="文生3D",
        category="generate",
        description="使用文本提示生成3D模型",
        inputs=[NodePort(name="prompt", type="text", required=True)],
        outputs=[NodePort(name="model", type="any")],
        params=[
            NodeParam(name="provider", type="string", default="trellis"),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from production_workbench import (
                ProviderFactory,
                ProviderType,
                ProviderConfig,
                GenerationRequest,
            )
            provider_str = params.get("provider", "trellis")
            provider_type_map = {
                "trellis": ProviderType.TRELLIS,
                "hunyuan3d": ProviderType.HUNYUAN3D,
                "triposr": ProviderType.TRIPOSR,
                "lgm": ProviderType.LGM,
            }
            provider_type = provider_type_map.get(provider_str, ProviderType.TRELLIS)
            config = ProviderConfig(
                provider_type=provider_type,
                name=provider_type.value,
            )
            provider = ProviderFactory.create_provider(config)
            import uuid
            req = GenerationRequest(
                request_id=f"3d-{uuid.uuid4().hex[:8]}",
                prompt=inputs.get("prompt", ""),
            )
            result = await provider.generate(req)
            return {
                "model": result.outputs[0] if (hasattr(result, "outputs") and result.outputs) else "",
                "request_id": result.request_id,
                "status": result.status,
            }
        except Exception as e:
            logger.error(f"TextTo3DNode failed: {e}")
            return {"model": "", "error": str(e)}


# ---- 注册 ----
registry.register(TextToImageNode)
registry.register(TextToVideoNode)
registry.register(ImageEditNode)
registry.register(ImageUpscaleNode)
registry.register(TextTo3DNode)
