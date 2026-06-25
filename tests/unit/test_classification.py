"""分类规则引擎单元测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'../..'))
from engines.classification_engine import ClassificationEngine as Classifier

class TestClassification:
    def setup_method(self):
        self.clf = Classifier()
    
    def test_basic_classify(self):
        items = [{"name":"portrait","resolution":"2048","tags":"人物 室外"}]
        results = self.clf.classify(items, rule_set="default")
        assert len(results) > 0
    
    def test_empty_input(self):
        results = self.clf.classify([], rule_set="default")
        assert results == []
    
    def test_nl_filter(self):
        items = [{"name":"a","tags":"人物"},{"name":"b","tags":"场景"},{"name":"c"}]
        result = self.clf.nl_filter(items, "人物")
        assert len(result) == 1
        assert result[0]["name"] == "a"
    
    def test_rules_exist(self):
        rules = self.clf.list_rules()
        assert len(rules) >= 6
