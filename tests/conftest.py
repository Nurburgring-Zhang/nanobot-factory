"""pytest conftest — 全局fixtures和配置"""
import os
import sys
import pytest

# 设置JWT_SECRET避免auth模块import失败
os.environ.setdefault('JWT_SECRET', 'test-jwt-secret-for-pytest-only-do-not-use-in-prod')

# 添加IMDF路径
_imdf_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'imdf')
if os.path.isdir(_imdf_path) and _imdf_path not in sys.path:
    sys.path.insert(0, _imdf_path)


@pytest.fixture
def test_data_dir(tmp_path):
    """创建临时测试数据目录"""
    return tmp_path


@pytest.fixture
def sample_annotations():
    """Fleiss Kappa 测试用的标注矩阵"""
    return [
        [1, 2, 2],
        [2, 2, 1],
        [3, 1, 3],
        [2, 1, 2],
    ]


@pytest.fixture
def sample_texts():
    """去重测试用的文本列表"""
    return [
        "这是一段测试文本",
        "这是另一段测试文本",
        "这是一段测试文本",  # 重复
        "完全不同的文本内容",
    ]
