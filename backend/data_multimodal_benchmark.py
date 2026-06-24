"""
NanoBot Factory - 多模态评测数据生成
Multimodal Benchmark Data Generator

功能:
- MMMU风格评测数据 (大学级别学科问答)
- 图文问答对 (VQA pairs)
- LLaVA多轮对话格式
- VBench评测条目
- HuggingFace Datasets格式保存
"""

import os, json, logging, random, math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class BenchmarkQuestion:
    """评测问题"""
    question_id: str
    question: str
    options: List[str]          # 选择题选项
    answer: str                 # 正确答案
    explanation: str = ""       # 解释
    subject: str = ""           # 学科
    difficulty: str = "medium"  # easy / medium / hard
    image_required: bool = False


@dataclass
class VQAPair:
    """图文问答对"""
    qa_id: str
    image_path: str = ""
    question: str = ""
    answer: str = ""
    category: str = "general"   # general / counting / color / location / etc.
    confidence: float = 1.0


@dataclass
class LLaVAConversation:
    """LLaVA多轮对话"""
    conv_id: str
    image_path: str = ""
    conversations: List[Dict] = field(default_factory=list)  # [{"from": "human"/"gpt", "value": str}, ...]


@dataclass
class VBenchItem:
    """VBench评测条目"""
    item_id: str
    dimension: str          # 评测维度
    prompt: str = ""        # 生成提示词
    reference: str = ""     # 参考标准
    scoring_method: str = ""  # 评分方法


@dataclass
class BenchmarkDataset:
    """完整评测数据集"""
    name: str
    questions: List[BenchmarkQuestion] = field(default_factory=list)
    vqa_pairs: List[VQAPair] = field(default_factory=list)
    conversations: List[LLaVAConversation] = field(default_factory=list)
    vbench_items: List[VBenchItem] = field(default_factory=list)
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Benchmark Data Generator
# ============================================================================

