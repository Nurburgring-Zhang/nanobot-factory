"""
NanoBot Factory - Edit Pipeline Tests
测试编辑指令自动生成管线

测试覆盖:
1. 编辑类型Taxonomy完整性 (20+种)
2. 指令模板生成
3. 模拟编辑效果 (PIL/CV2)
4. InstructPix2Pix格式
5. UltraEdit格式
6. AnyEdit格式
7. 批量生成
"""

import pytest
import sys
import os
import json
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEditPipeline:
    """编辑指令管线测试"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """每个测试前的设置"""
        img = Image.new("RGB", (256, 256), (100, 150, 200))
        self.test_image_path = str(tmp_path / "test_edit.png")
        img.save(self.test_image_path)
        self.test_image = img

    def test_import(self):
        """测试模块导入"""
        from data_edit_pipeline import EditInstructionPipeline, get_edit_pipeline
        assert EditInstructionPipeline is not None
        pipeline = get_edit_pipeline()
        assert isinstance(pipeline, EditInstructionPipeline)

    def test_edit_types_count(self):
        """验证编辑类型数量 >= 15"""
        from data_edit_pipeline import EDIT_TYPE_TAXONOMY
        assert len(EDIT_TYPE_TAXONOMY) >= 15, f"Only {len(EDIT_TYPE_TAXONOMY)} types"

    def test_taxonomy_structure(self):
        """验证编辑类型taxonomy结构"""
        from data_edit_pipeline import EDIT_TYPE_TAXONOMY
        for edit_type, config in EDIT_TYPE_TAXONOMY.items():
            assert "description" in config
            assert "templates" in config
            assert len(config["templates"]) > 0
            # 验证模板包含变量占位符或完整句子
            assert all(len(t) > 5 for t in config["templates"])

    def test_color_change(self):
        """测试颜色变化编辑"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="color_change",
            params={"color": "red", "object": "the car"}
        )
        assert result is not None
        assert result.edit_type == "color_change"
        assert "red" in result.instruction or "color" in result.instruction

    def test_background_replace(self):
        """测试背景替换"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="background_replace",
        )
        assert result is not None
        assert result.edit_type == "background_replace"
        assert len(result.instruction) > 10

    def test_style_transfer(self):
        """测试风格迁移"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="style_transfer",
            params={"style": "vintage"}
        )
        assert result is not None
        assert "vintage" in result.instruction.lower() or result.edit_type == "style_transfer"

    def test_season_change(self):
        """测试季节变化"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="season_change",
        )
        assert result is not None
        assert result.edit_type == "season_change"

    def test_weather_change(self):
        """测试天气变化"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="weather_change",
        )
        assert result is not None
        assert result.edit_type == "weather_change"

    def test_lighting_adjust(self):
        """测试光照调整"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="lighting_adjust",
        )
        assert result is not None
        # instruction 可能包含 lighting 或 illumination
        instr = result.instruction.lower()
        assert "lighting" in instr or "illumination" in instr

    def test_object_add_remove(self):
        """测试物体添加和移除"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        add_result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="object_add",
        )
        assert add_result is not None
        assert add_result.edit_type == "object_add"

        remove_result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="object_remove",
        )
        assert remove_result is not None
        assert remove_result.edit_type == "object_remove"

    def test_lighting_dramatic(self):
        """测试戏剧化光照"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="lighting_dramatic",
        )
        assert result is not None
        assert result.edit_type == "lighting_dramatic"

    def test_random_edit_type(self):
        """测试随机编辑类型"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(self.test_image_path)
        assert result is not None
        assert result.edit_type in pipeline.edit_types

    def test_item_dataclass(self):
        """测试EditInstructionItem结构"""
        from data_edit_pipeline import EditInstructionPipeline, EditInstructionItem
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="color_change",
        )
        assert isinstance(result, EditInstructionItem)
        assert result.id.startswith("edit_")
        assert result.source_image == self.test_image_path
        assert len(result.instruction) > 5
        assert result.source_caption
        assert result.target_caption

    def test_batch_generate(self):
        """测试批量生成"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        results = pipeline.batch_generate(
            [self.test_image_path, self.test_image],
            n_per_image=2,
        )
        assert len(results) >= 2

    def test_generate_all_types(self):
        """测试为单张图像生成所有编辑类型"""
        from data_edit_pipeline import EditInstructionPipeline, EDIT_TYPE_TAXONOMY
        pipeline = EditInstructionPipeline()
        results = pipeline.generate_all_types(self.test_image_path)
        assert len(results) == len(EDIT_TYPE_TAXONOMY)
        # 验证每种类型都有结果
        types_generated = set(r.edit_type for r in results)
        assert types_generated == set(EDIT_TYPE_TAXONOMY.keys())

    def test_save_instructpix2pix_jsonl(self, tmp_path):
        """测试InstructPix2Pix格式保存"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        items = [pipeline.generate_edit(self.test_image_path)]
        output = str(tmp_path / "instructpix2pix.jsonl")
        pipeline.save_instructpix2pix_jsonl(items, output)
        assert os.path.exists(output)
        with open(output, "r") as f:
            line = json.loads(f.readline())
        assert "input_image" in line
        assert "edited_image" in line
        assert "instruction" in line

    def test_save_ultraedit_jsonl(self, tmp_path):
        """测试UltraEdit格式保存"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        items = [pipeline.generate_edit(self.test_image_path)]
        output = str(tmp_path / "ultraedit.jsonl")
        pipeline.save_ultraedit_jsonl(items, output)
        assert os.path.exists(output)
        with open(output, "r") as f:
            line = json.loads(f.readline())
        assert "original_image" in line
        assert "edited_image" in line
        assert "instruction" in line
        assert "source_caption" in line
        assert "target_caption" in line

    def test_save_anyedit_jsonl(self, tmp_path):
        """测试AnyEdit格式保存"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        items = [pipeline.generate_edit(self.test_image_path)]
        output = str(tmp_path / "anyedit.jsonl")
        pipeline.save_anyedit_jsonl(items, output)
        assert os.path.exists(output)
        with open(output, "r") as f:
            line = json.loads(f.readline())
        assert "source" in line
        assert "target" in line
        assert "instruction" in line
        assert "edit_type" in line

    def test_material_change(self):
        """测试材质变化"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="material_change",
        )
        assert result is not None
        assert result.edit_type == "material_change"

    def test_color_saturation(self):
        """测试饱和度变化"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="color_saturation",
        )
        assert result is not None
        assert result.edit_type == "color_saturation"

    def test_color_temperature(self):
        """测试色温变化"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="color_temperature",
        )
        assert result is not None
        assert result.edit_type == "color_temperature"

    def test_background_blur(self):
        """测试背景模糊"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="background_blur",
        )
        assert result is not None
        assert result.edit_type == "background_blur"

    def test_object_resize(self):
        """测试物体大小变化"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="object_resize",
        )
        assert result is not None
        assert result.edit_type == "object_resize"

    def test_object_move(self):
        """测试物体移动"""
        from data_edit_pipeline import EditInstructionPipeline
        pipeline = EditInstructionPipeline()
        result = pipeline.generate_edit(
            self.test_image_path,
            edit_type="object_move",
        )
        assert result is not None
        assert result.edit_type == "object_move"
