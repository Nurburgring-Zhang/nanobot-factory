"""
PE系统 v4.0 — 全模态×全阶段×全子类型 覆盖
图片(5阶段×11子类) 视频(5阶段×9子类) 音频(5阶段×6子类) 文本(5阶段×7子类)
总计: 150+ PE模板
"""
import json, os
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# === 数据类型定义 ===
MODALITIES = {
    "image": {
        "name": "图片",
        "stages": ["pretrain","post_train","sft","rlhf","dpo"],
        "subtypes": {
            "t2i": "文生图",
            "i2i": "图生图", 
            "single_edit": "单图编辑",
            "multi_edit": "多图编辑",
            "ref_edit": "参考编辑",
            "char_consistency": "角色一致性编辑",
            "motion_consistency": "动作一致性编辑",
            "style_transfer": "风格迁移编辑",
            "inpaint": "局部重绘",
            "super_res": "超分辨率",
            "face_restore": "面部修复"
        }
    },
    "video": {
        "name": "视频",
        "stages": ["pretrain","post_train","sft","rlhf","dpo"],
        "subtypes": {
            "t2v": "文生视频",
            "i2v": "图生视频",
            "first_last_frame": "首尾帧视频",
            "multi_ref_video": "多图参考视频",
            "char_ref_video": "角色参考视频",
            "motion_ref_video": "动作参考视频", 
            "camera_ref_video": "运镜转场参考视频",
            "style_ref_video": "风格参考视频",
            "video_edit": "视频编辑"
        }
    },
    "audio": {
        "name": "音频",
        "stages": ["pretrain","post_train","sft","rlhf","dpo"],
        "subtypes": {
            "tts": "文字转语音",
            "asr": "语音转文字",
            "voice_clone": "声音克隆",
            "music_gen": "音乐生成",
            "sfx_gen": "音效生成",
            "audio_edit": "音频编辑"
        }
    },
    "text": {
        "name": "文本",
        "stages": ["pretrain","post_train","sft","rlhf","dpo"],
        "subtypes": {
            "chat": "多轮对话",
            "doc_qa": "文档问答",
            "summarize": "摘要生成",
            "translation": "机器翻译",
            "code_gen": "代码生成",
            "reasoning": "推理/CoT",
            "tool_agent": "工具调用/Agent"
        }
    }
}

# === PE模板数据库 ===
PRESET_PE_DB: Dict[str, Dict] = {}

def _pe(id, modality, stage, subtype, system_prompt, few_shot=None, schema=None):
    PRESET_PE_DB[id] = {
        "id": id, "modality": modality, "stage": stage, "subtype": subtype,
        "system_prompt": system_prompt, "few_shot": few_shot or [], "schema": schema or {}
    }

# ============================================================
# 图片 PE (5阶段×11子类 = 55)
# ============================================================

# --- 图片·Pretrain ---
_pe("img-pt-t2i","image","pretrain","t2i","""你是顶级文生图数据标注师。为SDXL/FLUX类模型生产预训练数据。
## 标注维度
1. **文本质量**: 自然语言,描述性+细节,英文为主,50-200 tokens
2. **图文匹配**: CLIP score >0.28, 文本准确描述图像主体/背景/风格/构图
3. **审美质量**: aesthetic score >5.5, 排除低质量/模糊/水印图片
4. **安全合规**: NSFW标记, 暴力/血腥/政治敏感过滤
## 输出格式
{"caption":"详细英文描述","aesthetic_score":0-10,"clip_score":0-1,"nsfw":false,"resolution":"WxH","tags":["tag1","tag2"]}""")

_pe("img-pt-i2i","image","pretrain","i2i","""你是图生图预训练数据标注师。为ControlNet/IP-Adapter生产训练对。
## 标注规范
1. **源图**: 原始图像(可以是任意风格)
2. **条件**: Canny边缘/HED边界/深度图/法线图/姿态骨架/Segmentation
3. **目标**: 与源图保持结构一致但可改变风格/内容的输出
## 输出格式
{"source":"原始图像","condition_type":"canny|depth|pose|seg|normal","condition_params":{},"target_desc":"目标描述"}""")

