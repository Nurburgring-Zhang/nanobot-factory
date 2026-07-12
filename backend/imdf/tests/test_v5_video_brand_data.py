"""智影 V5 — Video Harness + Brand Research + Data Gateway + MCP + Proactive + Monitor + Geo + Perf 测试"""
import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "1")
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-for-v5-1234567890abcdef")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-v5-p11b-1234567890")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

_IMDF = Path(__file__).resolve().parent.parent
_BACKEND = _IMDF.parent
sys.path = [p for p in sys.path if Path(p).resolve() != _BACKEND.resolve()]
_sp = str(_IMDF.resolve())
if _sp not in sys.path:
    sys.path.insert(0, _sp)


class TestV5VideoHarness(unittest.TestCase):
    """V5 Video Harness — 短剧创作"""

    def test_video_harness_create(self):
        """创建视频项目"""
        from imdf.intelligence_v5 import video_harness
        project = video_harness.create_project("一个关于赛博朋克的短剧")
        self.assertIsNotNone(project)
        self.assertIsNotNone(project.project_id)

    def test_video_harness_list(self):
        """列出项目"""
        from imdf.intelligence_v5 import video_harness
        video_harness.create_project("项目1")
        video_harness.create_project("项目2")
        projects = video_harness.list_projects()
        self.assertGreaterEqual(len(projects), 2)

    def test_video_harness_get_project(self):
        """按 ID 获取项目"""
        from imdf.intelligence_v5 import video_harness
        project = video_harness.create_project("查询测试")
        got = video_harness.get_project(project.project_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.project_id, project.project_id)

    def test_storyboard_engine(self):
        """StoryboardEngine"""
        from imdf.intelligence_v5 import StoryboardEngine
        engine = StoryboardEngine()
        self.assertIsNotNone(engine)

    def test_shot_types(self):
        """Shot 类型"""
        from imdf.intelligence_v5 import ShotType
        self.assertGreaterEqual(len(list(ShotType)), 5)

    def test_camera_movements(self):
        """镜头运动"""
        from imdf.intelligence_v5 import CameraMovement
        self.assertGreaterEqual(len(list(CameraMovement)), 5)

    def test_model_router(self):
        """模型路由"""
        from imdf.intelligence_v5 import ModelRouter
        router = ModelRouter()
        self.assertIsNotNone(router)


class TestV5BrandResearch(unittest.TestCase):
    """V5 Brand Research — 4 大技能"""

    def test_brand_researcher(self):
        """BrandResearcher"""
        from imdf.intelligence_v5 import BrandResearcher
        researcher = BrandResearcher()
        self.assertIsNotNone(researcher)

    def test_hook_categories(self):
        """Hook 类别"""
        from imdf.intelligence_v5 import HookCategory
        self.assertGreaterEqual(len(list(HookCategory)), 3)

    def test_ad_sources(self):
        """广告数据源"""
        from imdf.intelligence_v5 import (
            MetaAdLibrary, GoogleAdsTransparency, XMonitor, RedditMonitor
        )
        # 类存在即可
        self.assertIsNotNone(MetaAdLibrary)
        self.assertIsNotNone(GoogleAdsTransparency)
        self.assertIsNotNone(XMonitor)
        self.assertIsNotNone(RedditMonitor)

    def test_competitor_intel(self):
        """竞品情报"""
        from imdf.intelligence_v5 import CompetitorAdIntelligence
        intel = CompetitorAdIntelligence()
        self.assertIsNotNone(intel)


class TestV5DataGateway(unittest.TestCase):
    """V5 Data Gateway — RedFox 13 平台"""

    def test_platform_count(self):
        """至少 10 平台"""
        from imdf.intelligence_v5 import platform_registry
        count = len(platform_registry.platforms)
        self.assertGreaterEqual(count, 10)

    def test_platform_enum(self):
        """Platform 枚举"""
        from imdf.intelligence_v5 import Platform
        self.assertGreaterEqual(len(list(Platform)), 10)

    def test_data_categories(self):
        """DataCategory 类别"""
        from imdf.intelligence_v5 import DataCategory
        self.assertGreaterEqual(len(list(DataCategory)), 3)

    def test_data_gateway_client(self):
        """客户端创建"""
        from imdf.intelligence_v5 import DataGatewayClient, DataGatewayConfig
        config = DataGatewayConfig(api_key="test-key")
        client = DataGatewayClient(config)
        self.assertIsNotNone(client)


class TestV5MCP(unittest.TestCase):
    """V5 MCP — Comfy MCP 协议"""

    def test_mcp_server(self):
        """MCP Server"""
        from imdf.intelligence_v5 import mcp_server
        self.assertIsNotNone(mcp_server)

    def test_mcp_tools_count(self):
        """工具数"""
        from imdf.intelligence_v5 import mcp_server
        self.assertGreaterEqual(len(mcp_server.tools), 5)

    def test_mcp_tool_registry(self):
        """工具注册表"""
        from imdf.intelligence_v5 import tool_registry
        self.assertIsNotNone(tool_registry)


class TestV5Proactive(unittest.TestCase):
    """V5 Proactive — Vida 持续上下文 + 主动建议"""

    def test_proactive_engine(self):
        """Proactive 引擎"""
        from imdf.intelligence_v5 import proactive_engine
        self.assertIsNotNone(proactive_engine)

    def test_proactive_observe(self):
        """观察用户活动"""
        from imdf.intelligence_v5 import proactive_engine
        # observe 方法存在
        self.assertTrue(hasattr(proactive_engine, "observe"))


