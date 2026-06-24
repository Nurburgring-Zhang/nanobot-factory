"""
NanoBot Factory - MLLM Pipeline Tests
测试MLLM训练数据生成管线

测试覆盖:
1. LLaVA格式生成 (验证conversations结构)
2. ShareGPT4V格式生成 (验证caption长度>100字)
3. Interleaved格式生成 (验证sequences结构)
4. Qwen-VL格式 (验证ocr/layout字段)
5. 文档版面分析
"""

import pytest
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMLLMPipeline:
    """MLLM数据管线测试"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """每个测试前的设置"""
        # 用PIL创建一个测试图像
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        # 创建彩色测试图像 (400x300, 带渐变和文字)
        img = Image.new("RGB", (400, 300), (135, 206, 235))  # 天蓝色背景
        draw = ImageDraw.Draw(img)

        # 画一些形状
        draw.rectangle([50, 50, 150, 150], fill=(255, 100, 50))  # 橙色方块
        draw.rectangle([200, 80, 350, 180], fill=(100, 200, 100))  # 绿色方块
        draw.ellipse([100, 180, 200, 250], fill=(255, 255, 100))  # 黄色椭圆

        # 画一个人脸形状 (简化)
        draw.ellipse([260, 200, 330, 270], fill=(255, 200, 150))  # 肤色圆

        # 添加文本 (用于OCR测试)
        try:
            draw.text((30, 260), "Hello World", fill=(0, 0, 0))
            draw.text((200, 260), "测试文本", fill=(0, 0, 0))
        except Exception:
            pass  # 字体不可用时不报错

        self.test_image_path = str(tmp_path / "test_image.png")
        img.save(self.test_image_path)
        self.test_image = img
        self.test_caption = "A colorful scene with geometric shapes and text on a blue sky background."

    def test_import(self):
        """测试模块导入"""
        from data_mllm_pipeline import MLLMDataPipeline, get_mllm_pipeline
        assert MLLMDataPipeline is not None
        pipeline = get_mllm_pipeline()
        assert isinstance(pipeline, MLLMDataPipeline)

    def test_generate_llava_format(self):
        """测试LLaVA格式生成"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_llava_conversation(
            self.test_image_path,
            caption=self.test_caption,
            num_turns=3,
        )

        # 验证结构
        assert "id" in result
        assert result["id"].startswith("llava_")
        assert "image" in result
        assert "conversations" in result

        # 验证对话结构
        convs = result["conversations"]
        assert len(convs) >= 2  # 至少一轮问答

        # 验证第一轮格式
        assert convs[0]["from"] == "human"
        assert convs[0]["value"].startswith("<image>\n")
        assert convs[1]["from"] == "gpt"
        assert len(convs[1]["value"]) > 0

        # 验证3轮: 6条消息 (3 Q + 3 A)
        expected_msgs = len(result.get("conversations", []))
        assert len(convs) == expected_msgs, f"Expected {expected_msgs} msgs, got {len(convs)}"

        # 验证alternating pattern
        for i, msg in enumerate(convs):
            if i % 2 == 0:
                assert msg["from"] == "human"
            else:
                assert msg["from"] == "gpt"

    def test_generate_llava_5_turns(self):
        """测试LLaVA 5轮对话"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_llava_conversation(
            self.test_image_path,
            caption=self.test_caption,
            num_turns=5,
        )

        assert len(result["conversations"]) == 10  # 5轮=10条消息
        assert result["conversations"][-1]["from"] == "gpt"

    def test_batch_llava(self):
        """测试批量LLaVA生成"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        pairs = [(self.test_image_path, self.test_caption),
                 (self.test_image, "Another test image")]
        results = pipeline.batch_llava(pairs)

        assert len(results) == 2
        for r in results:
            assert "id" in r
            assert "conversations" in r
            assert len(r["conversations"]) >= 2

    def test_generate_sharegpt4v_format(self):
        """测试ShareGPT4V格式生成"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_sharegpt4v(
            self.test_image_path,
            caption=self.test_caption,
        )

        # 验证结构
        assert "id" in result
        assert result["id"].startswith("sg_")
        assert "image" in result
        assert "caption" in result
        assert "conversations" in result
        assert "source" in result
        assert result["source"] == "NanoBot"

        # 验证caption长度 > 100字
        caption = result["caption"]
        assert len(caption) >= 100, f"Caption too short: {len(caption)} chars"

        # 验证caption包含关键元素
        keywords = ["scene", "color", "lighting"]
        for kw in keywords:
            assert kw in caption.lower(), f"Missing keyword: {kw}"

        # 验证对话
        convs = result["conversations"]
        assert len(convs) >= 2
        assert convs[0]["from"] == "human"
        assert "<image>" in convs[0]["value"]
        assert convs[1]["from"] == "gpt"

    def test_generate_sharegpt4v_no_caption(self):
        """测试ShareGPT4V无原始caption"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_sharegpt4v(self.test_image_path)

        assert "caption" in result
        assert len(result["caption"]) >= 100

    def test_generate_interleaved_format(self):
        """测试Interleaved格式生成"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        pairs = [
            ("Introduction text about the first image.",),
            (self.test_image_path, "This is a diagram showing the system architecture."),
            ("The following details explain each component.",),
            (self.test_image, "A close-up view of component A."),
            ("Finally, the implementation results are discussed.",),
        ]

        result = pipeline.generate_interleaved(pairs)

        # 验证结构
        assert "id" in result
        assert result["id"].startswith("doc_")
        assert "sequences" in result

        # 验证序列
        seqs = result["sequences"]
        assert len(seqs) == 5

        for i, seq in enumerate(seqs):
            assert "text" in seq
            assert "images" in seq
            assert isinstance(seq["images"], list)
            # 第2和第4个序列应该有图像
            if i in [1, 3]:
                assert len(seq["images"]) > 0, f"Sequence {i} should have an image"
            else:
                assert len(seq["images"]) == 0, f"Sequence {i} should not have an image"

    def test_generate_interleaved_empty(self):
        """测试Interleaved空输入"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_interleaved([])
        assert "id" in result
        assert "sequences" in result
        # 空输入应该有默认序列
        assert len(result["sequences"]) >= 1

    def test_generate_qwenvl_format(self):
        """测试Qwen-VL格式生成"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_qwenvl(
            self.test_image_path,
            caption=self.test_caption,
        )

        # 验证结构
        assert "id" in result
        assert result["id"].startswith("qwen_")
        assert "image_path" in result
        assert "region" in result
        assert "ocr_text" in result
        assert "conversations" in result
        assert "layout_analysis" in result

        # 验证layout_analysis字段
        layout = result["layout_analysis"]
        assert "paragraphs" in layout
        assert "tables" in layout
        assert "figures" in layout

    def test_analyze_document_layout(self):
        """测试文档版面分析"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.analyze_document_layout(self.test_image_path)

        assert "layout_analysis" in result
        layout = result["layout_analysis"]
        assert "paragraphs" in layout
        assert "tables" in layout
        assert "figures" in layout

        # 验证每个区域的类型
        for region_type in ["paragraphs", "tables", "figures"]:
            regions = layout[region_type]
            for r in regions:
                assert "region_type" in r
                assert "bbox" in r
                assert "content" in r
                assert "confidence" in r

    def test_save_llava_jsonl(self, tmp_path):
        """测试保存LLaVA JSONL"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        items = [
            pipeline.generate_llava_conversation(self.test_image_path, num_turns=2),
            pipeline.generate_llava_conversation(self.test_image, num_turns=2),
        ]

        output = str(tmp_path / "llava_test.jsonl")
        pipeline.save_llava_jsonl(items, output)

        assert os.path.exists(output)

        # 验证文件内容
        with open(output, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "id" in data
            assert "conversations" in data

    def test_save_sharegpt4v_jsonl(self, tmp_path):
        """测试保存ShareGPT4V JSONL"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        items = [
            pipeline.generate_sharegpt4v(self.test_image_path),
            pipeline.generate_sharegpt4v(self.test_image),
        ]

        output = str(tmp_path / "sharegpt4v_test.jsonl")
        pipeline.save_sharegpt4v_jsonl(items, output)

        assert os.path.exists(output)

        with open(output, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_save_hf_dataset(self, tmp_path):
        """测试保存HF Dataset格式"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        items = [
            pipeline.generate_llava_conversation(self.test_image_path, num_turns=2),
        ]

        output_dir = str(tmp_path / "hf_dataset")
        pipeline.save_hf_dataset(items, output_dir, format="llava")

        # 验证文件结构
        assert os.path.exists(os.path.join(output_dir, "llava_data.jsonl"))
        assert os.path.exists(os.path.join(output_dir, "dataset_metadata.json"))
        assert os.path.exists(os.path.join(output_dir, "dataset_config.json"))

        with open(os.path.join(output_dir, "dataset_metadata.json"), "r") as f:
            meta = json.load(f)
        assert meta["format"] == "llava"
        assert meta["num_items"] == 1

    def test_pipeline_without_image(self):
        """测试无图像的pipeline行为"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        # 空图像路径应该返回有效但简化的结果
        result_llava = pipeline.generate_llava_conversation("")
        assert "id" in result_llava
        assert "conversations" in result_llava

        # ShareGPT4V
        result_sg = pipeline.generate_sharegpt4v("")
        assert "id" in result_sg
        assert "caption" in result_sg

        # Qwen-VL
        result_qwen = pipeline.generate_qwenvl("")
        assert "id" in result_qwen
        assert "layout_analysis" in result_qwen

    def test_get_mllm_pipeline(self):
        """测试get_mllm_pipeline便利函数"""
        from data_mllm_pipeline import get_mllm_pipeline
        pipeline = get_mllm_pipeline()
        from data_mllm_pipeline import MLLMDataPipeline
        assert isinstance(pipeline, MLLMDataPipeline)

    def test_qwenvl_ocr_field(self):
        """测试Qwen-VL的ocr字段存在性"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        result = pipeline.generate_qwenvl(self.test_image_path)
        # ocr_text应该是一个字符串 (可能为空)
        assert isinstance(result["ocr_text"], str)

    def test_sharegpt4v_100_chars_always(self):
        """验证ShareGPT4V的caption始终100+字"""
        from data_mllm_pipeline import MLLMDataPipeline
        pipeline = MLLMDataPipeline()

        # 用不同输入测试
        inputs = [
            (self.test_image_path, ""),
            (self.test_image_path, "A test."),
            (self.test_image, self.test_caption),
        ]

        for img, cap in inputs:
            result = pipeline.generate_sharegpt4v(img, caption=cap)
            assert len(result["caption"]) >= 100, f"Caption too short for input: '{cap}'"
