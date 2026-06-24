"""
NanoBot Factory - 统一生成参数模型
整合所有生成/编辑功能的完整参数维度，作为所有API端点和后端引擎的统一参数契约
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


# ============================================================================
# 枚举类型
# ============================================================================

class GenerationType(str, Enum):
    """所有支持的生成类型"""
    # 图像生成
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    MULTI_IMAGE_TO_IMAGE = "multi_image_to_image"
    IMAGE_INPAINT = "image_inpaint"
    IMAGE_OUTPAINT = "image_outpaint"
    IMAGE_EDIT = "image_edit"
    IMAGE_VARIATION = "image_variation"
    IMAGE_UPSCALE = "image_upscale"
    STYLE_TRANSFER = "style_transfer"
    # 视频生成
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    MULTI_IMAGE_TO_VIDEO = "multi_image_to_video"
    FIRST_LAST_FRAME_TO_VIDEO = "first_last_frame_to_video"
    VIDEO_EDIT = "video_edit"
    VIDEO_STYLE_TRANSFER = "video_style_transfer"
    VIDEO_EXTEND = "video_extend"
    VIDEO_INPAINT = "video_inpaint"
    VIDEO_UPSCALE = "video_upscale"
    # 3D生成
    TEXT_TO_3D = "text_to_3d"
    IMAGE_TO_3D = "image_to_3d"
    MULTI_VIEW_TO_3D = "multi_view_to_3d"
    # 无限画布
    CANVAS_IMAGE_GEN = "canvas_image_gen"
    CANVAS_IMAGE_EDIT = "canvas_image_edit"
    CANVAS_VIDEO_GEN = "canvas_video_gen"
    CANVAS_OUTPAINT = "canvas_outpaint"


class SamplerType(str, Enum):
    EULER = "euler"
    EULER_A = "euler_a"
    EULER_K = "euler_k"
    DPM_2 = "dpm_2"
    DPM_2_A = "dpm_2_a"
    DPM_2_K = "dpm_2_k"
    DPM_2_A_K = "dpm_2_a_k"
    DPM_SOLVER = "dpm_solver"
    DPM_SOLVER_PP = "dpm_solver_pp"
    DPM_2M = "dpm++_2m"
    DPM_2M_SDE = "dpm++_2m_sde"
    DPM_2M_K = "dpm++_2m_k"
    DPM_2M_SDE_K = "dpm++_2m_sde_k"
    DPM_SDE = "dpm++_sde"
    DPM_SDE_K = "dpm++_sde_k"
    LCM = "lcm"
    DDIM = "ddim"
    UNIPC = "unipc"
    TCD = "tcd"
    HEUN = "heun"
    PNDM = "pndm"
    LMS = "lms"
    IPNDM = "ipndm"


class SchedulerType(str, Enum):
    NORMAL = "normal"
    KARRAS = "karras"
    EXPONENTIAL = "exponential"
    SIMPLE = "simple"
    SQUARED = "squared"
    DDIM_UNIFORM = "ddim_uniform"
    BETA = "beta"
    TCD = "tcd"
    LCM = "lcm"


class ControlNetType(str, Enum):
    CANNY = "canny"
    DEPTH = "depth"
    OPENPOSE = "openpose"
    SCRIBBLE = "scribble"
    MLSD = "mlsd"
    NORMAL = "normal"
    LINEART = "lineart"
    SOFTEDGE = "softedge"
    SEGMENTATION = "segmentation"
    TILE = "tile"
    INPAINT = "inpaint"
    IP2P = "ip2p"
    SHUFFLE = "shuffle"
    IP_ADAPTER = "ip_adapter"
    REVISION = "revision"


class LoraType(str, Enum):
    STANDARD = "standard"
    LYCORIS = "lycoris"
    LOHA = "loha"
    LOKR = "lokr"
    DYLORA = "dylora"


class FilterType(str, Enum):
    """滤镜/增强类型"""
    NONE = "none"
    ENHANCE = "enhance"
    SHARPEN = "sharpen"
    BLUR = "blur"
    GAUSSIAN_BLUR = "gaussian_blur"
    EDGE_ENHANCE = "edge_enhance"
    DETAIL = "detail"
    SMOOTH = "smooth"
    EMBOSS = "emboss"
    CONTOUR = "contour"
    FIND_EDGES = "find_edges"
    MAX = "max"
    MIN = "min"
    MEDIAN = "median"
    MODE = "mode"
    ANIME = "anime"
    OIL_PAINTING = "oil_painting"
    WATERCOLOR = "watercolor"
    PENCIL_SKETCH = "pencil_sketch"
    PIXELATE = "pixelate"
    CARTOON = "cartoon"
    NEON = "neon"


class MaskMode(str, Enum):
    """蒙版模式"""
    USER_DRAWN = "user_drawn"
    AI_AUTO = "ai_auto"
    COLOR_KEY = "color_key"
    DEPTH = "depth"
    SAM = "sam"
    REMOVE_BACKGROUND = "remove_background"


class VideoEditType(str, Enum):
    """视频编辑类型"""
    STYLE_TRANSFER = "style_transfer"
    INPAINT = "inpaint"
    OUTPAINT = "outpaint"
    COLOR_GRADE = "color_grade"
    REPLACE_BG = "replace_bg"
    INTERPOLATION = "interpolation"
    MOTION_BRUSH = "motion_brush"
    LIP_SYNC = "lip_sync"


class CanvasAction(str, Enum):
    """无限画布操作"""
    GEN_IMAGE = "gen_image"
    EDIT_REGION = "edit_region"
    OUTPAINT_LEFT = "outpaint_left"
    OUTPAINT_RIGHT = "outpaint_right"
    OUTPAINT_UP = "outpaint_up"
    OUTPAINT_DOWN = "outpaint_down"
    OUTPAINT_ALL = "outpaint_all"
    GEN_VIDEO = "gen_video"
    GEN_SHORT_DRAMA = "gen_short_drama"
    GEN_PICTURE_BOOK = "gen_picture_book"
    INPAINT_REGION = "inpaint_region"


class ProviderType(str, Enum):
    """支持的Provider"""
    AUTO = "auto"
    COMFYUI = "comfyui"
    DIFFUSERS = "diffusers"
    KLING = "kling"
    SEEDANCE = "seedance"
    DOUBAO = "doubao"
    MINIMAX = "minimax"
    RUNWAY = "runway"
    PIKA = "pika"
    STABILITY = "stability"
    OPENAI = "openai"
    MIDJOURNEY = "midjourney"
    HUNYUAN = "hunyuan"
    ANIMATEDIFF = "animatediff"
    SVD = "svd"
    TRIPOSR = "triposr"
    TRELLIS = "trellis"
    OMNIGEN = "omnigen"


class AspectRatioType(str, Enum):
    SQUARE_1_1 = "1:1"
    LANDSCAPE_4_3 = "4:3"
    LANDSCAPE_3_2 = "3:2"
    LANDSCAPE_16_9 = "16:9"
    LANDSCAPE_21_9 = "21:9"
    PORTRAIT_3_4 = "3:4"
    PORTRAIT_2_3 = "2:3"
    PORTRAIT_9_16 = "9:16"
    CUSTOM = "custom"


class ResolutionQuality(str, Enum):
    STANDARD = "standard"
    HD = "hd"
    FULL_HD = "full_hd"
    QHD = "qhd"
    UHD_4K = "4k"
    CUSTOM = "custom"


class StylePreset(str, Enum):
    """风格预设"""
    PHOTOREALISTIC = "photorealistic"
    CINEMATIC = "cinematic"
    ANIME = "anime"
    FANTASY = "fantasy"
    RENDER_3D = "3d_render"
    PIXEL_ART = "pixel_art"
    OIL_PAINTING = "oil_painting"
    WATERCOLOR = "watercolor"
    SKETCH = "sketch"
    CARTOON = "cartoon"
    CYBERPUNK = "cyberpunk"
    MINIMALIST = "minimalist"
    VAPORWAVE = "vaporwave"
    STUDIO_GHIBLI = "studio_ghibli"
    NOIR = "noir"
    RETRO = "retro"
    NONE = "none"


# ============================================================================
# 子参数结构
# ============================================================================

@dataclass
class LoraConfig:
    """LoRA配置"""
    model: str = ""                   # LoRA模型路径/名称
    weight: float = 1.0               # 整体权重
    clip_weight: float = 1.0          # CLIP权重
    lora_type: LoraType = LoraType.STANDARD
    trigger_words: List[str] = field(default_factory=list)


@dataclass
class ControlNetConfig:
    """ControlNet配置"""
    type: ControlNetType = ControlNetType.CANNY
    image: str = ""                    # 控制图像(base64/url)
    weight: float = 1.0               # 权重
    guidance_start: float = 0.0       # 生效开始比例
    guidance_end: float = 1.0         # 生效结束比例
    preprocessor: str = ""            # 预处理器
    control_mode: int = 0             # 0:均衡 1:提示词优先 2:controlnet优先


@dataclass
class CameraControl:
    """摄像机控制（视频生成）"""
    type: str = ""                     # none, pan_left, pan_right, pan_up, pan_down, zoom_in, zoom_out, orbit_left, orbit_right, tilt_up, tilt_down
    speed: float = 1.0                # 移动速度
    start_frame: int = 0
    end_frame: int = -1               # -1表示到最后


@dataclass
class MaskConfig:
    """蒙版配置"""
    mode: MaskMode = MaskMode.USER_DRAWN
    image: str = ""                    # 蒙版图片(base64/url)
    invert: bool = False
    feather: int = 0                  # 羽化像素
    padding: int = 0                  # 扩展像素
    auto_mask_prompt: str = ""         # AI自动蒙版提示词


@dataclass
class CanvasConfig:
    """无限画布配置"""
    action: CanvasAction = CanvasAction.GEN_IMAGE
    x: int = 0                         # 画布X坐标
    y: int = 0                         # 画布Y坐标
    width: int = 1024                  # 区域宽度
    height: int = 1024                 # 区域高度
    canvas_width: int = 2048           # 总画布宽度
    canvas_height: int = 2048          # 总画布高度
    context_images: List[str] = field(default_factory=list)  # 上下文图片
    overlap: int = 64                  # 重叠像素(用于outpaint衔接)
    seam_blend: bool = True            # 缝合处混合
    style_guidance: float = 0.8        # 风格一致性引导
    scene_transition: str = ""          # 场景转场: cut, fade, dissolve, wipe
    story_prompt: str = ""             # 短剧/绘本故事提示词
    scene_count: int = 1               # 场景数量
    character_refs: List[str] = field(default_factory=list)   # 角色参考图


@dataclass
class AnimationConfig:
    """动画配置 (AnimateDiff等)"""
    motion_module: str = ""            # 运动模块名称
    motion_scale: float = 1.0          # 运动强度
    context_length: int = 16           # 上下文帧数
    context_stride: int = 1            # 步幅
    context_overlap: int = 4           # 重叠帧
    closed_loop: bool = False          # 无缝循环
    beta_schedule: str = "linear"      # beta调度
    ip_adapter_weight: float = 0.0     # IP-Adapter权重
    latent_power: float = 1.0
    loop_count: int = 1
    generator_loss_type: str = "l2"    # 生成器loss类型


@dataclass
class VideoEnhanceConfig:
    """视频增强配置"""
    upscale_factor: int = 2            # 放大倍数
    frame_interpolation: bool = False  # 是否插帧
    target_fps: int = 0                # 目标帧率(0=不变)
    denoise: bool = True
    deblur: bool = False
    color_grade: bool = False
    stabilize: bool = False            # 防抖
    slow_motion: bool = False          # 慢动作


# ============================================================================
# 统一生成参数 - 完整版
# 整合所有生成/编辑类型所需的所有参数维度
# ============================================================================

@dataclass
class UnifiedGenerationParams:
    """统一生成参数——一个模型覆盖所有生成/编辑类型的完整参数"""

    # ========================================================================
    # 基础参数
    # ========================================================================
    generation_type: GenerationType = GenerationType.TEXT_TO_IMAGE
    provider: ProviderType = ProviderType.AUTO
    model: str = ""                    # 具体模型名称(如sd_xl_base_1.0, flux_dev等)
    prompt: str = ""
    negative_prompt: str = ""

    # ========================================================================
    # 图像基础参数
    # ========================================================================
    width: int = 1024
    height: int = 1024
    steps: int = 28
    cfg_scale: float = 7.0
    seed: int = -1
    sampler: SamplerType = SamplerType.EULER_A
    scheduler: SchedulerType = SchedulerType.KARRAS

    # 批量
    batch_count: int = 1              # 每次生成的图片/视频数量
    batch_size: int = 1               # 每个batch内的并行数

    # 图像质量
    clip_skip: int = 0                # 0=不跳过
    eta: float = 0.0                  # eta参数(DDIM相关)
    guidance_rescale: float = 0.0     # 引导重缩放
    style_preset: StylePreset = StylePreset.NONE

    # 高分辨率修复
    enable_hr: bool = False
    hr_scale: float = 2.0
    hr_upscaler: str = ""
    hr_second_pass_steps: int = 0
    denoising_strength: float = 0.4

    # VAE
    vae: str = ""                     # VAE模型名称
    vae_tiling: bool = False

    # ========================================================================
    # LoRA 参数
    # ========================================================================
    loras: List[LoraConfig] = field(default_factory=list)

    # ========================================================================
    # ControlNet / IP-Adapter 参数
    # ========================================================================
    controlnet: List[ControlNetConfig] = field(default_factory=list)

    # ========================================================================
    # 图像输入参数（图生图/编辑）
    # ========================================================================
    input_images: List[str] = field(default_factory=list)   # 输入图片(base64/url)
    source_image: str = ""             # 编辑源图片
    mask: MaskConfig = field(default_factory=MaskConfig)    # 蒙版配置
    strength: float = 0.75             # 图生图/编辑强度(0-1)

    # 编辑类型
    edit_type: str = ""                # inpaint, outpaint, style_transfer, replace_bg 等
    edit_prompt: str = ""              # 编辑区域的新内容描述

    # 滤镜/增强
    filter_type: FilterType = FilterType.NONE
    filter_strength: float = 1.0

    # 放大
    upscale_model: str = "realesrgan_x4plus"
    upscale_scale: int = 2            # 放大倍数
    face_enhance: bool = False        # 人脸增强
    tile_size: int = 512              # 分块大小
    tile_pad: int = 32                # 分块边距

    # 色彩校正
    brightness: float = 1.0           # 亮度
    contrast: float = 1.0             # 对比度
    saturation: float = 1.0           # 饱和度
    vibrance: float = 1.0             # 自然饱和度
    temperature: float = 0.0          # 色温(-100~100)
    tint: float = 0.0                 # 色调(-100~100)
    exposure: float = 0.0             # 曝光补偿
    highlights: float = 0.0           # 高光
    shadows: float = 0.0              # 阴影

    # ========================================================================
    # 视频参数
    # ========================================================================
    duration: int = 5                 # 视频时长(秒)
    fps: int = 24                     # 视频帧率
    video_frames: int = 0             # 总帧数(0=由duration*fps计算)
    first_frame: str = ""              # 首帧(首尾帧生成)
    last_frame: str = ""              # 尾帧(首尾帧生成)
    reference_images: List[str] = field(default_factory=list)  # 参考图(多图参考)
    audio_url: str = ""               # 音频(配音/音效)

    # 视频编辑
    video_source: str = ""            # 源视频(视频编辑)
    video_edit_type: VideoEditType = VideoEditType.STYLE_TRANSFER
    video_enhance: VideoEnhanceConfig = field(default_factory=VideoEnhanceConfig)

    # 摄像机运动
    camera: CameraControl = field(default_factory=CameraControl)

    # 循环
    loop: bool = False                # 无缝循环
    single_loop: bool = False         # 单次循环(Kling)

    # 运动控制
    motion_bucket_id: int = 127       # SVD运动强度(1-255)
    motion_intensity: float = 0.5     # 通用运动强度(0-1)
    noise_aug_strength: float = 0.02  # 噪声增强(图生视频)
    augmentation_level: float = 0.0   # 增强级别

    # 动画(AnimateDiff)
    animation: AnimationConfig = field(default_factory=AnimationConfig)

    # ========================================================================
    # 3D参数
    # ========================================================================
    export_format: str = "glb"        # obj/glb/stl/ply/usdz
    texture_resolution: int = 2048    # 纹理分辨率
    mesh_simplification: float = 0.0  # 网格简化(0-1)
    remove_background: bool = True    # 移除背景
    num_views: int = 6                # 多视角数量(Zero123++)
    shape_resolution: int = 256       # 形状分辨率(Hunyuan3D)
    marching_cubes_resolution: int = 128  # MC分辨率(TripoSR)

    # ========================================================================
    # 无限画布参数
    # ========================================================================
    canvas: CanvasConfig = field(default_factory=CanvasConfig)

    # ========================================================================
    # 其他高级参数
    # ========================================================================
    aspect_ratio: AspectRatioType = AspectRatioType.CUSTOM
    quality: ResolutionQuality = ResolutionQuality.STANDARD
    extra_params: Dict[str, Any] = field(default_factory=dict)

    # 生成策略
    use_progressive: bool = False      # 渐进式生成
    progressive_start: float = 0.0     # 渐进开始比例
    progressive_end: float = 1.0       # 渐进结束比例

    # 回调
    callback_url: str = ""
    user_id: str = ""
    project_id: str = ""


# ============================================================================
# 快捷方法
# ============================================================================

def params_to_diffuser(params: UnifiedGenerationParams) -> Dict[str, Any]:
    """将统一参数转换为diffuser_engine的GenerationParams兼容字典"""
    d = {
        "prompt": params.prompt,
        "negative_prompt": params.negative_prompt,
        "width": params.width,
        "height": params.height,
        "steps": params.steps,
        "cfg_scale": params.cfg_scale,
        "seed": params.seed,
        "num_images": params.batch_count,
        "sampler": params.sampler.value if hasattr(params.sampler, 'value') else str(params.sampler),
        "scheduler": params.scheduler.value if hasattr(params.scheduler, 'value') else str(params.scheduler),
        "strength": params.strength,
        "guidance_start": 0.0,
        "guidance_end": 1.0,
        "lora_paths": [l.model for l in params.loras],
        "lora_weights": [l.weight for l in params.loras],
        "lora_clip_weights": [l.clip_weight for l in params.loras],
        "controlnet_paths": [c.type.value for c in params.controlnet],
        "controlnet_weights": [c.weight for c in params.controlnet],
        "control_images": [c.image for c in params.controlnet],
        "control_guidance_start": [c.guidance_start for c in params.controlnet],
        "control_guidance_end": [c.guidance_end for c in params.controlnet],
        "vae_path": params.vae or None,
        "vae_slice_size": 4,
        "video_frames": params.video_frames or (params.duration * params.fps),
        "video_fps": params.fps,
        "enable_attention_slicing": True,
        "enable_vae_slicing": True,
        "enable_cpu_offload": False,
        "enable_xformers": True,
        "clip_skip": params.clip_skip,
        "guidance_scale_min": 1.0,
    }
    return d


def params_to_unified_service(params: UnifiedGenerationParams) -> Dict[str, Any]:
    """将统一参数转换为unified_generation_service的GenerationRequest兼容字典"""
    return {
        "generation_type": params.generation_type.value,
        "prompt": params.prompt,
        "negative_prompt": params.negative_prompt,
        "model": params.model,
        "width": params.width,
        "height": params.height,
        "steps": params.steps,
        "cfg_scale": params.cfg_scale,
        "seed": params.seed,
        "sampler": params.sampler.value if hasattr(params.sampler, 'value') else str(params.sampler),
        "scheduler": params.scheduler.value if hasattr(params.scheduler, 'value') else str(params.scheduler),
        "duration": params.duration,
        "fps": params.fps,
        "reference_images": params.reference_images,
        "source_image": params.source_image,
        "first_frame": params.first_frame,
        "last_frame": params.last_frame,
        "edit_type": params.edit_type,
        "mask_image": params.mask.image,
        "strength": params.strength,
        "audio_url": params.audio_url,
    }


def params_to_kling(params: UnifiedGenerationParams) -> Dict[str, Any]:
    """将统一参数转换为Kling API参数"""
    d = {
        "prompt": params.prompt,
        "negative_prompt": params.negative_prompt,
        "duration": params.duration,
        "cfg_scale": params.cfg_scale,
        "seed": params.seed if params.seed >= 0 else None,
        "mode": "pro",
    }
    if params.width and params.height:
        d["width"] = params.width
        d["height"] = params.height
    if params.camera.type:
        d["camera_control"] = {"type": params.camera.type}
    if params.loop:
        d["single_loop"] = 0
    return d


def params_to_seedance(params: UnifiedGenerationParams) -> Dict[str, Any]:
    """将统一参数转换为Seedance API参数"""
    d = {
        "prompt": params.prompt,
        "negative_prompt": params.negative_prompt,
        "duration": params.duration,
        "seed": params.seed if params.seed >= 0 else None,
        "cfg_scale": params.cfg_scale,
        "style_preset": params.style_preset.value if params.style_preset != StylePreset.NONE else "",
    }
    if params.first_frame:
        d["image"] = params.first_frame
    if params.last_frame:
        d["image_tail"] = params.last_frame
    if params.reference_images:
        d["reference_images"] = params.reference_images
    return d


def params_to_comfyui(params: UnifiedGenerationParams) -> Dict[str, Any]:
    """将统一参数转换为ComfyUI workflow prompt - 完整节点映射"""
    import json
    workflow = {}
    node_counter = [0]
    def nid(): node_counter[0] += 1; return str(node_counter[0])

    # 基础CLIP编码
    clip_pos = nid(); clip_neg = nid()
    workflow[clip_pos] = {"class_type": "CLIPTextEncode", "inputs": {"text": params.prompt}}
    workflow[clip_neg] = {"class_type": "CLIPTextEncode", "inputs": {"text": params.negative_prompt}}

    # 模型加载
    model_nid = nid()
    if params.model:
        workflow[model_nid] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": params.model}}
    else:
        workflow[model_nid] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}}

    # VAE加载
    vae_nid = None
    if params.vae:
        vae_nid = nid()
        workflow[vae_nid] = {"class_type": "VAELoader", "inputs": {"vae_name": params.vae}}

    # LoRA加载链
    lora_chain_model = model_nid
    lora_chain_clip = clip_pos
    if params.loras:
        for i, lora in enumerate(params.loras):
            lora_nid = nid()
            workflow[lora_nid] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora.model,
                    "strength_model": lora.weight,
                    "strength_clip": lora.clip_weight,
                    "model": [lora_chain_model, 0],
                    "clip": [lora_chain_clip, 0],
                }
            }
            lora_chain_model = lora_nid
            lora_chain_clip = lora_nid

    # CLIP Skip
    clip_final = lora_chain_clip
    if params.clip_skip > 0:
        skip_nid = nid()
        workflow[skip_nid] = {
            "class_type": "CLIPSetLastLayer",
            "inputs": {"stop_at_clip_layer": -abs(params.clip_skip), "clip": [clip_final, 0]}
        }
        clip_final = skip_nid

    # ControlNet加载与应用
    cond_model = lora_chain_model
    cond_pos = clip_final
    if params.controlnet:
        for i, cn in enumerate(params.controlnet):
            cn_load_nid = nid()
            cn_type = cn.type.value if hasattr(cn.type, 'value') else cn.type
            workflow[cn_load_nid] = {
                "class_type": "ControlNetLoader",
                "inputs": {"control_net_name": f"{cn_type}.safetensors", "strength": cn.weight}
            }
            cn_apply_nid = nid()
            workflow[cn_apply_nid] = {
                "class_type": "ControlNetApply",
                "inputs": {
                    "strength": cn.weight,
                    "start_percent": cn.guidance_start,
                    "end_percent": cn.guidance_end,
                    "conditioning": [cond_pos, 0],
                    "control_net": [cn_load_nid, 0],
                    "image": None,  # 由外部提供
                }
            }
            cond_pos = cn_apply_nid

    # IP-Adapter (通过CLIPVision + IPAdapterApply)
    if any(cn.type.value in ("ip_adapter", "revision") for cn in params.controlnet if hasattr(cn.type, 'value')):
        ip_nid = nid()
        workflow[ip_nid] = {
            "class_type": "IPAdapterApply",
            "inputs": {"weight": 0.5, "model": [cond_model, 0], "ipadapter": [], "clip_vision": []}
        }

    # 空Latent / 视频Latent
    latent_nid = nid()
    if params.video_frames > 1 or params.generation_type in ("text_to_video", "image_to_video"):
        workflow[latent_nid] = {
            "class_type": "EmptyLatentVideo",
            "inputs": {"width": params.width, "height": params.height, "batch_size": params.video_frames or 16, "length": params.video_frames or 16}
        }
    else:
        workflow[latent_nid] = {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": params.width, "height": params.height, "batch_size": params.batch_count}
        }

    # 图生图: 用VAE Encode输入图
    vae_encode_nid = None
    if params.input_images or params.source_image:
        load_img_nid = nid()
        workflow[load_img_nid] = {"class_type": "LoadImage", "inputs": {"image": params.source_image or (params.input_images[0] if params.input_images else "")}}
        vae_encode_nid = nid()
        workflow[vae_encode_nid] = {"class_type": "VAEEncode", "inputs": {"pixels": [load_img_nid, 0], "vae": [vae_nid, 0]} if vae_nid else {"pixels": [load_img_nid, 0]}}
        latent_nid = vae_encode_nid

    # Inpaint: 加VAE Encode (mask)
    if params.edit_type == "inpaint" and params.mask.image:
        mask_nid = nid()
        workflow[mask_nid] = {"class_type": "LoadImage", "inputs": {"image": params.mask.image}}
        set_mask_nid = nid()
        workflow[set_mask_nid] = {"class_type": "SetLatentNoiseMask", "inputs": {"mask": [mask_nid, 0], "latent": [latent_nid, 0]}}
        latent_nid = set_mask_nid

    # KSamper (核心采样)
    sampler_nid = nid()
    sampler_name = params.sampler.value if hasattr(params.sampler, 'value') else str(params.sampler)
    scheduler_name = params.scheduler.value if hasattr(params.scheduler, 'value') else str(params.scheduler)
    workflow[sampler_nid] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": params.seed if params.seed >= 0 else 42,
            "steps": params.steps,
            "cfg": params.cfg_scale,
            "sampler_name": sampler_name,
            "scheduler": scheduler_name,
            "denoise": params.strength if params.strength < 1.0 or vae_encode_nid else 1.0,
            "model": [cond_model, 0],
            "positive": [cond_pos, 0],
            "negative": [clip_final, 0] if clip_final != cond_pos else [clip_neg, 0],
            "latent_image": [latent_nid, 0],
        }
    }

    # AnimateDiff 集成
    if params.animation.motion_module or params.video_frames > 16:
        ad_nid = nid()
        workflow[ad_nid] = {
            "class_type": "AnimateDiffLoaderWithContext",
            "inputs": {
                "model": [cond_model, 0],
                "latent": [latent_nid, 0],
                "motion_module": params.animation.motion_module or "mm_sd_v15_v2.ckpt",
                "motion_scale": params.animation.motion_scale,
                "context_length": params.animation.context_length,
                "context_stride": params.animation.context_stride,
                "context_overlap": params.animation.context_overlap,
                "closed_loop": params.animation.closed_loop,
                "beta_schedule": params.animation.beta_schedule,
                "loop_count": params.animation.loop_count,
            }
        }

    # VAE Decode (输出)
    decode_nid = nid()
    vae_for_decode = vae_nid
    if vae_for_decode:
        workflow[decode_nid] = {"class_type": "VAEDecode", "inputs": {"samples": [sampler_nid, 0], "vae": [vae_for_decode, 0]}}
    else:
        workflow[decode_nid] = {"class_type": "VAEDecode", "inputs": {"samples": [sampler_nid, 0]}}

    # 图像保存
    save_nid = nid()
    workflow[save_nid] = {"class_type": "SaveImage", "inputs": {"images": [decode_nid, 0], "filename_prefix": "nanobot_"}}

    # 视频: 用VHS VideoCombine
    if params.video_frames > 1:
        video_nid = nid()
        workflow[video_nid] = {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": [decode_nid, 0],
                "frame_rate": params.fps or 24,
                "loop_count": 0 if params.loop else 1,
                "filename_prefix": "nanobot_video_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            }
        }

    return {"prompt": workflow}