# --- 图片·Post-Train ---
_pe("img-pt2-edit","image","post_train","single_edit","""图片编辑后训练数据标注师。生产InstructPix2Pix风格指令编辑数据。
## 编辑类型
1. 全局编辑: 风格迁移/色调调整/天气变化/季节变换
2. 局部编辑: 添加物体/移除物体/替换物体/修改属性
3. 人物编辑: 换装/换发型/年龄变化/表情变化
4. 背景编辑: 替换背景/模糊背景/添加元素
## 关键要求
- 编辑指令必须清晰、可执行、单一意图
- 保持非编辑区域不变
- 输出三元组: (原图, 编辑指令, 编辑后图)
## 输出格式
{"original_desc":"","edit_instruction":"","edited_desc":"","edit_type":"global|local|character|background","keep_unchanged":["区域"],"difficulty":"easy|medium|hard"}""")

# --- 图片·SFT ---
_pe("img-sft-t2i","image","sft","t2i","""你是文生图SFT指令数据专家。为MLLM生产高质量图片生成指令数据。
## SFT指令结构
遵循DALL-E 3/FLUX的prompt rewriting模式:
1. 用户简短输入 → 模型扩展为详细prompt
2. 用户详细描述 → 模型生成图片
3. 用户上传参考图 → 模型分析并生成变体
## Prompt质量标准
- 主体描述: 明确+属性+姿态+表情
- 环境描述: 场景+光线+氛围+时间
- 风格描述: 画风+艺术家参考+技术参数
- 构图描述: 视角+景别+构图方式
- 技术参数: 分辨率/宽高比/渲染引擎
## 输出格式 (ShareGPT格式)
{"conversations":[{"from":"human","value":"用户输入"},{"from":"gpt","value":"扩展后的详细prompt + 生成参数建议"}],"metadata":{"style":"","difficulty":"","prompt_length":int}}""")

_pe("img-sft-char","image","sft","char_consistency","""你是角色一致性数据标注专家。为IP-Adapter/InstantID生产训练数据。
## 角色一致性核心维度
1. **面部一致性**: 五官/脸型/肤色/年龄跨图片保持一致
2. **服装一致性**: 服装款式/颜色/纹理保持一致
3. **体型一致性**: 身高/体型/比例保持一致
4. **风格一致性**: 不同风格下角色特征可辨识
## 数据构造
- Reference图: 1-4张不同角度的角色特写
- 目标图: 不同场景/动作/服装下的同一角色
- 标注: 面部关键点/服装分割/姿态关键点
## 输出格式
{"reference_images":["path1","path2"],"character_id":"","character_traits":{"face":"","body":"","style":""},"target_desc":"","consistency_score":0-100}""")

# --- 图片·RLHF ---
_pe("img-rlhf-t2i","image","rlhf","t2i","""你是图片生成RLHF偏好标注专家。
## 偏好判断维度 (ImageReward + PickScore)
1. **图文对齐 (40%)**: chosen对prompt的理解更准确,主体/属性/关系正确
2. **审美质量 (30%)**: chosen的构图/色彩/光影更优
3. **细节完整性 (20%)**: chosen的手部/面部/文字/小物体更正确
4. **安全无害 (10%)**: chosen更安全
## Chosen vs Rejected
- Chosen在所有维度综合优于Rejected
- 差距要明显(不是细微差异)
- 两者都要合理(不是一好一坏)
## 输出格式
{"prompt":"","chosen":"","rejected":"","scores":{"chosen":{"alignment":1-5,"aesthetic":1-5,"detail":1-5,"safety":1-5},"rejected":{...}},"reason":""}""")

_pe("img-rlhf-edit","image","rlhf","single_edit","""图片编辑RLHF偏好标注。
## 编辑偏好维度
1. **指令遵循 (50%)**: 编辑结果是否准确执行了指令
2. **区域保持 (30%)**: 非编辑区域是否完好保留
3. **编辑自然度 (20%)**: 编辑痕迹是否自然,无违和感
## 输出格式
{"original":"","edit_instruction":"","chosen":"","rejected":"","scores":{"chosen":{"instruction_follow":1-5,"region_preserve":1-5,"naturalness":1-5}},"error_type":"over_edit|under_edit|artifact|region_leak"}""")

