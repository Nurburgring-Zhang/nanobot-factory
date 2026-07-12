"""
P19 v5.1-B — test_skills_registry

验证 SkillRegistryV51 的注册 / 查询 / 搜索 / trigger_match / 序列化
"""

import json

import pytest

from backend.skills import SkillSpec
from backend.skills_manager import SkillRegistry, SkillRegistryV51
from backend.skills_builtin import BUILTIN_SKILLS


@pytest.fixture
def empty_registry() -> SkillRegistryV51:
    return SkillRegistryV51()


@pytest.fixture
def filled_registry() -> SkillRegistryV51:
    return SkillRegistryV51.from_builtin(BUILTIN_SKILLS)


class TestRegister:
    def test_register_one(self, empty_registry):
        s = SkillSpec(id="x1", name="X1", category="crawl")
        assert empty_registry.register(s) is True
        assert len(empty_registry) == 1
        assert "x1" in empty_registry

    def test_register_duplicate_raises(self, empty_registry):
        s = SkillSpec(id="dup", name="Dup", category="crawl")
        empty_registry.register(s)
        with pytest.raises(ValueError):
            empty_registry.register(s)

    def test_register_all(self, empty_registry):
        n = empty_registry.register_all(BUILTIN_SKILLS)
        assert n == 50
        assert len(empty_registry) == 50


class TestQueries:
    def test_get(self, filled_registry):
        s = filled_registry.get("skill_crawl_web")
        assert s is not None
        assert s.category == "crawl"

    def test_get_missing_returns_none(self, filled_registry):
        assert filled_registry.get("nope") is None

    def test_list_by_category(self, filled_registry):
        crawl_skills = filled_registry.list_by_category("crawl")
        assert len(crawl_skills) == 10
        assert all(s.category == "crawl" for s in crawl_skills)

    def test_list_categories(self, filled_registry):
        cats = filled_registry.list_categories()
        assert "crawl" in cats
        assert "agent" in cats
        assert "drama" in cats


class TestSearch:
    def test_search_finds_by_name(self, filled_registry):
        hits = filled_registry.search("Agent 对话")
        assert len(hits) >= 1
        assert any(s.id == "skill_agent_chat" for s in hits)

    def test_search_finds_by_description_keyword(self, filled_registry):
        hits = filled_registry.search("翻译")
        assert any(s.id == "skill_translate" for s in hits)

    def test_search_empty_returns_empty(self, filled_registry):
        assert filled_registry.search("") == []

    def test_search_no_match_returns_empty(self, filled_registry):
        assert filled_registry.search("zzzzzzz_no_match") == []


class TestTriggerMatch:
    def test_match_chinese_phrase(self, filled_registry):
        s = filled_registry.trigger_match("抓取网页")
        assert s is not None
        assert s.id == "skill_crawl_web"

    def test_match_english_phrase(self, filled_registry):
        s = filled_registry.trigger_match("crawl")
        assert s is not None
        assert s.id == "skill_crawl_web"

    def test_match_dedupe(self, filled_registry):
        s = filled_registry.trigger_match("去重")
        assert s is not None
        assert s.id == "skill_dedupe"

    def test_match_substring(self, filled_registry):
        # 用短语里的子串也能 match (loose)
        s = filled_registry.trigger_match("Dedup")
        assert s is not None

    def test_match_unknown_returns_none(self, filled_registry):
        assert filled_registry.trigger_match("nonexistent trigger xxx") is None


class TestSerialize:
    def test_to_json(self, filled_registry):
        j = filled_registry.to_json()
        d = json.loads(j)
        assert d["version"] == "v5.1"
        assert d["count"] == 50
        assert len(d["skills"]) == 50
        # 包含必要字段
        first = d["skills"][0]
        for k in ("id", "name", "category", "trigger_phrases", "version"):
            assert k in first, f"missing {k} in serialized"

    def test_to_json_is_ascii_safe(self, filled_registry):
        j = filled_registry.to_json()
        # 中文字符应保留(ensure_ascii=False)
        assert "抓取" in j or "网页" in j


class TestAlias:
    """验证 SkillRegistry == SkillRegistryV51 (任务要求的导入名)"""

    def test_alias_works(self):
        assert SkillRegistry is SkillRegistryV51
