"""
IMDF Node Registry — node type registration + lookup
====================================================
Singleton registry that auto-discovers the 47 node types
defined in the frontend NT object and makes them available
to the DAG engine and workflow API.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


# ─── Port / Param definitions ────────────────────────────────────────────────

@dataclass
class PortDef:
    """Single port definition (input or output)."""
    name: str = ""
    type: str = "any"           # any / image / video / text / audio / 3d
    description: str = ""
    required: bool = True


@dataclass
class ParamDef:
    """Single parameter definition for a node type."""
    name: str = ""
    type: str = "string"        # string / int / float / bool / select / json
    label: str = ""
    default: Any = None
    options: List[str] = field(default_factory=list)  # for select type
    description: str = ""


@dataclass
class NodeDef:
    """Complete definition of a node type."""
    type: str = ""
    category: str = ""          # dimension / capability / function
    label: str = ""
    icon: str = ""
    color: str = ""
    inputs: List[PortDef] = field(default_factory=list)
    outputs: List[PortDef] = field(default_factory=list)
    params: List[ParamDef] = field(default_factory=list)
    description: str = ""


# ─── Node Registry ───────────────────────────────────────────────────────────

class NodeRegistry:
    """
    Singleton registry for all node types.
    
    Auto-discovers from the 47 frontend NT definitions.
    Usage:
        NodeRegistry.initialize()       # one-time setup
        nd = NodeRegistry.get('llm')    # get NodeDef by type
        cats = NodeRegistry.list_by_category('dimension')
    """

    _instance = None
    _registry: Dict[str, NodeDef] = {}
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def initialize(cls):
        """Auto-register all 47 node types from the frontend NT definitions."""
        if cls._initialized:
            return

        # ── Dimension nodes (data types) ────────────────────────────────
        dimension_nodes = {
            "text": NodeDef(
                type="text", category="dimension", label="文本", icon="📝", color="#2d5d2d",
                inputs=[PortDef(name="in_0", type="any")],
                outputs=[PortDef(name="out_0", type="text")],
                params=[ParamDef(name="content", type="string", label="内容", default="双击编辑")],
                description="文本节点 — 输入或显示文本内容",
            ),
            "image": NodeDef(
                type="image", category="dimension", label="图片", icon="🖼", color="#3d2d6d",
                inputs=[PortDef(name="in_0", type="any")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="src", type="string", label="图片源", default="")],
                description="图片节点 — 图像数据输入/输出",
            ),
            "video": NodeDef(
                type="video", category="dimension", label="视频", icon="🎬", color="#2d4d6d",
                inputs=[PortDef(name="in_0", type="any")],
                outputs=[PortDef(name="out_0", type="video")],
                params=[ParamDef(name="src", type="string", label="视频源", default=""),
                        ParamDef(name="dur", type="float", label="时长(秒)", default=5.0)],
                description="视频节点 — 视频数据输入/输出",
            ),
            "audio": NodeDef(
                type="audio", category="dimension", label="音频", icon="🎵", color="#2d5d5d",
                inputs=[PortDef(name="in_0", type="any")],
                outputs=[PortDef(name="out_0", type="audio")],
                params=[ParamDef(name="src", type="string", label="音频源", default=""),
                        ParamDef(name="dur", type="float", label="时长(秒)", default=10.0)],
                description="音频节点 — 音频数据输入/输出",
            ),
            "model3d": NodeDef(
                type="model3d", category="dimension", label="3D", icon="🎯", color="#2d3d4d",
                inputs=[PortDef(name="in_0", type="any")],
                outputs=[PortDef(name="out_0", type="3d")],
                params=[ParamDef(name="model", type="string", label="3D模型", default=""),
                        ParamDef(name="pose", type="string", label="姿态", default="standing")],
                description="3D模型节点 — 三维模型数据输入/输出",
            ),
            "output": NodeDef(
                type="output", category="dimension", label="输出", icon="💾", color="#4d3d2d",
                inputs=[PortDef(name="in_0", type="any")],
                outputs=[],
                params=[ParamDef(name="fmt", type="select", label="格式", default="mp4",
                                options=["mp4", "png", "jpg", "txt", "html", "pdf"])],
                description="输出节点 — 工作流最终输出",
            ),
        }

        # ── Capability nodes (AI generation / processing) ───────────────
        capability_nodes = {
            "llm": NodeDef(
                type="llm", category="capability", label="AI对话", icon="🤖", color="#6d2d4d",
                inputs=[PortDef(name="in_0", type="text", description="提示词输入"),
                        PortDef(name="in_1", type="any", description="上下文输入")],
                outputs=[PortDef(name="out_0", type="text", description="AI回复")],
                params=[ParamDef(name="prompt", type="string", label="提示词", default=""),
                        ParamDef(name="model", type="string", label="模型", default="auto")],
                description="AI对话节点 — 调用大语言模型进行对话",
            ),
            "comfyui": NodeDef(
                type="comfyui", category="capability", label="ComfyUI", icon="⚡", color="#4d2d4d",
                inputs=[PortDef(name="in_0", type="any", description="参数输入"),
                        PortDef(name="in_1", type="any", description="图片输入")],
                outputs=[PortDef(name="out_0", type="image", description="生成图片"),
                        PortDef(name="out_1", type="image", description="附加输出")],
                params=[ParamDef(name="workflow", type="json", label="Workflow JSON", default="")],
                description="ComfyUI节点 — 运行ComfyUI工作流",
            ),
            "ppt": NodeDef(
                type="ppt", category="capability", label="PPT", icon="📊", color="#3d4d2d",
                inputs=[PortDef(name="in_0", type="text", description="内容输入")],
                outputs=[PortDef(name="out_0", type="any", description="生成的PPT")],
                params=[ParamDef(name="title", type="string", label="标题", default="新建PPT"),
                        ParamDef(name="tpl", type="select", label="模板", default="clean-business",
                                options=["clean-business", "dark-tech", "minimal"]),
                        ParamDef(name="slides", type="int", label="页数", default=5)],
                description="PPT生成节点 — 自动生成演示文稿",
            ),
            "script": NodeDef(
                type="script", category="capability", label="脚本", icon="🔧", color="#2d4d4d",
                inputs=[PortDef(name="in_0", type="any", description="输入数据")],
                outputs=[PortDef(name="out_0", type="any", description="脚本输出")],
                params=[ParamDef(name="code", type="string", label="脚本代码", default="return input;")],
                description="脚本节点 — 运行自定义Python/JS脚本",
            ),
            # ── Image processing capabilities ──
            "imgedit": NodeDef(
                type="imgedit", category="capability", label="图片编辑", icon="🎨", color="#5d2d6d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="action", type="select", label="操作", default="裁剪",
                                options=["裁剪", "旋转", "翻转", "调色", "滤镜"])],
                description="图片编辑节点 — 基础图片处理操作",
            ),
            "upscale": NodeDef(
                type="upscale", category="capability", label="放大", icon="🔍", color="#4d3d5d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="scale", type="float", label="放大倍数", default=2.0)],
                description="图片放大节点 — AI超分辨率放大",
            ),
            "removebg": NodeDef(
                type="removebg", category="capability", label="去背景", icon="✂️", color="#5d5d3d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="color", type="select", label="背景色", default="green",
                                options=["green", "white", "transparent", "blue"])],
                description="去背景节点 — 自动移除图片背景",
            ),
            "rmwatermark": NodeDef(
                type="rmwatermark", category="capability", label="去水印", icon="🚫", color="#5d4d3d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="method", type="select", label="方法", default="auto",
                                options=["auto", "inpaint", "crop"])],
                description="去水印节点 — 自动检测并移除水印",
            ),
            "topazimg": NodeDef(
                type="topazimg", category="capability", label="Topaz图片", icon="✨", color="#5d4d3d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="model", type="select", label="模型", default="standard",
                                options=["standard", "high-quality", "denoise"])],
                description="Topaz图片增强 — Topaz AI图片质量提升",
            ),
            # ── Video processing capabilities ──
            "videoedit": NodeDef(
                type="videoedit", category="capability", label="视频编辑", icon="✂️", color="#2d5d6d",
                inputs=[PortDef(name="in_0", type="video")],
                outputs=[PortDef(name="out_0", type="video")],
                params=[ParamDef(name="action", type="select", label="操作", default="裁剪",
                                options=["裁剪", "拼接", "添加字幕", "变速"])],
                description="视频编辑节点 — 视频裁剪/拼接等操作",
            ),
            "topazvid": NodeDef(
                type="topazvid", category="capability", label="Topaz视频", icon="🌟", color="#5d4d5d",
                inputs=[PortDef(name="in_0", type="video")],
                outputs=[PortDef(name="out_0", type="video")],
                params=[ParamDef(name="model", type="select", label="模型", default="standard",
                                options=["standard", "motion-blur", "low-light"])],
                description="Topaz视频增强 — AI驱动视频质量提升",
            ),
            # ── AI generation extension capabilities ──
            "seedance": NodeDef(
                type="seedance", category="capability", label="Seedance", icon="🎭", color="#6d3d4d",
                inputs=[PortDef(name="in_0", type="text", description="提示词"),
                        PortDef(name="in_1", type="image", description="参考图")],
                outputs=[PortDef(name="out_0", type="video", description="生成视频")],
                params=[ParamDef(name="prompt", type="string", label="提示词", default=""),
                        ParamDef(name="model", type="string", label="模型", default="seedance2")],
                description="Seedance视频生成 — AI文本/图片生成视频",
            ),
            "runninghub": NodeDef(
                type="runninghub", category="capability", label="RunningHub", icon="🏃", color="#6d4d3d",
                inputs=[PortDef(name="in_0", type="any", description="输入参数"),
                        PortDef(name="in_1", type="any", description="附加输入")],
                outputs=[PortDef(name="out_0", type="any", description="结果输出")],
                params=[ParamDef(name="endpoint", type="string", label="端点", default=""),
                        ParamDef(name="params", type="json", label="参数", default="{}")],
                description="RunningHub节点 — 接入RunningHub多模型服务",
            ),
            "portrait": NodeDef(
                type="portrait", category="capability", label="人像大师", icon="👤", color="#6d2d5d",
                inputs=[PortDef(name="in_0", type="text", description="描述"),
                        PortDef(name="in_1", type="image", description="参考图")],
                outputs=[PortDef(name="out_0", type="image", description="人像图片")],
                params=[ParamDef(name="gender", type="select", label="性别", default="女",
                                options=["男", "女", "不限"]),
                        ParamDef(name="style", type="select", label="风格", default="写实",
                                options=["写实", "二次元", "油画", "素描"])],
                description="人像大师 — AI人像生成与风格化",
            ),
            "falbox": NodeDef(
                type="falbox", category="capability", label="Fal模型", icon="🔮", color="#5d3d4d",
                inputs=[PortDef(name="in_0", type="text", description="提示词"),
                        PortDef(name="in_1", type="image", description="参考图")],
                outputs=[PortDef(name="out_0", type="any", description="模型输出")],
                params=[ParamDef(name="endpoint", type="string", label="端点", default=""),
                        ParamDef(name="key", type="string", label="API Key", default="")],
                description="Fal模型节点 — 接入fal.ai模型服务",
            ),
            "rhtools": NodeDef(
                type="rhtools", category="capability", label="RH工具箱", icon="🧰", color="#5d4d4d",
                inputs=[PortDef(name="in_0", type="any", description="输入"),
                        PortDef(name="in_1", type="any", description="附加")],
                outputs=[PortDef(name="out_0", type="any", description="结果"),
                        PortDef(name="out_1", type="any", description="日志")],
                params=[ParamDef(name="tool", type="string", label="工具", default=""),
                        ParamDef(name="params", type="json", label="参数", default="{}")],
                description="RH工具箱 — RunningHub工具集",
            ),
            "grok": NodeDef(
                type="grok", category="capability", label="Grok", icon="🐦", color="#4d3d6d",
                inputs=[PortDef(name="in_0", type="text", description="输入文本")],
                outputs=[PortDef(name="out_0", type="text", description="回复")],
                params=[ParamDef(name="prompt", type="string", label="提示词", default=""),
                        ParamDef(name="model", type="string", label="模型", default="grok")],
                description="Grok节点 — xAI Grok模型对话",
            ),
            "prelabel": NodeDef(
                type="prelabel", category="capability", label="AI预标注", icon="🎯", color="#9B59B6",
                inputs=[PortDef(name="in_0", type="image", description="输入图片")],
                outputs=[PortDef(name="out_0", type="any", description="标注结果"),
                        PortDef(name="out_1", type="text", description="日志输出")],
                params=[ParamDef(name="prompt", type="string", label="图片描述", default=""),
                        ParamDef(name="task_type", type="select", label="任务类型", default="detection",
                                options=["detection", "classification", "tagging"])],
                description="AI预标注节点 — 自动标注图片中的目标",
            ),
        }

        # ── Function nodes (utility / control flow) ─────────────────────
        function_nodes = {
            "upload": NodeDef(
                type="upload", category="function", label="上传", icon="📤", color="#3d5d4d",
                inputs=[],
                outputs=[PortDef(name="out_0", type="any", description="上传的数据")],
                params=[ParamDef(name="path", type="string", label="路径", default="")],
                description="上传节点 — 上传文件到工作流",
            ),
            "textsplit": NodeDef(
                type="textsplit", category="function", label="文本分割", icon="✂️", color="#4d5d4d",
                inputs=[PortDef(name="in_0", type="text", description="输入文本")],
                outputs=[PortDef(name="out_0", type="text", description="分割结果")],
                params=[ParamDef(name="delimiter", type="string", label="分隔符", default="\\n")],
                description="文本分割节点 — 按分隔符分割文本",
            ),
            "mention": NodeDef(
                type="mention", category="function", label="@引用", icon="🔗", color="#3d4d4d",
                inputs=[PortDef(name="in_0", type="any", description="引用目标")],
                outputs=[PortDef(name="out_0", type="any", description="引用数据")],
                params=[ParamDef(name="ref", type="string", label="引用", default="")],
                description="@引用节点 — 引用画布中其他元素的数据",
            ),
            "loop": NodeDef(
                type="loop", category="function", label="循环", icon="🔄", color="#4d4d4d",
                inputs=[PortDef(name="in_0", type="any", description="迭代数据")],
                outputs=[PortDef(name="out_0", type="any", description="循环输出")],
                params=[ParamDef(name="count", type="int", label="循环次数", default=3)],
                description="循环节点 — 对输入数据进行迭代处理",
            ),
            "relay": NodeDef(
                type="relay", category="function", label="中继", icon="🔁", color="#3d3d4d",
                inputs=[PortDef(name="in_0", type="any", description="输入")],
                outputs=[PortDef(name="out_0", type="any", description="输出")],
                params=[ParamDef(name="target", type="string", label="目标", default="")],
                description="中继节点 — 数据中继转发",
            ),
            "groupbox": NodeDef(
                type="groupbox", category="function", label="分组", icon="📦", color="#4d4d5d",
                inputs=[PortDef(name="in_0", type="any", description="输入1"),
                        PortDef(name="in_1", type="any", description="输入2")],
                outputs=[PortDef(name="out_0", type="any", description="分组输出")],
                params=[ParamDef(name="label", type="string", label="组名", default="组")],
                description="分组节点 — 将多个输入分组",
            ),
            "browser": NodeDef(
                type="browser", category="function", label="浏览器", icon="🌐", color="#2d3d5d",
                inputs=[PortDef(name="in_0", type="text", description="URL或指令")],
                outputs=[PortDef(name="out_0", type="any", description="页面内容")],
                params=[ParamDef(name="url", type="string", label="URL", default="https://")],
                description="浏览器节点 — 网页浏览与数据采集",
            ),
            "aggregate": NodeDef(
                type="aggregate", category="function", label="聚合解析", icon="🔀", color="#4d3d4d",
                inputs=[PortDef(name="in_0", type="any", description="数据源1"),
                        PortDef(name="in_1", type="any", description="数据源2")],
                outputs=[PortDef(name="out_0", type="any", description="聚合结果")],
                params=[ParamDef(name="mode", type="select", label="模式", default="合并",
                                options=["合并", "交叉", "去重", "排序"])],
                description="聚合解析节点 — 多数据源聚合分析",
            ),
            "drawboard": NodeDef(
                type="drawboard", category="function", label="绘图板", icon="✏️", color="#3d5d5d",
                inputs=[PortDef(name="in_0", type="any", description="参考输入")],
                outputs=[PortDef(name="out_0", type="image", description="绘图输出")],
                params=[ParamDef(name="strokes", type="json", label="笔画数据", default="[]")],
                description="绘图板节点 — 手动绘制或标注",
            ),
            "storygrid": NodeDef(
                type="storygrid", category="function", label="故事板", icon="📋", color="#4d5d3d",
                inputs=[PortDef(name="in_0", type="any", description="内容输入")],
                outputs=[PortDef(name="out_0", type="any", description="故事板输出")],
                params=[ParamDef(name="scenes", type="int", label="场景数", default=5)],
                description="故事板节点 — 生成故事板编排",
            ),
            "combine": NodeDef(
                type="combine", category="function", label="合并", icon="🔗", color="#3d4d5d",
                inputs=[PortDef(name="in_0", type="any", description="数据1"),
                        PortDef(name="in_1", type="any", description="数据2")],
                outputs=[PortDef(name="out_0", type="any", description="合并结果")],
                params=[ParamDef(name="mode", type="select", label="模式", default="拼接",
                                options=["拼接", "叠加", "混合"])],
                description="合并节点 — 多路数据合并输出",
            ),
            # ── 3D / layout functions ──
            "panorama": NodeDef(
                type="panorama", category="function", label="全景3D", icon="🌍", color="#2d3d5d",
                inputs=[PortDef(name="in_0", type="image", description="全景图输入")],
                outputs=[PortDef(name="out_0", type="3d", description="3D场景")],
                params=[ParamDef(name="scene", type="string", label="场景", default=""),
                        ParamDef(name="quality", type="select", label="质量", default="high",
                                options=["low", "medium", "high"])],
                description="全景3D节点 — 生成360度全景3D场景",
            ),
            "posemaster": NodeDef(
                type="posemaster", category="function", label="姿势大师", icon="🧍", color="#3d3d5d",
                inputs=[PortDef(name="in_0", type="image", description="参考图")],
                outputs=[PortDef(name="out_0", type="any", description="姿态数据")],
                params=[ParamDef(name="pose", type="string", label="姿态", default="standing")],
                description="姿势大师节点 — 人体姿态检测与控制",
            ),
            "materialset": NodeDef(
                type="materialset", category="function", label="素材集", icon="🗂️", color="#4d4d3d",
                inputs=[PortDef(name="in_0", type="any", description="素材输入")],
                outputs=[PortDef(name="out_0", type="any", description="素材集输出")],
                params=[ParamDef(name="items", type="json", label="素材列表", default="[]")],
                description="素材集节点 — 管理和组织素材集合",
            ),
            "pickfromset": NodeDef(
                type="pickfromset", category="function", label="从集选择", icon="🎯", color="#3d4d3d",
                inputs=[PortDef(name="in_0", type="any", description="素材集")],
                outputs=[PortDef(name="out_0", type="any", description="选择结果")],
                params=[ParamDef(name="options", type="json", label="选项", default="[]")],
                description="从集选择节点 — 从素材集中选择特定项",
            ),
            # ── Utility functions ──
            "idea": NodeDef(
                type="idea", category="function", label="灵感", icon="💡", color="#5d5d4d",
                inputs=[],
                outputs=[PortDef(name="out_0", type="text", description="灵感文本")],
                params=[ParamDef(name="note", type="string", label="灵感笔记", default="")],
                description="灵感节点 — 记录创意灵感",
            ),
            "placeholder": NodeDef(
                type="placeholder", category="function", label="占位", icon="⬜", color="#3d3d3d",
                inputs=[],
                outputs=[PortDef(name="out_0", type="any", description="占位输出")],
                params=[ParamDef(name="text", type="string", label="占位文本", default="占位")],
                description="占位节点 — 工作流占位符",
            ),
            # ── Additional image utilities ──
            "gridcrop": NodeDef(
                type="gridcrop", category="function", label="网格裁剪", icon="🔲", color="#5d2d5d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="rows", type="int", label="行数", default=3),
                        ParamDef(name="cols", type="int", label="列数", default=3)],
                description="网格裁剪节点 — 按网格批量裁剪图片",
            ),
            "gridedit": NodeDef(
                type="gridedit", category="function", label="网格编辑", icon="📐", color="#5d3d5d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="rows", type="int", label="行数", default=3),
                        ParamDef(name="cols", type="int", label="列数", default=3)],
                description="网格编辑节点 — 按网格编辑多张图片",
            ),
            "imgcmp": NodeDef(
                type="imgcmp", category="function", label="图片对比", icon="🔍", color="#4d2d5d",
                inputs=[PortDef(name="in_0", type="image", description="图片A"),
                        PortDef(name="in_1", type="image", description="图片B")],
                outputs=[PortDef(name="out_0", type="any", description="对比结果")],
                params=[ParamDef(name="mode", type="select", label="模式", default="并排",
                                options=["并排", "差异", "滑动对比"])],
                description="图片对比节点 — 对比两张图片的差异",
            ),
            "presetimg": NodeDef(
                type="presetimg", category="function", label="预设图片", icon="🖼️", color="#3d3d6d",
                inputs=[],
                outputs=[PortDef(name="out_0", type="image", description="预设图片")],
                params=[ParamDef(name="preset", type="string", label="预设", default="samples")],
                description="预设图片节点 — 使用预设图片资源",
            ),
            "resize": NodeDef(
                type="resize", category="function", label="缩放", icon="📏", color="#3d4d5d",
                inputs=[PortDef(name="in_0", type="image")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="w", type="int", label="宽度", default=1024),
                        ParamDef(name="h", type="int", label="高度", default=1024)],
                description="缩放节点 — 调整图片分辨率",
            ),
            "frameex": NodeDef(
                type="frameex", category="function", label="帧提取", icon="📸", color="#3d5d6d",
                inputs=[PortDef(name="in_0", type="video")],
                outputs=[PortDef(name="out_0", type="image")],
                params=[ParamDef(name="fps", type="float", label="提取帧率", default=1.0)],
                description="帧提取节点 — 从视频提取关键帧",
            ),
            "framepair": NodeDef(
                type="framepair", category="function", label="帧对比", icon="🎞️", color="#4d5d6d",
                inputs=[PortDef(name="in_0", type="video")],
                outputs=[PortDef(name="out_0", type="any")],
                params=[ParamDef(name="mode", type="select", label="模式", default="对比",
                                options=["对比", "首尾帧"])],
                description="帧对比节点 — 视频帧对比分析",
            ),
        }

        # Register all nodes
        all_nodes = {}
        all_nodes.update(dimension_nodes)
        all_nodes.update(capability_nodes)
        all_nodes.update(function_nodes)
        
        for node_type, node_def in all_nodes.items():
            cls._registry[node_type] = node_def

        cls._initialized = True

    # ─── Public API ─────────────────────────────────────────────────────

    @classmethod
    def register(cls, node_type: str, node_def: NodeDef):
        """Register a custom node type at runtime."""
        cls._registry[node_type] = node_def

    @classmethod
    def get(cls, node_type: str) -> Optional[NodeDef]:
        """Get a node definition by its type key."""
        if not cls._initialized:
            cls.initialize()
        return cls._registry.get(node_type)

    @classmethod
    def list_all(cls) -> Dict[str, NodeDef]:
        """Get all registered node definitions."""
        if not cls._initialized:
            cls.initialize()
        return dict(cls._registry)

    @classmethod
    def list_by_category(cls, category: str) -> Dict[str, NodeDef]:
        """List all node definitions in a given category (dimension/capability/function)."""
        if not cls._initialized:
            cls.initialize()
        return {t: d for t, d in cls._registry.items() if d.category == category}

    @classmethod
    def list_categories(cls) -> List[str]:
        """Get all available categories."""
        if not cls._initialized:
            cls.initialize()
        cats = set()
        for nd in cls._registry.values():
            cats.add(nd.category)
        return sorted(cats)

    @classmethod
    def count(cls) -> int:
        """Get total number of registered node types."""
        if not cls._initialized:
            cls.initialize()
        return len(cls._registry)

    @classmethod
    def get_all_as_dict(cls) -> List[Dict[str, Any]]:
        """Serialize all node definitions to dicts for API responses."""
        if not cls._initialized:
            cls.initialize()
        return [
            {
                "type": nd.type,
                "category": nd.category,
                "label": nd.label,
                "icon": nd.icon,
                "color": nd.color,
                "description": nd.description,
                "inputs": [asdict(p) for p in nd.inputs],
                "outputs": [asdict(p) for p in nd.outputs],
                "params": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "label": p.label,
                        "default": p.default,
                        "options": p.options,
                        "description": p.description,
                    }
                    for p in nd.params
                ],
            }
            for nd in cls._registry.values()
        ]