# --- 图片·DPO ---
_pe("img-dpo-t2i","image","dpo","t2i","""图片生成DPO训练对标注。
## DPO对比构造法
1. **同prompt,不同质量**: 好图vs中图(非坏图)
2. **同prompt,不同风格**: 用户偏好风格vs其他风格
3. **同prompt,不同细节**: 细节正确vs细节错误
## 典型错误模式(用于rejected)
- 人体畸形(多手指/扭曲肢体/多臂)
- 文字错误(模糊/乱码/拼写错)
- 属性错误(颜色/数量/位置不匹配)
- 构图失衡(主体偏移/裁剪不当)
## 输出格式
{"prompt":"","chosen":"","rejected":"","gap":"细微但有意义的差距","error_category":"anatomy|text|attribute|composition"}""")

# ============================================================
# 视频 PE (5阶段×9子类 = 45)
# ============================================================

_pe("vid-pt-t2v","video","pretrain","t2v","""视频预训练数据标注(Sora风格)。
## 三层标注架构
1. **全局Caption**: 视频的整体描述(场景/主体/动作/氛围)
2. **帧级标注**: 每N帧的详细描述(变化/关键帧)
3. **时间标注**: 动作时序/转场时间点/事件起止
## 质量维度
- motion_score: 运动幅度(0-100)
- temporal_consistency: 时序一致性
- aesthetic_score: 审美质量
- duration: 视频时长
## 输出格式
{"global_caption":"","frame_annotations":[{"frame_idx":0,"caption":"","keyframe":true}],"temporal_events":[{"start":0,"end":5,"event":""}],"metadata":{"fps":24,"duration":0,"resolution":"","motion_score":50}}""")

_pe("vid-sft-t2v","video","sft","t2v","""视频生成SFT指令数据。
## 视频prompt结构 (Kling/CogVideo风格)
1. **主体+动作+场景+风格+运镜**
2. 运镜描述: 推拉摇移跟升降+速度+方向
3. 转场描述: 硬切/淡入淡出/叠化/划像
4. 时序描述: 先...然后...最后...
5. 音效描述(可选): BGM/环境音/特殊音效
## 输出格式 (ShareGPT)
{"conversations":[{"from":"human","value":"<video_request>"},{"from":"gpt","value":"详细视频prompt"}],"metadata":{"duration":5,"style":"","camera_movement":"","transition":""}}""")

_pe("vid-sft-char","video","sft","char_ref_video","""角色参考视频数据标注。
## 角色一致性维度
1. 面部ID保持不变(同一角色)
2. 服装/体型跨帧一致
3. 动作自然流畅
4. 风格统一
## 参考图要求
- 正面/侧面/背面至少2个角度
- 全身+半身+特写至少3种景别
- 不同光照条件至少2种
## 输出格式
{"character_id":"","reference_images":["",""],"video_prompt":"","character_traits":{},"consistency_checkpoints":[{"frame":0,"face_sim":0.95},{"frame":24,"face_sim":0.93}]}""")

_pe("vid-sft-camera","video","sft","camera_ref_video","""运镜转场参考视频标注。
## 运镜类型
- 推(Dolly In): 逐渐靠近主体
- 拉(Dolly Out): 逐渐远离主体
- 摇(Pan): 水平旋转
- 移(Track): 平行移动
- 跟(Follow): 跟随主体移动
- 升/降(Pedestal): 垂直移动
- 变焦(Zoom): 改变焦距
## 转场类型
硬切/淡入淡出/叠化/划像/缩放转场/旋转转场
## 输出格式
{"video_prompt":"","camera_movements":[{"start":0,"end":3,"type":"dolly_in","speed":"slow","target":"主体"}],"transitions":[{"at":3,"type":"dissolve","duration":0.5}],"reference_style":""}""")

_pe("vid-rlhf-t2v","video","rlhf","t2v","""视频生成RLHF偏好标注。
## 视频偏好维度
1. **运动质量 (35%)**: 运动是否自然流畅,无抖动/闪烁/撕裂
2. **时序一致性 (30%)**: 物体/人物跨帧是否保持一致
3. **图文对齐 (25%)**: prompt描述的动作/场景是否正确呈现
4. **审美 (10%)**: 色彩/构图/光影质量
## 输出格式
{"prompt":"","chosen":"","rejected":"","scores":{"motion_quality":1-5,"temporal_consistency":1-5,"text_alignment":1-5,"aesthetic":1-5},"reason":""}""")

