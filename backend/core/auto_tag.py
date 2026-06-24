"""自动标签建议 — 基于频率分析和内容推荐"""
from collections import Counter
from typing import List, Dict

class AutoTagEngine:
    def __init__(self):
        self._tag_frequency: Dict[str, int] = Counter()
        self._tag_cooccurrence: Dict[str, Counter] = {}
    
    def record_tags(self, tags: List[str]):
        for t in tags:
            self._tag_frequency[t] += 1
        for i, t1 in enumerate(tags):
            for t2 in tags[i+1:]:
                self._tag_cooccurrence.setdefault(t1, Counter())[t2] += 1
                self._tag_cooccurrence.setdefault(t2, Counter())[t1] += 1
    
    def suggest(self, existing_tags: List[str] = None, top_k: int = 5) -> List[Dict]:
        candidates = Counter()
        if existing_tags:
            for t in existing_tags:
                for co_tag, count in self._tag_cooccurrence.get(t, Counter()).items():
                    if co_tag not in existing_tags:
                        candidates[co_tag] += count
        else:
            for t, count in self._tag_frequency.most_common(20):
                candidates[t] = count
        return [{"tag": t, "score": s} for t, s in candidates.most_common(top_k)]
    
    def get_hot_tags(self, top_k: int = 20) -> List[Dict]:
        return [{"tag": t, "count": c} for t, c in self._tag_frequency.most_common(top_k)]
