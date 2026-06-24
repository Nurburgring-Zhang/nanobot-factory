"""
NanoBot Factory - 高级模块测试
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==================== AIAutomation测试 ====================

class TestAIAutomation:
    """AI自动化系统测试"""

    def test_region_enum(self):
        """测试区域枚举"""
        from agent.ai_automation import Region
        assert Region.CHINA.value == "china"
        assert Region.GLOBAL.value == "global"

    def test_data_source_type(self):
        """测试数据源类型"""
        from agent.ai_automation import DataSourceType
        assert DataSourceType.NEWS.value == "news"
        assert DataSourceType.RSS.value == "rss"

    def test_content_type(self):
        """测试内容类型"""
        from agent.ai_automation import ContentType
        assert ContentType.TEXT.value == "text"
        assert ContentType.VIDEO.value == "video"

    def test_topic_category(self):
        """测试话题分类"""
        from agent.ai_automation import TopicCategory
        assert TopicCategory.TECHNOLOGY.value == "technology"
        assert TopicCategory.FINANCE.value == "finance"

    def test_sentiment_type(self):
        """测试情感类型"""
        from agent.ai_automation import SentimentType
        assert SentimentType.POSITIVE.value == "positive"
        assert SentimentType.NEGATIVE.value == "negative"

    def test_data_source_creation(self):
        """测试数据源创建"""
        from agent.ai_automation import DataSource, DataSourceType, Region
        source = DataSource(
            source_id="test_src",
            name="测试源",
            url="https://example.com",
            source_type=DataSourceType.NEWS,
            region=Region.CHINA,
            language="zh"
        )
        assert source.source_id == "test_src"
        assert source.is_active == True

    def test_collected_item_creation(self):
        """测试采集项创建"""
        from agent.ai_automation import CollectedItem, ContentType, Region
        item = CollectedItem(
            item_id="item_001",
            source_id="src_001",
            url="https://example.com/article",
            title="测试文章",
            content="这是测试内容",
            content_type=ContentType.TEXT,
            region=Region.GLOBAL
        )
        assert item.item_id == "item_001"
        assert item.quality_score == 0.5

    def test_hot_topic_creation(self):
        """测试热点话题创建"""
        from agent.ai_automation import HotTopic, TopicCategory, Region
        from datetime import datetime
        topic = HotTopic(
            topic_id="topic_001",
            keywords=["AI", "科技"],
            title="AI技术热点",
            description="讨论AI最新进展",
            topic_category=TopicCategory.TECHNOLOGY,
            heat_score=85.5,
            trend_direction="up",
            first_appeared=datetime.now(),
            last_updated=datetime.now(),
            total_mentions=1000,
            region=Region.GLOBAL
        )
        assert topic.heat_score == 85.5
        assert topic.trend_direction == "up"

    def test_web_scraper_init(self):
        """测试网页抓取器初始化"""
        from agent.ai_automation import WebScraper
        scraper = WebScraper(timeout=30, max_retries=3)
        assert scraper.timeout == 30
        assert scraper.max_retries == 3

    def test_sentiment_analyzer(self):
        """测试情感分析器"""
        from agent.ai_automation import SentimentAnalyzer, SentimentType
        analyzer = SentimentAnalyzer()
        sentiment, score = analyzer.analyze("这是一个非常好的消息，太棒了！")
        assert sentiment in [SentimentType.POSITIVE, SentimentType.NEUTRAL]

    def test_topic_tracker(self):
        """测试话题追踪器"""
        from agent.ai_automation import TopicTracker
        from datetime import datetime
        tracker = TopicTracker(window_minutes=60)
        tracker.record_mention("AI", datetime.now())
        heat = tracker.calculate_heat("AI")
        assert heat > 0

    def test_agent_reach_system_init(self):
        """测试AgentReach系统初始化"""
        from agent.ai_automation import AgentReachSystem, Region
        system = AgentReachSystem(max_workers=3)
        assert system.max_workers == 3
        assert len(system.data_sources) > 0  # 默认数据源

    def test_world_monitor_init(self):
        """测试WorldMonitor初始化"""
        from agent.ai_automation import WorldMonitor, TopicCategory
        monitor = WorldMonitor(track_window=60)
        assert monitor.tracker.window_minutes == 60
        assert TopicCategory.TECHNOLOGY in monitor.keywords

    def test_data_processor(self):
        """测试数据处理器"""
        from agent.ai_automation import DataProcessor, CollectedItem, ContentType, Region
        processor = DataProcessor()
        items = [
            CollectedItem(
                item_id="1", source_id="s1", url="u1",
                title="t1", content="c1", content_type=ContentType.TEXT,
                region=Region.GLOBAL, is_processed=False
            )
        ]
        processed = processor.process(items)
        assert processed[0].is_processed == True

    def test_information_fusion(self):
        """测试信息融合"""
        from agent.ai_automation import InformationFusion, CollectedItem, ContentType, Region
        fusion = InformationFusion()
        items = [
            CollectedItem(
                item_id="1", source_id="s1", url="u1",
                title="t1", content="c1", content_type=ContentType.TEXT,
                region=Region.CHINA
            ),
            CollectedItem(
                item_id="2", source_id="s2", url="u2",
                title="t2", content="c2", content_type=ContentType.TEXT,
                region=Region.GLOBAL
            )
        ]
        result = fusion.fuse(items)
        assert result['total_items'] == 2

    def test_ai_automation_engine_init(self):
        """测试AI自动化引擎初始化"""
        from agent.ai_automation import AIAutomationEngine
        engine = AIAutomationEngine()
        assert engine.agent_reach is not None
        assert engine.world_monitor is not None
        assert engine.processor is not None


# ==================== 安全认证测试 ====================

class TestSecurityAuth:
    """安全认证系统测试"""

    def test_auth_provider_enum(self):
        """测试认证提供者枚举"""
        from security.auth import AuthProvider
        assert AuthProvider.LOCAL.value == "local"
        assert AuthProvider.OAUTH2.value == "oauth2"

    def test_user_role_enum(self):
        """测试用户角色枚举"""
        from security.auth import UserRole
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.USER.value == "user"

    def test_permission_enum(self):
        """测试权限枚举"""
        from security.auth import Permission
        assert Permission.USER_CREATE.value == "user:create"
        assert Permission.TOOL_EXECUTE.value == "tool:execute"

    def test_user_creation(self):
        """测试用户创建"""
        from security.auth import User, UserRole, Permission
        user = User(
            user_id="user_001",
            username="testuser",
            email="test@example.com",
            role=UserRole.USER
        )
        assert user.username == "testuser"
        assert user.is_active == True

    def test_api_key_creation(self):
        """测试API密钥创建"""
        from security.auth import APIKey, Permission
        key = APIKey(
            key_id="key_001",
            user_id="user_001",
            key_hash="abc123",
            name="Test Key"
        )
        assert key.key_id == "key_001"
        assert key.is_active == True

    def test_password_manager_hash(self):
        """测试密码哈希"""
        from security.auth import PasswordManager
        hashed, salt = PasswordManager.hash_password("testpass123")
        assert len(hashed) > 0
        assert len(salt) > 0

    def test_password_manager_verify(self):
        """测试密码验证"""
        from security.auth import PasswordManager
        hashed, salt = PasswordManager.hash_password("testpass123")
        assert PasswordManager.verify_password("testpass123", hashed, salt) == True
        assert PasswordManager.verify_password("wrongpass", hashed, salt) == False

    def test_jwt_manager_create_token(self):
        """测试JWT令牌创建"""
        from security.auth import JWTManager, Permission
        manager = JWTManager("test_secret_key")
        token = manager.create_token("user_001", [Permission.USER_READ])
        assert len(token) > 0

    def test_jwt_manager_verify_token(self):
        """测试JWT令牌验证"""
        from security.auth import JWTManager, Permission
        manager = JWTManager("test_secret_key")
        token = manager.create_token("user_001", [Permission.USER_READ])
        payload = manager.verify_token(token)
        assert payload is not None
        assert payload['user_id'] == "user_001"

    def test_permission_manager(self):
        """测试权限管理器"""
        from security.auth import PermissionManager, UserRole
        admin_perms = PermissionManager.get_role_permissions(UserRole.ADMIN)
        user_perms = PermissionManager.get_role_permissions(UserRole.USER)
        assert len(admin_perms) > len(user_perms)

    def test_auth_manager_init(self):
        """测试认证管理器初始化"""
        from security.auth import AuthManager
        auth = AuthManager("jwt_secret_123")
        assert "admin" in auth.users

    def test_auth_manager_register(self):
        """测试用户注册"""
        from security.auth import AuthManager, UserRole
        auth = AuthManager("jwt_secret_123")
        user_id = auth.register_user("newuser", "new@example.com", "pass123", UserRole.USER)
        assert user_id.startswith("user_")

    def test_auth_manager_authenticate(self):
        """测试用户认证"""
        from security.auth import AuthManager
        auth = AuthManager("jwt_secret_123")
        token = auth.authenticate("admin", "admin123")
        assert token is not None

    def test_rate_limiter(self):
        """测试速率限制器"""
        from security.auth import RateLimiter
        limiter = RateLimiter(calls_per_minute=60, calls_per_hour=1000)
        # 第一次调用应该通过
        assert limiter.check("user_001") == True

    def test_access_controller(self):
        """测试访问控制器"""
        from security.auth import AccessController, AuthManager
        auth = AuthManager("secret")
        controller = AccessController(auth)
        assert controller.auth_manager is not None


# ==================== 高级视频模型测试 ====================

class TestAdvancedVideoModels:
    """高级视频模型测试"""

    def test_video_model_type_enum(self):
        """测试视频模型类型枚举"""
        from omni_gen_studio.backend_modules.advanced_video_models import VideoModelType
        assert VideoModelType.WAN_2_2.value == "wan_2_2"
        assert VideoModelType.COGVIDEO.value == "cogvideo"

    def test_video_generation_config(self):
        """测试视频生成配置"""
        from omni_gen_studio.backend_modules.advanced_video_models import VideoGenerationConfig, VideoModelType
        config = VideoGenerationConfig(
            model_type=VideoModelType.WAN_2_2,
            num_frames=32,
            fps=24
        )
        assert config.num_frames == 32
        assert config.fps == 24

    def test_video_generation_result(self):
        """测试视频生成结果"""
        from omni_gen_studio.backend_modules.advanced_video_models import VideoGenerationResult
        result = VideoGenerationResult(success=True, output_path="/path/to/video.mp4")
        assert result.success == True
        assert result.output_path == "/path/to/video.mp4"

    def test_wan22_generator_init(self):
        """测试Wan2.2生成器初始化"""
        from omni_gen_studio.backend_modules.advanced_video_models import Wan22VideoGenerator
        gen = Wan22VideoGenerator()
        assert gen.device in ["cuda", "cpu", "mps"]

    def test_ltx_generator_init(self):
        """测试LTX-Video生成器初始化"""
        from omni_gen_studio.backend_modules.advanced_video_models import LTXVideoGenerator
        gen = LTXVideoGenerator()
        assert gen.device in ["cuda", "cpu"]

    def test_cogvideo_generator_init(self):
        """测试CogVideo生成器初始化"""
        from omni_gen_studio.backend_modules.advanced_video_models import CogVideoGenerator
        gen = CogVideoGenerator()
        assert gen.device in ["cuda", "cpu"]

    def test_i2vgenxl_generator_init(self):
        """测试I2VGen-XL生成器初始化"""
        from omni_gen_studio.backend_modules.advanced_video_models import I2VGenXLGenerator
        gen = I2VGenXLGenerator()
        assert gen.device in ["cuda", "cpu"]

    def test_advanced_video_manager_init(self):
        """测试高级视频管理器初始化"""
        from omni_gen_studio.backend_modules.advanced_video_models import AdvancedVideoManager, VideoModelType
        manager = AdvancedVideoManager()
        assert VideoModelType.WAN_2_2 in manager.generators
        assert VideoModelType.LTX_VIDEO in manager.generators
        assert VideoModelType.COGVIDEO in manager.generators

    def test_get_supported_models(self):
        """测试获取支持的模型"""
        from omni_gen_studio.backend_modules.advanced_video_models import AdvancedVideoManager
        manager = AdvancedVideoManager()
        models = manager.get_supported_models()
        assert len(models) >= 4  # 至少4个模型


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
