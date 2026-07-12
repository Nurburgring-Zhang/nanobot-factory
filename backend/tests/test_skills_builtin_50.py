"""
P19 v5.1-B — test_skills_builtin_50

验证 backend/skills_builtin.py 中的 50 个内置 Skill 全部:
1. 数量 = 50
2. ID 全局唯一
3. 全部分在合法 category 内(11 类之一)
4. 每个 skill 至少有 1 个 trigger_phrase + 1 个 input/output
5. trigger_match "抓取网页" -> skill_crawl_web (回归)
"""

import pytest

from backend.skills_builtin import BUILTIN_SKILLS, categories_builtin
from backend.skills_manager import SkillRegistryV51


EXPECTED_CATEGORIES = {
    "agency", "agent", "comfy", "crawl", "drama",
    "meta_kim", "octo", "process", "reach", "redfox", "vida",
}


class TestBuiltinCount:
    def test_total_is_50(self):
        assert len(BUILTIN_SKILLS) == 50, (
            f"expected 50 builtin skills, got {len(BUILTIN_SKILLS)}"
        )

    def test_categories_count(self):
        cnt = categories_builtin()
        assert len(cnt) == 11, f"expected 11 categories, got {len(cnt)}: {cnt}"
        # 各类别下计数
        assert cnt["crawl"] == 10
        assert cnt["process"] == 5
        assert cnt["agent"] == 8
        assert cnt["octo"] == 4
        assert cnt["vida"] == 2
        assert cnt["meta_kim"] == 3
        assert cnt["drama"] == 5
        assert cnt["comfy"] == 3
        assert cnt["redfox"] == 3
        assert cnt["reach"] == 4
        assert cnt["agency"] == 3
        # 总和 = 50
        assert sum(cnt.values()) == 50


class TestBuiltinUniqueness:
    def test_unique_ids(self):
        ids = [s.id for s in BUILTIN_SKILLS]
        dups = [x for x in ids if ids.count(x) > 1]
        assert not dups, f"duplicate skill ids: {set(dups)}"

    def test_unique_categories(self):
        # category 在 allowed set 内
        for s in BUILTIN_SKILLS:
            assert s.category in EXPECTED_CATEGORIES, (
                f"unknown category {s.category} for {s.id}"
            )


class TestBuiltinShape:
    def test_each_has_required_fields(self):
        for s in BUILTIN_SKILLS:
            assert s.id, f"empty id in {s}"
            assert s.name, f"empty name in {s.id}"
            assert s.version, f"empty version in {s.id}"

    def test_trigger_phrases_not_empty(self):
        empty = [s.id for s in BUILTIN_SKILLS if not s.trigger_phrases]
        assert not empty, f"skills without trigger_phrases: {empty}"

    def test_inputs_outputs_not_empty(self):
        empty_inputs = [s.id for s in BUILTIN_SKILLS if not s.inputs]
        empty_outputs = [s.id for s in BUILTIN_SKILLS if not s.outputs]
        assert not empty_inputs, f"skills without inputs: {empty_inputs}"
        assert not empty_outputs, f"skills without outputs: {empty_outputs}"


class TestBuiltinRegistration:
    """50 个 builtin 全部能 register 到 SkillRegistryV51"""

    def test_register_all(self):
        reg = SkillRegistryV51()
        n = reg.register_all(BUILTIN_SKILLS)
        assert n == 50, f"register_all returned {n}, expected 50"
        assert len(reg) == 50
        assert set(reg.list_categories()) == EXPECTED_CATEGORIES

    def test_specific_id_present(self):
        reg = SkillRegistryV51()
        reg.register_all(BUILTIN_SKILLS)
        for sid in (
            "skill_crawl_web",
            "skill_dedupe",
            "skill_agent_chat",
            "skill_octo_bot_create",
            "skill_vida_screen",
            "skill_meta_intent",
            "skill_drama_script",
            "skill_comfy_run",
            "skill_redfox_search",
            "skill_reach_web",
            "skill_agency_expert",
        ):
            assert sid in reg, f"missing {sid} in registry"

    def test_trigger_match_cn(self):
        """中英 trigger phrase 都能 match"""
        reg = SkillRegistryV51.from_builtin(BUILTIN_SKILLS)
        assert reg.trigger_match("抓取网页").id == "skill_crawl_web"
        assert reg.trigger_match("dedupe").id == "skill_dedupe"
        assert reg.trigger_match("crawl").id == "skill_crawl_web"

    def test_search_by_query(self):
        reg = SkillRegistryV51.from_builtin(BUILTIN_SKILLS)
        hits = reg.search("agent")
        assert len(hits) > 0
        assert all(h.category in EXPECTED_CATEGORIES for h in hits)