class TestV5Monitor(unittest.TestCase):
    """V5 Monitor — Bugu 状态监控"""

    def test_status_monitor(self):
        """状态监控器"""
        from imdf.intelligence_v5 import status_monitor
        self.assertIsNotNone(status_monitor)

    def test_agent_status_enum(self):
        """Agent 状态枚举"""
        from imdf.intelligence_v5 import AgentStatus
        self.assertGreaterEqual(len(list(AgentStatus)), 3)

    def test_heartbeat_sounds(self):
        """心跳音效"""
        from imdf.intelligence_v5 import HeartbeatSound
        self.assertGreaterEqual(len(list(HeartbeatSound)), 3)


class TestV5Geo(unittest.TestCase):
    """V5 Geo — MapLibre + Terrarium DEM"""

    def test_geo_engine(self):
        """Geo 引擎"""
        from imdf.intelligence_v5 import geo_engine
        self.assertIsNotNone(geo_engine)

    def test_terrarium_decode(self):
        """Terrarium RGB → 高程"""
        from imdf.intelligence_v5 import terrarium_decode
        # 标准值: 紫色=海平面=0m (R=128, G=0, B=0) → (128 * 256 + 0 + 0/256 - 32768) = 32768 - 32768 = 0
        # 高程=0 米
        elevation = terrarium_decode(128, 0, 0)
        self.assertAlmostEqual(elevation, 0.0, delta=1.0)

    def test_terrarium_encode(self):
        """高程 → Terrarium RGB"""
        from imdf.intelligence_v5 import terrarium_decode, terrarium_encode
        # 0 米 → 紫色 (R=128)
        r, g, b = terrarium_encode(0.0)
        decoded = terrarium_decode(r, g, b)
        self.assertAlmostEqual(decoded, 0.0, delta=1.0)

    def test_dem_tile_fetcher(self):
        """DEM 瓦片获取器"""
        from imdf.intelligence_v5 import DEMTileFetcher
        f = DEMTileFetcher()
        self.assertIsNotNone(f)

    def test_terrain_baker(self):
        """地形烘焙器"""
        from imdf.intelligence_v5 import TerrainBaker
        b = TerrainBaker()
        self.assertIsNotNone(b)

    def test_tile_exporter(self):
        """瓦片导出器"""
        from imdf.intelligence_v5 import tile_exporter
        self.assertIsNotNone(tile_exporter)

    def test_map_style(self):
        """地图样式"""
        from imdf.intelligence_v5 import MapStyle
        self.assertGreaterEqual(len(list(MapStyle)), 3)


class TestV5Perf(unittest.TestCase):
    """V5 Perf — 上下文压缩 + 提示缓存"""

    def test_prompt_cache_put_get(self):
        """缓存 put/get"""
        from imdf.intelligence_v5 import prompt_cache
        prompt_cache.put("k1", "v1")
        v = prompt_cache.get("k1")
        self.assertEqual(v, "v1")

    def test_prompt_cache_lru(self):
        """LRU 淘汰"""
        from imdf.intelligence_v5 import prompt_cache
        # 改 max_size 测淘汰
        prompt_cache.max_size = 2
        prompt_cache.clear()
        prompt_cache.put("a", 1)
        prompt_cache.put("b", 2)
        prompt_cache.put("c", 3)  # 触发 LRU
        stats = prompt_cache.get_stats()
        self.assertGreaterEqual(stats.get("evictions", 0), 1)

    def test_prompt_cache_ttl(self):
        """TTL 过期"""
        from imdf.intelligence_v5 import prompt_cache
        prompt_cache.put("ttl_key", "ttl_val", ttl=0.1)
        v = prompt_cache.get("ttl_key")
        self.assertEqual(v, "ttl_val")
        time.sleep(0.2)
        v2 = prompt_cache.get("ttl_key")
        self.assertIsNone(v2)

    def test_context_compressor_skips(self):
        """低于阈值不压缩"""
        from imdf.intelligence_v5 import context_compressor
        msgs = [{"role": "user", "content": "hi"}] * 3
        result, cr = context_compressor.compress(msgs)
        self.assertEqual(cr.compression_ratio, 1.0)
        self.assertEqual(len(result), 3)

    def test_context_compressor_compresses(self):
        """超阈值触发压缩"""
        from imdf.intelligence_v5 import context_compressor
        # 重新初始化更小阈值
        from imdf.intelligence_v5.perf.tuning import ContextCompressor
        # 大量内容触发 (直接构造更小阈值的实例)
        compressor = ContextCompressor(threshold_ratio=0.01, max_context_tokens=1000)
        long_msg = "x" * 10000
        msgs = [{"role": "user", "content": long_msg}] * 100
        result, cr = compressor.compress(msgs)
        # 压缩比 < 1.0
        self.assertLess(cr.compression_ratio, 1.0)

    def test_compression_strategy(self):
        """压缩策略"""
        from imdf.intelligence_v5 import CompressionStrategy
        self.assertGreaterEqual(len(list(CompressionStrategy)), 3)


class TestV5Collaboration(unittest.TestCase):
    """V5 Collaboration — 6 协作模式"""

    def test_collaboration_engine(self):
        """协作引擎"""
        from imdf.intelligence_v5 import collaboration_engine
        self.assertIsNotNone(collaboration_engine)

    def test_collaboration_modes(self):
        """6 模式"""
        from imdf.intelligence_v5 import CollaborationMode
        self.assertGreaterEqual(len(list(CollaborationMode)), 5)

    def test_session_lifecycle(self):
        """协作 session 启动"""
        from imdf.intelligence_v5 import collaboration_engine, CollaborationContext
        ctx = CollaborationContext(task="Test topic")
        session = collaboration_engine.create_roundtable(
            participant_ids=["bot1", "bot2"],
            leader_id="bot1",
            context=ctx,
        )
        self.assertIsNotNone(session)


if __name__ == "__main__":
    unittest.main()