class BenchmarkDataGenerator:
    """
    多模态评测数据生成器

    生成以下类型的评测数据:
    - MMMU风格: 大学级别多学科问答
    - VQA: 图文问答对
    - LLaVA: 多轮对话格式
    - VBench: 视频评测条目

    全部基于模板和规则生成 (无需LLM API调用)
    """

    # MMMU学科
    MMMU_SUBJECTS = [
        "physics", "chemistry", "biology", "mathematics",
        "computer_science", "engineering", "medical", "psychology",
        "art_history", "geography", "literature", "philosophy",
    ]

    # VBench评测维度
    VBENCH_DIMENSIONS = [
        "subject_consistency", "background_consistency", "temporal_flickering",
        "motion_smoothness", "dynamic_degree", "aesthetic_quality",
        "imaging_quality", "object_class", "multiple_objects",
        "color", "spatial_relationship", "scene",
        "temporal_style", "human_action", "human_face",
    ]

    def __init__(self):
        self._question_templates = self._init_question_templates()
        self._vqa_templates = self._init_vqa_templates()
        self._llava_templates = self._init_llava_templates()

    def _init_question_templates(self) -> Dict[str, List[Dict]]:
        """初始化MMMU风格问题模板"""
        return {
            "physics": [
                {
                    "question": "Based on Newton's second law, what happens to the acceleration of an object when the net force applied is doubled?",
                    "options": ["It is halved", "It is doubled", "It quadruples", "It stays the same"],
                    "answer": "It is doubled",
                    "explanation": "F=ma, so when F is doubled, a is also doubled (mass constant).",
                },
                {
                    "question": "An object is placed at the focal point of a convex lens. Where will the image be formed?",
                    "options": ["At infinity", "At 2F", "Between F and 2F", "At F"],
                    "answer": "At infinity",
                    "explanation": "When an object is at the focal point, rays emerge parallel, forming an image at infinity.",
                },
                {
                    "question": "Which of the following has the highest specific heat capacity?",
                    "options": ["Water", "Iron", "Copper", "Mercury"],
                    "answer": "Water",
                    "explanation": "Water has the highest specific heat capacity (4.18 J/g·K) among common substances.",
                },
            ],
            "chemistry": [
                {
                    "question": "What is the pH of a 0.001 M HCl solution?",
                    "options": ["1", "2", "3", "4"],
                    "answer": "3",
                    "explanation": "pH = -log[H+], so pH = -log(0.001) = 3.",
                },
                {
                    "question": "Which of the following is NOT an allotrope of carbon?",
                    "options": ["Graphene", "Diamond", "Fullerene", "Silicon carbide"],
                    "answer": "Silicon carbide",
                    "explanation": "Silicon carbide is a compound, not an allotrope of carbon.",
                },
            ],
            "biology": [
                {
                    "question": "What organelle is primarily responsible for ATP production in eukaryotic cells?",
                    "options": ["Nucleus", "Ribosome", "Mitochondrion", "Golgi apparatus"],
                    "answer": "Mitochondrion",
                    "explanation": "Mitochondria are the powerhouses of the cell, producing ATP through oxidative phosphorylation.",
                },
                {
                    "question": "DNA replication is described as semi-conservative because:",
                    "options": ["Each new DNA molecule contains one original strand and one new strand",
                               "Only one strand is copied",
                               "The entire molecule is conserved",
                               "RNA is used as a template"],
                    "answer": "Each new DNA molecule contains one original strand and one new strand",
                    "explanation": "In semi-conservative replication, each daughter DNA molecule consists of one parent strand and one newly synthesized strand.",
                },
            ],
            "mathematics": [
                {
                    "question": "What is the limit of (sin x)/x as x approaches 0?",
                    "options": ["0", "1", "Infinity", "Does not exist"],
                    "answer": "1",
                    "explanation": "This is a fundamental limit in calculus. As x→0, sin x/x→1.",
                },
                {
                    "question": "A 3×3 matrix has eigenvalues 1, 2, and 3. What is its determinant?",
                    "options": ["6", "5", "3", "Cannot be determined"],
                    "answer": "6",
                    "explanation": "The determinant equals the product of eigenvalues: 1×2×3=6.",
                },
            ],
            "computer_science": [
                {
                    "question": "What is the time complexity of binary search?",
                    "options": ["O(n)", "O(log n)", "O(n log n)", "O(n²)"],
                    "answer": "O(log n)",
                    "explanation": "Binary search halves the search space each iteration, giving logarithmic time complexity.",
                },
                {
                    "question": "Which data structure uses FIFO (First-In-First-Out) principle?",
                    "options": ["Stack", "Queue", "Tree", "Hash Table"],
                    "answer": "Queue",
                    "explanation": "Queues follow FIFO order: elements are added at the rear and removed from the front.",
                },
            ],
            "engineering": [
                {
                    "question": "What is the Nyquist sampling rate for a signal with maximum frequency 5 kHz?",
                    "options": ["5 kHz", "10 kHz", "2.5 kHz", "15 kHz"],
                    "answer": "10 kHz",
                    "explanation": "Nyquist rate is twice the maximum frequency: 2 × 5 kHz = 10 kHz.",
                },
                {
                    "question": "In a series RLC circuit at resonance, the impedance is:",
                    "options": ["Maximum", "Minimum and purely resistive", "Zero", "Infinite"],
                    "answer": "Minimum and purely resistive",
                    "explanation": "At resonance, inductive and capacitive reactances cancel, leaving only resistance.",
                },
            ],
        }

    def _init_vqa_templates(self) -> List[Dict]:
        """初始化VQA模板"""
        return [
            {"question": "What is the main color in this image?", "category": "color"},
            {"question": "How many objects are visible in this image?", "category": "counting"},
            {"question": "What is the primary subject of this image?", "category": "general"},
            {"question": "Is this image taken indoors or outdoors?", "category": "scene"},
            {"question": "What time of day does this image depict?", "category": "time"},
            {"question": "What is the mood or atmosphere of this scene?", "category": "mood"},
            {"question": "What objects are shown in the foreground?", "category": "spatial"},
            {"question": "What objects are shown in the background?", "category": "spatial"},
            {"question": "Describe the lighting conditions in this image.", "category": "technical"},
            {"question": "Is there text visible in this image? If so, what does it say?", "category": "text"},
        ]

    def _init_llava_templates(self) -> List[List[Dict]]:
        """初始化LLaVA多轮对话模板"""
        return [
            [
                {"from": "human", "value": "What is shown in this image?"},
                {"from": "gpt", "value": "This image shows a scene with various visual elements. The overall composition includes {objects} with {color} tones and {lighting} lighting."},
                {"from": "human", "value": "Can you describe the spatial layout?"},
                {"from": "gpt", "value": "The spatial layout consists of {foreground} in the foreground and {background} in the background, creating a sense of depth."},
                {"from": "human", "value": "What is the likely context of this scene?"},
                {"from": "gpt", "value": "Based on the visual elements, this appears to be a {scene_type} scene, possibly captured in a {setting} setting."},
            ],
            [
                {"from": "human", "value": "Describe this image in detail."},
                {"from": "gpt", "value": "This is a detailed visual scene featuring {main_subject}. The color palette is dominated by {color} tones. The composition draws attention to the central elements through {technique}."},
                {"from": "human", "value": "What are the most notable features?"},
                {"from": "gpt", "value": "The most notable features include {features}. The image quality shows {quality_desc} with {lighting} lighting conditions."},
            ],
        ]

    # ========================================================================
    # MMMU风格评测数据
    # ========================================================================

    def generate_mmmu_style(
        self,
        subjects: Optional[List[str]] = None,
        questions_per_subject: int = 3,
        difficulty: str = "medium"
    ) -> List[BenchmarkQuestion]:
        """
        生成MMMU风格评测数据

        MMMU格式:
        {
            "id": str,
            "question": str,
            "options": [str],
            "answer": str,
            "explanation": str,
            "subject": str,
            "difficulty": str
        }

        Args:
            subjects: 学科列表 (默认全部)
            questions_per_subject: 每学科问题数
            difficulty: 难度

        Returns:
            BenchmarkQuestion列表
        """
        if subjects is None:
            subjects = self.MMMU_SUBJECTS

        questions = []

        for subject in subjects:
            templates = self._question_templates.get(subject, [])
            if not templates:
                # 为没有模板的学科生成通用问题
                for i in range(questions_per_subject):
                    q = BenchmarkQuestion(
                        question_id=f"mmmu_{subject}_{i:04d}",
                        question=f"Which of the following best describes a concept in {subject}?",
                        options=[
                            f"Option A related to {subject}",
                            f"Option B related to {subject}",
                            f"Option C related to {subject}",
                            f"Option D related to {subject}",
                        ],
                        answer=f"Option A related to {subject}",
                        explanation=f"This is a fundamental concept in {subject}.",
                        subject=subject,
                        difficulty=difficulty,
                    )
                    questions.append(q)
                continue

            for i in range(min(questions_per_subject, len(templates))):
                t = templates[i]
                q = BenchmarkQuestion(
                    question_id=f"mmmu_{subject}_{i:04d}",
                    question=t["question"],
                    options=t["options"],
                    answer=t["answer"],
                    explanation=t.get("explanation", ""),
                    subject=subject,
                    difficulty=difficulty,
                )
                questions.append(q)

        logger.info(f"Generated {len(questions)} MMMU-style questions across {len(subjects)} subjects")
        return questions

    # ========================================================================
    # 图文问答对
    # ========================================================================

    def generate_vqa_pairs(
        self,
        image: Optional[Union[str, Image.Image]] = None,
        questions: Optional[List[str]] = None,
        num_pairs: int = 5
    ) -> List[VQAPair]:
        """
        生成图文问答对 (VQA)

        如果提供了图像，会基于图像属性生成相关的问答。
        如果没有图像，生成模板通用问答。

        Args:
            image: 输入图像 (可选)
            questions: 自定义问题列表 (可选)
            num_pairs: 要生成的对数

        Returns:
            VQAPair列表
        """
        pairs = []

        if questions is None:
            templates = self._vqa_templates
            if num_pairs < len(templates):
                templates = random.sample(templates, num_pairs)
        else:
            templates = [{"question": q, "category": "custom"} for q in questions]

        image_path = ""
        image_analysis = {}

        if image is not None:
            # 分析图像
            image_analysis = self._analyze_image_for_vqa(image)
            if isinstance(image, str):
                image_path = image

        for i, tpl in enumerate(templates):
            question = tpl["question"]
            category = tpl.get("category", "general")

            # 如果有图像分析结果，生成基于内容的答案
            if image_analysis:
                answer = self._generate_vqa_answer(question, category, image_analysis)
            else:
                answer = f"This is a sample answer for: '{question}'. The specific answer depends on the input image."

            pair = VQAPair(
                qa_id=f"vqa_{i:04d}",
                image_path=image_path,
                question=question,
                answer=answer,
                category=category,
            )
            pairs.append(pair)

        return pairs

    def _analyze_image_for_vqa(self, image: Union[str, Image.Image]) -> Dict[str, Any]:
        """分析图像属性用于VQA"""
        try:
            if isinstance(image, str):
                img = Image.open(image).convert("RGB")
            else:
                img = image.convert("RGB")

            arr = np.array(img)
            h, w = arr.shape[:2]

            # 颜色
            avg_color = np.mean(arr.reshape(-1, 3), axis=0)
            brightness = float(np.mean(arr)) / 255.0
            std_color = float(np.std(arr))

            # 主色名称
            colors = {"red": (255,0,0), "green": (0,128,0), "blue": (0,0,255),
                      "yellow": (255,255,0), "white": (255,255,255), "black": (0,0,0),
                      "gray": (128,128,128), "brown": (165,42,42)}
            main_color = min(colors, key=lambda c: np.sqrt(
                (avg_color[0]-colors[c][0])**2 + (avg_color[1]-colors[c][1])**2 +
                (avg_color[2]-colors[c][2])**2
            ))

            # 场景 (室内/室外)
            gray = np.mean(arr, axis=2)
            top_brightness = float(np.mean(gray[:h//4]))
            is_outdoor = top_brightness > 150

            # 物体数量估算 (通过边缘检测)
            try:
                import cv2
                edges = cv2.Canny(gray.astype(np.uint8), 50, 150)
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                obj_count = sum(1 for c in contours if cv2.contourArea(c) > w * h * 0.005)
            except Exception:
                obj_count = 3  # fallback

            # 面部检测
            face_count = 0
            try:
                import cv2
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                if os.path.exists(cascade_path):
                    cascade = cv2.CascadeClassifier(cascade_path)
                    gray_cv = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                    faces = cascade.detectMultiScale(gray_cv, 1.1, 5)
                    face_count = len(faces)
            except Exception:
                pass

            # 文本检测 (简单: 检查高频边缘区域)
            has_text = False
            try:
                import cv2
                gray_cv = gray.astype(np.uint8)
                # MSER-like: 检测小连通区域
                _, binary = cv2.threshold(gray_cv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                text_ratio = float(np.sum(binary > 0)) / (w * h)
                has_text = 0.3 < text_ratio < 0.7
            except Exception:
                pass

            return {
                "main_color": main_color,
                "brightness": brightness,
                "color_diversity": std_color,
                "is_outdoor": is_outdoor,
                "estimated_objects": obj_count,
                "face_count": face_count,
                "has_text": has_text,
                "width": w,
                "height": h,
                "aspect_ratio": w / max(h, 1),
            }

        except Exception as e:
            logger.warning(f"Image analysis failed: {e}")
            return {}

    def _generate_vqa_answer(self, question: str, category: str,
                              analysis: Dict[str, Any]) -> str:
        """根据图像分析生成VQA答案"""
        if category == "color":
            return f"The main color in this image is {analysis.get('main_color', 'unknown')}."

        elif category == "counting":
            count = analysis.get("estimated_objects", 0)
            return f"There are approximately {count} objects visible in this image."

        elif category == "scene":
            is_outdoor = analysis.get("is_outdoor", False)
            return "This image was taken outdoors." if is_outdoor else "This image was taken indoors."

        elif category == "time":
            brightness = analysis.get("brightness", 0.5)
            if brightness > 0.7:
                return "This image appears to be taken during daytime with bright lighting."
            elif brightness > 0.4:
                return "This image has moderate lighting, possibly taken during daytime or well-lit indoor conditions."
            else:
                return "This image has low lighting, possibly taken at night or in dim conditions."

        elif category == "mood":
            brightness = analysis.get("brightness", 0.5)
            color = analysis.get("main_color", "neutral")
            if brightness > 0.7 and color in ["white", "yellow", "blue"]:
                return "The mood appears bright and cheerful."
            elif brightness < 0.3 or color in ["black", "gray"]:
                return "The mood appears somber or dramatic."
            else:
                return "The mood is neutral and balanced."

        elif category == "spatial":
            return f"The image has a {analysis.get('aspect_ratio', 1.0):.1f} aspect ratio, with estimated {analysis.get('estimated_objects', 0)} distinct visual elements."

        elif category == "technical":
            brightness = analysis.get("brightness", 0.5)
            diversity = analysis.get("color_diversity", 30)
            if diversity > 50:
                return "The lighting is varied with rich color diversity."
            else:
                return f"The lighting is {'bright' if brightness > 0.6 else 'moderate' if brightness > 0.3 else 'dim'} with a {analysis.get('main_color', 'neutral')} color cast."

        elif category == "text":
            if analysis.get("has_text", False):
                return "Yes, there appears to be text visible in this image."
            else:
                return "No significant text is visible in this image."

        else:
            return f"The image shows a scene characterized by {analysis.get('main_color', 'various')} colors and {analysis.get('estimated_objects', 0)} identifiable objects."

    # ========================================================================
    # LLaVA多轮对话格式
    # ========================================================================

    def generate_llava_style(
        self,
        image: Optional[Union[str, Image.Image]] = None,
        conversation: Optional[List[Dict]] = None,
        num_turns: int = 4
    ) -> LLaVAConversation:
        """
        生成LLaVA风格多轮对话

        LLaVA格式:
        {
            "id": str,
            "image": "path/to/image.jpg",
            "conversations": [
                {"from": "human", "value": "<image>\\nquestion"},
                {"from": "gpt", "value": "answer"},
                ...
            ]
        }

        Args:
            image: 输入图像 (可选)
            conversation: 自定义对话模板
            num_turns: 对话轮次

        Returns:
            LLaVAConversation
        """
        image_path = ""
        analysis = {}

        if image is not None:
            analysis = self._analyze_image_for_vqa(image)
            if isinstance(image, str):
                image_path = image

        if conversation is None:
            # 从模板中选择
            templates = self._llava_templates
            template = random.choice(templates) if templates else []
        else:
            template = conversation

        conv = LLaVAConversation(
            conv_id=f"llava_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}",
            image_path=image_path,
        )

        for turn in template[:num_turns]:
            speaker = turn["from"]
            value = turn["value"]

            # 如果是第一轮human，添加<image>标记
            if speaker == "human" and not conv.conversations:
                value = f"<image>\n{value}"

            # 填充模板变量
            if analysis:
                value = self._fill_template_vars(value, analysis)

            conv.conversations.append({
                "from": speaker,
                "value": value,
            })

        return conv

    def _fill_template_vars(self, text: str, analysis: Dict[str, Any]) -> str:
        """填充模板变量"""
        vars_map = {
            "{objects}": f"{analysis.get('estimated_objects', 'several')} objects",
            "{color}": analysis.get("main_color", "neutral"),
            "{lighting}": "bright" if analysis.get("brightness", 0.5) > 0.6 else "moderate",
            "{foreground}": analysis.get("main_color", "various"),
            "{background}": "complementary elements",
            "{scene_type}": "outdoor" if analysis.get("is_outdoor", False) else "indoor",
            "{setting}": "natural" if analysis.get("is_outdoor", False) else "built",
            "{main_subject}": f"a {analysis.get('main_color', 'colorful')} composition",
            "{technique}": "visual contrast and framing",
            "{features}": f"{analysis.get('estimated_objects', 0)} distinct visual regions",
            "{quality_desc}": "good clarity" if analysis.get("brightness", 0.5) > 0.4 else "moderate clarity",
        }
        for key, val in vars_map.items():
            text = text.replace(key, val)
        return text

    # ========================================================================
    # VBench评测条目
    # ========================================================================

    def generate_vbench_items(self) -> List[VBenchItem]:
        """
        生成VBench评测条目

        VBench是一个视频生成评测框架，包含多个评测维度。
        这里生成所有维度的评测条目。

        Returns:
            VBenchItem列表
        """
        items = []

        dimension_prompts = {
            "subject_consistency": "A person walking down a street",
            "background_consistency": "A cat sitting on a couch",
            "temporal_flickering": "A sunset over the ocean",
            "motion_smoothness": "A ball rolling across a field",
            "dynamic_degree": "A car racing on a track",
            "aesthetic_quality": "A beautiful garden in bloom",
            "imaging_quality": "A close-up of a flower",
            "object_class": "A dog playing in the park",
            "multiple_objects": "Several birds flying in the sky",
            "color": "A colorful butterfly on a leaf",
            "spatial_relationship": "A book on a table next to a lamp",
            "scene": "A busy city street during rush hour",
            "temporal_style": "A time-lapse of clouds moving",
            "human_action": "A person playing piano",
            "human_face": "A person smiling at the camera",
        }

        dimension_methods = {
            "subject_consistency": "CLIP-based subject consistency score across frames",
            "background_consistency": "Background region consistency via optical flow",
            "temporal_flickering": "Frame-to-frame intensity variation analysis",
            "motion_smoothness": "Optical flow smoothness measurement",
            "dynamic_degree": "Motion magnitude distribution analysis",
            "aesthetic_quality": "Image aesthetic score averaged over frames",
            "imaging_quality": "Frame-level image quality metrics (sharpness, noise, etc.)",
            "object_class": "Object detection accuracy across frames",
            "multiple_objects": "Number of consistently tracked objects",
            "color": "Color histogram consistency between frames",
            "spatial_relationship": "Spatial relationship preservation across frames",
            "scene": "Scene classification consistency",
            "temporal_style": "Style consistency across temporal segments",
            "human_action": "Action recognition confidence",
            "human_face": "Face detection and quality across frames",
        }

        for dim in self.VBENCH_DIMENSIONS:
            item = VBenchItem(
                item_id=f"vbench_{dim}",
                dimension=dim,
                prompt=dimension_prompts.get(dim, f"A video showing {dim.replace('_', ' ')}"),
                reference=f"Reference: {dim.replace('_', ' ')} evaluation protocol",
                scoring_method=dimension_methods.get(dim, "Standard evaluation metric"),
            )
            items.append(item)

        logger.info(f"Generated {len(items)} VBench items across {len(self.VBENCH_DIMENSIONS)} dimensions")
        return items

    # ========================================================================
    # 保存为HuggingFace Datasets格式
    # ========================================================================

    def save_hf_format(
        self,
        dataset: BenchmarkDataset,
        output_dir: str = "./data/benchmark"
    ) -> str:
        """
        保存为HuggingFace Datasets格式

        生成JSONL文件, 每行一个条目。

        Args:
            dataset: 评测数据集
            output_dir: 输出目录

        Returns:
            输出目录路径
        """
        os.makedirs(output_dir, exist_ok=True)

        # 1. MMMU问题
        if dataset.questions:
            questions_path = os.path.join(output_dir, "questions.jsonl")
            with open(questions_path, "w") as f:
                for q in dataset.questions:
                    f.write(json.dumps(asdict(q), ensure_ascii=False) + "\n")

        # 2. VQA对
        if dataset.vqa_pairs:
            vqa_path = os.path.join(output_dir, "vqa.jsonl")
            with open(vqa_path, "w") as f:
                for pair in dataset.vqa_pairs:
                    f.write(json.dumps(asdict(pair), ensure_ascii=False) + "\n")

        # 3. LLaVA对话
        if dataset.conversations:
            llava_path = os.path.join(output_dir, "llava_conversations.jsonl")
            with open(llava_path, "w") as f:
                for conv in dataset.conversations:
                    f.write(json.dumps(asdict(conv), ensure_ascii=False) + "\n")

        # 4. VBench
        if dataset.vbench_items:
            vbench_path = os.path.join(output_dir, "vbench_items.json")
            with open(vbench_path, "w") as f:
                json.dump({
                    "items": [asdict(it) for it in dataset.vbench_items],
                    "total": len(dataset.vbench_items),
                }, f, indent=2, ensure_ascii=False)

        # 5. 数据集元数据
        meta = {
            "name": dataset.name,
            "description": dataset.description,
            "stats": {
                "questions": len(dataset.questions),
                "vqa_pairs": len(dataset.vqa_pairs),
                "conversations": len(dataset.conversations),
                "vbench_items": len(dataset.vbench_items),
            },
            "created_at": dataset.created_at,
        }
        meta_path = os.path.join(output_dir, "dataset_metadata.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # 6. 数据集配置 (兼容datasets.load_dataset)
        config = {
            "dataset_name": dataset.name,
            "configs": ["questions", "vqa", "llava", "vbench"],
            "description": dataset.description,
        }
        config_path = os.path.join(output_dir, "dataset_config.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Benchmark dataset saved to {output_dir}")
        logger.info(f"  Questions: {len(dataset.questions)}")
        logger.info(f"  VQA pairs: {len(dataset.vqa_pairs)}")
        logger.info(f"  Conversations: {len(dataset.conversations)}")
        logger.info(f"  VBench items: {len(dataset.vbench_items)}")

        return output_dir

    # ========================================================================
    # 完整管线
    # ========================================================================

    def generate_full_benchmark(
        self,
        name: str = "multimodal_benchmark",
        image: Optional[Union[str, Image.Image]] = None,
        subjects: Optional[List[str]] = None,
        num_vqa: int = 10,
        num_llava_turns: int = 4,
    ) -> BenchmarkDataset:
        """
        生成完整的多模态评测数据集

        Args:
            name: 数据集名称
            image: 用于VQA和LLaVA的示例图像 (可选)
            subjects: MMMU学科列表
            num_vqa: VQA对数
            num_llava_turns: LLaVA对话轮次

        Returns:
            BenchmarkDataset
        """
        dataset = BenchmarkDataset(
            name=name,
            description=f"Multi-modal benchmark dataset generated by NanoBot Factory",
        )

        # 1. MMMU问题
        questions = self.generate_mmmu_style(subjects=subjects)
        dataset.questions = questions

        # 2. VQA对
        vqa_pairs = self.generate_vqa_pairs(image=image, num_pairs=num_vqa)
        dataset.vqa_pairs = vqa_pairs

        # 3. LLaVA对话
        conv = self.generate_llava_style(image=image, num_turns=num_llava_turns)
        dataset.conversations = [conv]

        # 4. VBench
        vbench = self.generate_vbench_items()
        dataset.vbench_items = vbench

        return dataset


# ============================================================================
# Convenience
# ============================================================================

def get_benchmark_generator() -> BenchmarkDataGenerator:
    """获取评测数据生成器实例"""
    return BenchmarkDataGenerator()
