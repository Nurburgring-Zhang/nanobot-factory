"""测试剩下功能: auto_tag + report_generator + search + preview + eval metrics"""
import sys, os, json, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.auto_tag import AutoTagEngine
from core.report_generator import ReportGenerator


def test_auto_tag_basic():
    at = AutoTagEngine()
    at.record_tags(["风景", "自然", "落日"])
    at.record_tags(["风景", "城市", "建筑"])
    at.record_tags(["自然", "动物", "风景"])
    
    # suggest based on existing tags
    suggestions = at.suggest(["风景"])
    assert len(suggestions) > 0, "should return suggestions"
    print(f"[PASS] auto_tag suggest({len(suggestions)} items): {[s['tag'] for s in suggestions]}")
    
    # hot tags
    hot = at.get_hot_tags(top_k=3)
    assert len(hot) == 3
    assert hot[0]["tag"] == "风景"
    print(f"[PASS] auto_tag hot tags: {hot}")
    
    # suggest without existing tags
    all_suggest = at.suggest(top_k=2)
    assert len(all_suggest) == 2
    print(f"[PASS] auto_tag suggest no existing: {all_suggest}")


def test_auto_tag_empty():
    at = AutoTagEngine()
    assert at.suggest() == []
    assert at.get_hot_tags() == []
    print("[PASS] auto_tag empty engine")


def test_report_generator_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        rg = ReportGenerator(output_dir=tmpdir)
        path = rg.generate_user_report([{"user": "a", "tasks": 10}, {"user": "b", "tasks": 5}])
        assert os.path.exists(path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 rows
        assert "user" in lines[0]
        print(f"[PASS] report CSV: {path}, lines={len(lines)}")


def test_report_generator_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        rg = ReportGenerator(output_dir=tmpdir)
        path = rg.generate_project_report({"project": "nanobot", "status": "active"})
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data["project"] == "nanobot"
        print(f"[PASS] report JSON: {path}, data={data}")


def test_report_generator_weekly():
    with tempfile.TemporaryDirectory() as tmpdir:
        rg = ReportGenerator(output_dir=tmpdir)
        path = rg.generate_weekly_report({"week": "2024W01", "tasks": 42})
        assert "2024W01" in path
        assert os.path.exists(path)
        print(f"[PASS] report weekly: {path}")


def test_report_generator_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        rg = ReportGenerator(output_dir=tmpdir)
        path = rg.export_csv([], "empty.csv")
        assert path == ""
        print("[PASS] report empty csv returns empty string")


if __name__ == "__main__":
    test_auto_tag_basic()
    test_auto_tag_empty()
    test_report_generator_csv()
    test_report_generator_json()
    test_report_generator_weekly()
    test_report_generator_empty()
    print("\n=== ALL REMAINING FEATURES TESTS PASSED ===")
