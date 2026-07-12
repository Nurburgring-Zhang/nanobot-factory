"""智影 V4 — Processing 6 模块集成测试"""
import os
import unittest

os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

from imdf.intelligence.crawler.base import RawDocument
from imdf.intelligence.processing.base import ProcessedItem, ProcessingMetrics
from imdf.intelligence.processing.dedupe import DedupeEngine, DedupStrategy
from imdf.intelligence.processing.cleaning import CleaningEngine, CleanStep
from imdf.intelligence.processing.auto_label import AutoLabelEngine, LabelModel
from imdf.intelligence.processing.scoring import ScoringEngine, ScoreDimension
from imdf.intelligence.processing.classify import ClassifyEngine, ClassifyTaxonomy, SUB_TAXONOMIES
from imdf.intelligence.processing.store import StorageEngine, StorageBackend


def make_item(
    url: str = "https://example.com/page1",
    text: str = "This is a test article about machine learning and AI for training data.",
    title: str = "Test Article",
    type_: str = "html",
    channel: str = "web_generic",
    hash_: str = "",
) -> ProcessedItem:
    """Helper"""
    if not hash_:
        import hashlib
        hash_ = hashlib.sha256((url + text).encode("utf-8")).hexdigest()
    return ProcessedItem(
        source_url=url,
        source_channel=channel,
        type=type_,
        title=title,
        text=text,
        content_hash=hash_,
        size_bytes=len(text),
    )


class TestProcessedItem(unittest.TestCase):
    def test_to_dict(self):
        item = make_item()
        d = item.to_dict()
        self.assertEqual(d["source_url"], "https://example.com/page1")
        self.assertEqual(d["title"], "Test Article")


class TestDedupeEngine(unittest.TestCase):
    def test_url_dedup(self):
        engine = DedupeEngine(strategies=[DedupStrategy.URL])
        items = [
            make_item(url="https://example.com/a"),
            make_item(url="https://example.com/a"),  # dup
            make_item(url="https://example.com/b"),
        ]
        out = engine.process(items)
        self.assertEqual(len(out), 2)
        self.assertEqual(engine.metrics.deduped, 1)

    def test_url_with_tracking_params(self):
        """URL 去重应去掉 utm_* 参数"""
        engine = DedupeEngine(strategies=[DedupStrategy.URL])
        items = [
            make_item(url="https://example.com/a?utm_source=x"),
            make_item(url="https://example.com/a"),
        ]
        out = engine.process(items)
        self.assertEqual(len(out), 1)

    def test_sha256_dedup(self):
        engine = DedupeEngine(strategies=[DedupStrategy.SHA256])
        items = [
            make_item(url="https://a.com/", text="hello world", hash_="h1"),
            make_item(url="https://b.com/", text="hello world", hash_="h1"),
        ]
        out = engine.process(items)
        self.assertEqual(len(out), 1)

    def test_simhash_dedup(self):
        engine = DedupeEngine(strategies=[DedupStrategy.SIMHASH], simhash_threshold=3)
        items = [
            make_item(url="https://a.com/", text="This is a long article about machine learning, AI, and data. " * 10),
            make_item(url="https://b.com/", text="This is a long article about machine learning, AI, and data. " * 10),
        ]
        out = engine.process(items)
        self.assertEqual(len(out), 1)

    def test_combined_strategies(self):
        engine = DedupeEngine(strategies=[DedupStrategy.URL, DedupStrategy.SHA256])
        items = [
            make_item(url="https://a.com/", text="a", hash_="h1"),
            make_item(url="https://a.com/", text="b", hash_="h2"),
            make_item(url="https://b.com/", text="a", hash_="h1"),
        ]
        out = engine.process(items)
        # a.com 被 URL 去重, h1 被 SHA256 去重
        self.assertEqual(len(out), 1)

    def test_reset(self):
        engine = DedupeEngine(strategies=[DedupStrategy.URL])
        items = [make_item(url="https://a.com/")]
        engine.process(items)
        engine.reset()
        # 重置后再次应能加进
        out = engine.process([make_item(url="https://a.com/")])
        self.assertEqual(len(out), 1)


