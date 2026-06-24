"""
P0-5: Annotation Agreement Engine
==================================
Scoring inter-annotator agreement using Cohen's Kappa, Fleiss' Kappa, and IoU.
Uses sklearn.metrics.cohen_kappa_score as the core metric.
"""

from typing import List, Dict, Any, Tuple, Union
from sklearn.metrics import cohen_kappa_score


class AgreementEngine:
    """标注一致性评分引擎"""

    @staticmethod
    def kappa(annotations: List[Tuple[List[int], List[int]]]) -> float:
        """计算两个标注者之间的Cohen's Kappa

        Args:
            annotations: [(rater1_labels, rater2_labels), ...] 每个元素是两个标注者的标注列表
                        如果传入多个样本对, 返回加权平均

        Returns:
            Cohen's Kappa 系数 (-1 ~ 1)
        """
        if not annotations:
            return 0.0
        scores = []
        for r1, r2 in annotations:
            if len(set(r1)) == 1 and len(set(r2)) == 1 and r1[0] == r2[0]:
                # All same — cohen_kappa_score raises ZeroDivision
                scores.append(1.0)
            elif len(set(r1)) == 1 and len(set(r2)) == 1:
                scores.append(-1.0)
            else:
                scores.append(cohen_kappa_score(r1, r2))
        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def iou(box1: Tuple[float, float, float, float],
            box2: Tuple[float, float, float, float]) -> float:
        """计算两个边界框的IoU (Intersection over Union)

        Args:
            box1: (x1, y1, x2, y2) 左上+右下坐标
            box2: (x1, y1, x2, y2)

        Returns:
            IoU值 (0 ~ 1)
        """
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0.0

    @staticmethod
    def fleiss_kappa(ratings: List[List[int]]) -> float:
        """计算Fleiss' Kappa (3个及以上标注者)

        Args:
            ratings: [[r1_cat1, r1_cat2, ...], [r2_cat1, ...], ...]
                     每行是一个标注者对 N 个项目的分类结果
                     每列是一个项目, 值=标注者给出的类别

        Returns:
            Fleiss' Kappa 系数 (-1 ~ 1)
        """
        n_subjects = len(ratings[0]) if ratings else 0
        n_raters = len(ratings)
        if n_subjects < 2 or n_raters < 3:
            return 0.0

        # Find all categories
        all_cats = set()
        for row in ratings:
            all_cats.update(row)
        k = len(all_cats)
        if k <= 1:
            return 1.0

        cat_list = sorted(all_cats)
        cat_index = {c: i for i, c in enumerate(cat_list)}

        # Build n_ij matrix: subjects x categories
        n_ij = [[0] * k for _ in range(n_subjects)]
        for rater_row in ratings:
            for subj_idx, cat in enumerate(rater_row):
                n_ij[subj_idx][cat_index[cat]] += 1

        N = n_subjects
        n = n_raters

        # P_i for each subject
        P_i = []
        for subject in n_ij:
            s = sum(subject)
            if s == 0:
                P_i.append(0.0)
            else:
                total_pairs = s * (s - 1)
                if total_pairs == 0:
                    P_i.append(0.0)
                else:
                    agree = sum(v * (v - 1) for v in subject)
                    P_i.append(agree / total_pairs)

        P_bar = sum(P_i) / N if N else 0.0

        # P_j for each category
        P_j = []
        for j in range(k):
            total = sum(n_ij[i][j] for i in range(N))
            P_j.append(total / (N * n))

        P_e = sum(pj ** 2 for pj in P_j)

        if abs(P_e - 1.0) < 1e-9:
            return 1.0
        if abs(P_bar - P_e) < 1e-9:
            return 0.0

        return (P_bar - P_e) / (1 - P_e)

    @staticmethod
    def overall_score(scores: List[float], weights: List[float] = None) -> float:
        """计算加权平均总体评分

        Args:
            scores: 各维度得分列表
            weights: 各维度权重 (默认均匀)

        Returns:
            加权平均值
        """
        if not scores:
            return 0.0
        if weights is None:
            weights = [1.0 / len(scores)] * len(scores)
        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)