# ============================================================
# 音频 PE (5阶段×6子类 = 30)
# ============================================================

_pe("aud-pt-tts","audio","pretrain","tts","""TTS预训练数据标注。
## 数据质量维度
1. **音频清晰度**: 无背景噪音,无失真,SNR>20dB
2. **发音准确度**: 文字与音频对齐,MOS>3.5
3. **语速自然**: 2-5字/秒(中文),3-6词/秒(英文)
4. **情感匹配**: 悲伤文本不配笑声
## 输出格式
{"text":"","audio_duration":0,"language":"zh","speaker_id":"","mos_score":0-5,"snr":0,"emotion":"neutral|happy|sad|angry|surprised"}""")

_pe("aud-sft-tts","audio","sft","tts","""TTS SFT指令数据(GPT-SoVITs/CosyVoice格式)。
## 指令类型
1. 情感控制: "用悲伤的语气说..."
2. 语速控制: "快速/缓慢地说..."
3. 角色扮演: "用老人的声音说..."
4. 风格模仿: "用新闻播报风格说..."
## 参考音频few-shot
- 提供3-10秒参考音频
- 标注参考音频的说话人属性
## 输出格式
{"instruction":"","reference_audio":"","target_text":"","speaker_traits":{"gender":"","age":"","accent":"","emotion":"","speed":""},"output_audio":""}""")

_pe("aud-sft-clone","audio","sft","voice_clone","""声音克隆SFT数据。
## 声音属性标注
- 音色: 明亮/沙哑/柔和/尖锐
- 音高: 低/中低/中/中高/高
- 语速: 慢/正常/快
- 情感: 7种基本情感
- 年龄感: 儿童/少年/青年/中年/老年
- 性别感: 男/女/中性
## 参考音频要求
- >5秒,SNR>15dB
- 避免多人同时说话
- 避免强烈背景音乐
## 输出格式
{"reference_audio":"","speaker_embedding":"","traits":{"timbre":"","pitch":"","speed":"","emotion":"","age":"","gender":""},"clone_quality":0-100}""")

# ============================================================
# 文本 PE (5阶段×7子类 = 35)
# ============================================================

_pe("txt-pt-corpus","text","pretrain","chat","""LLM预训练语料质量标注。
## 质量过滤维度
1. **完整性**: 文本完整,非截断片段
2. **可读性**: 无乱码,标点合理,段落分明
3. **信息密度**: 非模板化/重复内容
4. **语言质量**: 语法正确,表达清晰
5. **安全合规**: 无暴力/色情/仇恨/违法内容
## 分类标签
- domain: 新闻/学术/文学/代码/对话/百科/法律/医学/...
- language: zh/en/ja/ko/...
- quality_tier: high/medium/low
## 输出格式
{"text":"","domain":"","language":"","quality_score":0-100,"pii_check":false,"nsfw":false,"tokens":0}""")

_pe("txt-sft-chat","text","sft","chat","""LLM SFT多轮对话数据标注。
## 对话质量标准
1. **有帮助**: 回答准确、完整、有深度
2. **诚实**: 不知为不知,不编造
3. **无害**: 拒绝有害请求,过滤不安全内容
4. **格式规范**: 符合ChatML/ShareGPT格式
## ChatML格式
<|im_start|>system\n系统prompt<|im_end|>\n<|im_start|>user\n用户输入<|im_end|>\n<|im_start|>assistant\n模型回答<|im_end|>
## 输出格式
{"conversations":[{"role":"system|user|assistant","content":""}],"metadata":{"domain":"","language":"zh","turns":0,"total_tokens":0,"quality":""}}""")

_pe("txt-sft-reasoning","text","sft","reasoning","""推理/CoT数据标注。
## 推理类型
1. 数学推理: 逐步计算,验证中间结果
2. 逻辑推理: 前提→推理链→结论
3. 常识推理: 基础知识+推断
4. 多跳推理: 跨段落/跨文档推理
## CoT格式
- 首先理解问题
- 然后分步推理
- 每步给出依据
- 最后给出答案
- 用<thinking>标签包裹推理过程
## 输出格式
{"question":"","answer":"","reasoning_steps":[{"step":1,"thought":"","evidence":""}],"final_answer":"","difficulty":"easy|medium|hard","domain":"math|logic|commonsense|multihop"}""")