class TestCleaningEngine(unittest.TestCase):
    def test_basic_clean(self):
        engine = CleaningEngine()
        items = [make_item(text="  hello    world\n\n\n\nfoo bar baz qux quux corge " * 3)]
        out = engine.process(items)
        self.assertEqual(len(out), 1)
        self.assertIn("hello", out[0].text)

    def test_unicode_normalize(self):
        engine = CleaningEngine(steps=[CleanStep.UNICODE_NORMALIZE], min_length=0)
        items = [make_item(text="café　naïve　 " * 10)]
        out = engine.process(items)
        self.assertGreater(len(out), 0)
        self.assertIn("café", out[0].text)

    def test_html_strip(self):
        engine = CleaningEngine(steps=[CleanStep.HTML_STRIP], min_length=0)
        items = [make_item(text="<p>Hello <b>world</b></p> " * 10)]
        out = engine.process(items)
        self.assertGreater(len(out), 0)
        self.assertNotIn("<p>", out[0].text)
        self.assertIn("Hello", out[0].text)

    def test_pii_removal(self):
        engine = CleaningEngine(steps=[CleanStep.REMOVE_PII], remove_pii=True, min_length=0)
        items = [make_item(text="Contact me at test@example.com or 13800138000 " * 10)]
        out = engine.process(items)
        self.assertNotIn("test@example.com", out[0].text)
        self.assertNotIn("13800138000", out[0].text)
        self.assertIn("REDACTED", out[0].text)

    def test_boilerplate_removal(self):
        engine = CleaningEngine(steps=[CleanStep.REMOVE_BOILERPLATE], min_length=0)
        items = [make_item(text="Subscribe to our newsletter\n\nReal content here for testing. " * 10)]
        out = engine.process(items)
        self.assertNotIn("newsletter", out[0].text)
        self.assertIn("Real content", out[0].text)

    def test_dedupe_lines(self):
        engine = CleaningEngine(steps=[CleanStep.REMOVE_DUPLICATE_LINES], min_length=0)
        items = [make_item(text="line1\nline1\nline2\nline2\nline3\nline4\nline5\nline6 " * 5)]
        out = engine.process(items)
        self.assertIn("line1", out[0].text)
        self.assertIn("line2", out[0].text)

    def test_short_content_rejected(self):
        engine = CleaningEngine(min_length=100)
        items = [make_item(text="too short")]
        out = engine.process(items)
        # 短文本会被拒绝
        self.assertEqual(len(out), 0)
        self.assertGreaterEqual(engine.metrics.rejected, 1)

    def test_lang_detect_chinese(self):
        engine = CleaningEngine(steps=[CleanStep.LANG_DETECT], min_length=0)
        items = [make_item(text="这是一段关于机器学习和人工智能的中文测试文本,用于训练数据的语言检测。" * 5)]
        out = engine.process(items)
        self.assertEqual(out[0].language, "zh")

    def test_lang_detect_english(self):
        engine = CleaningEngine(steps=[CleanStep.LANG_DETECT])
        items = [make_item(text="This is an English text about machine learning and artificial intelligence for training data. " * 5)]
        out = engine.process(items)
        self.assertEqual(out[0].language, "en")


class TestAutoLabelEngine(unittest.TestCase):
    def test_basic_label(self):
        engine = AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS], consensus_threshold=2)
        items = [make_item(text="machine learning and python programming in data science, technology, software, ai " * 5)]
        out = engine.process(items)
        self.assertGreater(len(out[0].labels), 0)

    def test_rule_labeling_github(self):
        engine = AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS])
        items = [make_item(url="https://github.com/user/repo", text="code repository with python " * 5)]
        out = engine.process(items)
        self.assertIn("code", out[0].labels)

    def test_keyword_labeling_tech(self):
        engine = AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS])
        items = [make_item(text="machine learning AI software programming computer algorithm technology data " * 5)]
        out = engine.process(items)
        self.assertIn("tech", out[0].labels)

    def test_no_labels_for_unrelated(self):
        engine = AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS])
        items = [make_item(text="xxxxxxxxxx yyyyyyyyyy zzzzzzzzzz aaaaaaa bbbbbbb")]
        out = engine.process(items)
        # 可能没标签 (因为没共识)
        self.assertIsInstance(out[0].labels, list)

    def test_consensus_threshold(self):
        engine = AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS], consensus_threshold=3)
        items = [make_item(text="machine learning and AI")]
        out = engine.process(items)
        # 高 threshold → 标签少
        self.assertIsInstance(out[0].labels, list)


class TestScoringEngine(unittest.TestCase):
    def test_quality_score(self):
        engine = ScoringEngine(dimensions=[ScoreDimension.QUALITY])
        items = [make_item(text="This is a comprehensive test article about machine learning, AI, and data science. " * 10)]
        out = engine.process(items)
        self.assertGreater(out[0].quality_score, 0.5)

    def test_aesthetic_score_text(self):
        engine = ScoringEngine(dimensions=[ScoreDimension.AESTHETIC])
        items = [make_item(type_="text", text="hello")]
        out = engine.process(items)
        # 文本类型 → 默认 0.5
        self.assertEqual(out[0].aesthetic_score, 0.5)

    def test_safety_score_clean(self):
        engine = ScoringEngine(dimensions=[ScoreDimension.SAFETY])
        items = [make_item(text="A normal article about science and education.")]
        out = engine.process(items)
        self.assertEqual(out[0].custom_scores["safety"], 1.0)

    def test_safety_score_spam(self):
        engine = ScoringEngine(dimensions=[ScoreDimension.SAFETY])
        items = [make_item(text="Earn $5000 per day! Click here for free trial viagra")]
        out = engine.process(items)
        self.assertLess(out[0].custom_scores["safety"], 1.0)

    def test_diversity_score(self):
        engine = ScoringEngine(dimensions=[ScoreDimension.DIVERSITY])
        items = [make_item(text="apple banana cherry durian elderberry fig grape")]
        out = engine.process(items)
        # 全部唯一词 → diversity = 1.0
        self.assertGreater(out[0].custom_scores["diversity"], 0.9)

    def test_completeness(self):
        engine = ScoringEngine(dimensions=[ScoreDimension.COMPLETENESS])
        items = [make_item(text="A test article with content for completeness scoring evaluation. " * 5)]
        out = engine.process(items)
        self.assertGreater(out[0].custom_scores["completeness"], 0.5)


