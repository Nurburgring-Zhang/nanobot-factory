"""IAA一致性单元测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'../..'))
from engines.annotation_quality import IAAEngine

class TestIAA:
    def test_cohen_kappa_perfect(self):
        r1 = ["cat","dog","cat","dog","cat"]
        r2 = ["cat","dog","cat","dog","cat"]
        k = IAAEngine.cohen_kappa(r1, r2)
        assert k > 0.99
    
    def test_cohen_kappa_random(self):
        r1 = ["cat","dog","cat","dog","cat"]
        r2 = ["dog","cat","dog","cat","dog"]
        k = IAAEngine.cohen_kappa(r1, r2)
        assert k < 0
    
    def test_fleiss_kappa(self):
        ratings = [[0,0,0],[0,1,0],[0,0,0],[0,1,0],[0,0,0]]
        k = IAAEngine.fleiss_kappa(ratings, 2)
        assert -1 <= k <= 1
    
    def test_iou(self):
        a = [1.0, 0.5, 0.0]
        b = [1.0, 0.5, 0.0]
        m = IAAEngine.iou_matrix([a, b])
        assert m[0][1] == 1.0