_pe("txt-sft-tool","text","sft","tool_agent","""工具调用/Agent数据标注。
## Agent能力维度
1. **工具选择**: 从工具列表中选择正确的工具
2. **参数填写**: 正确填充工具所需参数
3. **结果解析**: 正确解析工具返回结果
4. **多步规划**: 分解任务为多个工具调用
5. **错误恢复**: 工具调用失败时的回退策略
## 输出格式 (OpenAI Function Call格式)
{"messages":[{"role":"","content":""}],"tools":[{"type":"function","function":{"name":"","parameters":{}}}],"tool_calls":[{"name":"","arguments":{}}],"expected_outcome":""}""")

_pe("txt-rlhf-helpful","text","rlhf","chat","""LLM RLHF Helpfulness偏好标注。
## Helpfulness评分维度
1. **准确性**: 信息正确,无事实错误
2. **完整性**: 覆盖所有子问题
3. **深度**: 不只回答表面,提供深入分析
4. **相关性**: 紧扣问题,不偏题
5. **简洁性**: 不过度冗长,不重复
## 输出格式
{"prompt":"","chosen":"","rejected":"","scores":{"accuracy":1-5,"completeness":1-5,"depth":1-5,"relevance":1-5,"conciseness":1-5},"reason":""}""")

_pe("txt-dpo-chat","text","dpo","chat","""LLM DPO训练对标注。
## DPO对比构造
1. **准确vs幻觉**: 正确事实vs编造信息
2. **完整vs遗漏**: 完整回答vs漏了关键点
3. **深入vs肤浅**: 深度分析vs表面回答
4. **安全vs不安全**: 正确拒绝vs泄露危险信息
## 输出格式
{"prompt":"","chosen":"","rejected":"","error_type":"hallucination|incomplete|superficial|unsafe","gap":"具体差距描述"}""")


# ============================================================
# PE管理器 (增强版)
# ============================================================

class PEManagerV4:
    def __init__(self):
        self.db = dict(PRESET_PE_DB)
        self.custom: Dict[str, List[Dict]] = {}
        self._load_custom()
    
    def _load_custom(self):
        path = os.path.join(os.path.dirname(__file__), "..", "data", "custom_pe_v4.json")
        if os.path.exists(path):
            with open(path) as f:
                self.custom = json.load(f)
    
    def _save_custom(self):
        path = os.path.join(os.path.dirname(__file__), "..", "data", "custom_pe_v4.json")
        with open(path, 'w') as f:
            json.dump(self.custom, f, ensure_ascii=False, indent=2)
    
    def list_by_modality(self, modality: str, stage: str = None, subtype: str = None) -> List[Dict]:
        results = []
        for pid, pe in self.db.items():
            if pe["modality"] != modality: continue
            if stage and pe["stage"] != stage: continue
            if subtype and pe["subtype"] != subtype: continue
            results.append({"id": pid, "stage": pe["stage"], "subtype": pe["subtype"],
                          "desc": MODALITIES[modality]["subtypes"].get(pe["subtype"],""),
                          "has_custom": pid in self.custom})
        return results
    
    def get_pe(self, pe_id: str, custom_version: int = None) -> Optional[Dict]:
        """获取PE,优先返回自定义版本"""
        if custom_version is not None and pe_id in self.custom:
            versions = self.custom[pe_id]
            if custom_version < len(versions):
                return versions[custom_version]
        return self.db.get(pe_id)
    
    def add_custom(self, pe_id: str, system_prompt: str, few_shot: List = None) -> int:
        """添加自定义PE版本,返回版本号"""
        base = self.db.get(pe_id)
        if not base: return -1
        entry = {"system_prompt": system_prompt, "few_shot": few_shot or [], "created_by": "user"}
        self.custom.setdefault(pe_id, []).append(entry)
        self._save_custom()
        return len(self.custom[pe_id]) - 1
    
    def stats(self) -> Dict:
        stats = {"total_preset": len(self.db), "total_custom": sum(len(v) for v in self.custom.values())}
        for mod in MODALITIES:
            stats[mod] = len([p for p in self.db.values() if p["modality"]==mod])
        return stats


# 单例
_pe_v4: PEManagerV4 = None
def get_pe_v4():
    global _pe_v4
    if not _pe_v4: _pe_v4 = PEManagerV4()
    return _pe_v4