class TestClassifyEngine(unittest.TestCase):
    def test_image_classification(self):
        engine = ClassifyEngine()
        items = [ProcessedItem(
            source_url="https://example.com/img.jpg",
            type="image",
            title="Beautiful landscape",
            text="A beautiful landscape with mountains and ocean scenery.",
            images=["https://example.com/img.jpg"],
        )]
        out = engine.process(items)
        self.assertEqual(out[0].modality, "image")
        self.assertIn("Nature", out[0].domain)

    def test_video_classification(self):
        engine = ClassifyEngine()
        items = [ProcessedItem(
            source_url="https://youtube.com/watch?v=xxx",
            type="video",
            title="My vlog",
            text="A vlog about my daily life and travel.",
        )]
        out = engine.process(items)
        self.assertEqual(out[0].modality, "video")
        self.assertEqual(out[0].domain, "vlog")

    def test_text_classification(self):
        engine = ClassifyEngine()
        items = [ProcessedItem(
            source_url="https://github.com/abc/def",
            type="text",
            text="def hello():\n    print('Hello world')\n",
        )]
        out = engine.process(items)
        self.assertEqual(out[0].modality, "text")

    def test_image_edit_classification(self):
        engine = ClassifyEngine()
        items = [ProcessedItem(
            source_url="https://example.com/",
            type="image",
            title="Inpainting result",
            text="This is an inpainting of the original image.",
        )]
        out = engine.process(items)
        self.assertEqual(out[0].modality, "image_edit")

    def test_all_taxonomies(self):
        """8 业务模态都定义"""
        self.assertEqual(len(ClassifyTaxonomy), 8)
        for m in ClassifyTaxonomy:
            self.assertIn(m, SUB_TAXONOMIES)
            self.assertGreater(len(SUB_TAXONOMIES[m]), 0)


class TestStorageEngine(unittest.TestCase):
    def test_local_storage(self):
        engine = StorageEngine(content_backend=StorageBackend.LOCAL)
        items = [make_item(text="content to store" * 10)]
        out = engine.process(items)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].media_uri.startswith("file:///"))
        self.assertEqual(engine.get_index_size(), 1)

    def test_lineage(self):
        engine = StorageEngine()
        items = [make_item(url="https://example.com/a"), make_item(url="https://example.com/b")]
        engine.process(items)
        lineage = engine.get_lineage()
        self.assertEqual(len(lineage), 2)

    def test_lineage_filter(self):
        engine = StorageEngine()
        items = [make_item(url="https://example.com/a", hash_="hashA"), make_item(url="https://example.com/b", hash_="hashB")]
        engine.process(items)
        # 找 hashA
        lineage = engine.get_lineage(content_hash="hashA")
        self.assertEqual(len(lineage), 1)

    def test_export_index(self):
        engine = StorageEngine()
        items = [make_item()]
        engine.process(items)
        idx = engine.export_index()
        self.assertEqual(len(idx), 1)
        self.assertIn("title", idx[0])


class TestProcessingPipelineIntegration(unittest.TestCase):
    """全流水线集成测试"""

    def test_full_pipeline(self):
        from imdf.intelligence.platform_agents.pipeline import PipelineAgent
        from imdf.intelligence.processing.base import ProcessedItem
        # 准备 3 条 item
        items = [
            ProcessedItem(
                source_url="https://example.com/1",
                type="text",
                title="ML Article",
                text="This is a machine learning article about Python and AI. " * 5,
                content_hash="h1",
            ),
            ProcessedItem(
                source_url="https://example.com/1",  # URL dup
                type="text",
                title="ML Article",
                text="Different content",
                content_hash="h2",
            ),
            ProcessedItem(
                source_url="https://example.com/2",
                type="text",
                title="Data Science",
                text="Data science and visualization are important. " * 5,
                content_hash="h3",
            ),
        ]
        # 跑全流水线
        agent = PipelineAgent()
        result = agent.run_full_pipeline(items)
        # 1 个 URL dup 应被去重
        self.assertLessEqual(result["final_count"], 2)
        # 各阶段 metrics
        self.assertIn("dedupe", result["stage_metrics"])
        self.assertIn("clean", result["stage_metrics"])
        self.assertIn("label", result["stage_metrics"])
        self.assertIn("score", result["stage_metrics"])
        self.assertIn("classify", result["stage_metrics"])
        self.assertIn("store", result["stage_metrics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
