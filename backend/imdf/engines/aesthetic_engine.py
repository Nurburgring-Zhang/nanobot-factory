"""
审美评分引擎 v3.1 — 三大顶级模型Ensemble + Elo 排行榜

修复内容(R1-Worker-1, 2026-06-18):
  1. 新增 `get_aesthetic_engine()` 单例工厂(向后兼容命名, 对应路由 `from engines.aesthetic_engine import get_aesthetic_engine`)
  2. 新增 `async score_image()` 接受 `use_llm / llm_models` 关键字参数
  3. ML 模型调用包 try/except — 单模型失败不影响其他模型和 Pillow fallback
  4. 始终返回结构化 dict: success / overall_score / dimensions / models_used / model_scores / confidence / error
  5. 新增 Elo 系统 + 批量评分方法, 修复 8 个端点的 500 错误
"""
import os
import json
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

import numpy as np
from PIL import Image, ImageStat, ImageFilter


# ─── Helper structures ──────────────────────────────────────────────────────

@dataclass
class EloEntry:
    """单张图片的 Elo 记录"""
    image_id: str
    image_name: str = ""
    rating: float = 1500.0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    games: int = 0
    registered_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EloComparison:
    """一次 Elo 对比结果"""
    image_a_id: str
    image_b_id: str
    image_a_new: float
    image_b_new: float
    elo_delta: float
    expected_a: float
    expected_b: float
    winner: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Engine ─────────────────────────────────────────────────────────────────

class EnsembleAestheticEngine:
    """三模型 ensemble 审美评分 + Elo 排行榜"""

    # 三个 SOTA 模型的权重(基于 Benchmark SRCC)
    MODEL_WEIGHTS = {
        "q_align": 0.45,           # SRCC 0.885
        "laion_aesthetic": 0.30,   # SRCC ~0.82
        "musiq": 0.25,             # SRCC ~0.78
    }

    DIMENSIONS = ["composition", "color", "lighting", "sharpness", "content", "creativity"]

    # Elo 配置
    ELO_K_FACTOR = 32.0
    ELO_DEFAULT_RATING = 1500.0

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._loaded = False
        # ─── Elo 状态(线程安全) ───────────────────────────────────────────
        self._elo_entries: Dict[str, EloEntry] = {}
        self._elo_history: List[Dict[str, Any]] = []
        self._elo_lock = threading.RLock()

    # ─── ML model lazy loaders(每个失败都返回 None, 不影响其他模型) ─────

    def _load_q_align(self):
        """Q-Align — 最强通用审美模型(南洋理工)"""
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
            model = AutoModel.from_pretrained("Q-Future/Q-Align", trust_remote_code=True)
            processor = AutoProcessor.from_pretrained("Q-Future/Q-Align", trust_remote_code=True)
            return {"model": model, "processor": processor}
        except Exception as e:
            # Quiet — expected when torch/transformers/Q-Align not available
            return None

    def _load_laion_aesthetic(self):
        """LAION Aesthetic Predictor V2.5 — 改进版 CLIP 审美"""
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor
            model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
            processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
            state = torch.hub.load_state_dict_from_url(
                "https://github.com/christophschuhmann/improved-aesthetic-predictor/raw/main/sac%2Blogos%2Bava1-l14-linearMSE.pth"
            )
            return {"model": model, "processor": processor, "head": state}
        except Exception:
            return None

    def _load_musiq(self):
        """MUSIQ — Google 多尺度图像质量评估"""
        try:
            import torch
            from pyiqa import create_metric
            model = create_metric("musiq", device="cpu")
            return {"model": model}
        except Exception:
            return None

    # ─── Per-model scoring(每个独立 try/except) ──────────────────────────

    def _score_q_align(self, image: Image.Image) -> Optional[Dict[str, Any]]:
        try:
            if "q_align" not in self._models:
                self._models["q_align"] = self._load_q_align()
            info = self._models["q_align"]
            if not info:
                return None

            import torch
            model, processor = info["model"], info["processor"]
            levels = ["excellent", "good", "fair", "poor", "bad"]
            level_scores = {"excellent": 10, "good": 8, "fair": 6, "poor": 4, "bad": 2}

            inputs = processor(images=image, text=levels, return_tensors="pt", padding=True)
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits_per_image[0]
                probs = torch.softmax(logits, dim=0)
                score = sum(level_scores[levels[i]] * float(probs[i]) for i in range(5))
            return {"overall": round(score, 1), "model": "Q-Align"}
        except Exception:
            return None

    def _score_laion(self, image: Image.Image) -> Optional[Dict[str, Any]]:
        try:
            if "laion" not in self._models:
                self._models["laion"] = self._load_laion_aesthetic()
            info = self._models["laion"]
            if not info:
                return None

            import torch
            model, processor, head = info["model"], info["processor"], info["head"]
            inputs = processor(images=image, return_tensors="pt")
            with torch.no_grad():
                features = model.get_image_features(**inputs)
                score = float(torch.sigmoid(
                    torch.matmul(features, head["weight"].t()) + head["bias"]
                )[0][0]) * 10

            prompts = {
                "composition": "A photo with excellent composition, rule of thirds, balanced framing",
                "color": "A photo with vibrant harmonious colors, excellent color grading",
                "lighting": "A photo with perfect lighting, well-exposed, beautiful highlights and shadows",
                "sharpness": "A photo with excellent sharpness, clear details, no blur",
                "content": "A photo with interesting meaningful content, compelling subject",
                "creativity": "A photo with creative unique artistic style, innovative composition",
            }
            dims = {}
            for dim, prompt in prompts.items():
                inputs2 = processor(text=[prompt], return_tensors="pt")
                with torch.no_grad():
                    text_feat = model.get_text_features(**inputs2)
                    sim = torch.cosine_similarity(features, text_feat, dim=-1)[0]
                dims[dim] = round(float(sim) * 10, 1)
            return {"overall": round(score, 1), "dimensions": dims, "model": "LAION-Aesthetic-V2.5"}
        except Exception:
            return None

    def _score_musiq(self, image: Image.Image) -> Optional[Dict[str, Any]]:
        try:
            if "musiq" not in self._models:
                self._models["musiq"] = self._load_musiq()
            info = self._models["musiq"]
            if not info:
                return None

            import torch
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            try:
                image.save(tmp.name)
                score = info["model"](tmp.name).item()
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
            return {"overall": round(min(max(score, 0), 10), 1), "model": "MUSIQ"}
        except Exception:
            return None

    # ─── Pillow 6 维度 baseline(始终可用) ───────────────────────────────

    def _pillow_6dim(self, img: Image.Image) -> Dict[str, float]:
        arr = np.array(img)
        lap = np.array(img.filter(ImageFilter.LAPLACIAN))

        composition = min(10, float(np.var(lap)) * 0.02 + 5)
        hsv = img.convert("HSV")
        stat = ImageStat.Stat(hsv)
        color = round(min(10, float(stat.mean[1]) * 0.08), 1)

        gray = img.convert("L")
        stat_l = ImageStat.Stat(gray)
        lighting = round(10 - abs(float(stat_l.mean[0]) - 128) / 25.6, 1)
        sharpness = round(min(10, float(np.var(lap)) * 0.03), 1)

        edges = np.array(img.filter(ImageFilter.FIND_EDGES))
        content = round(min(10, float(np.mean(edges)) * 0.1), 1)

        colors = len(set(tuple(p) for p in arr[::8, ::8].reshape(-1, 3)))
        creativity = round(min(10, float(colors) / 50), 1)

        return {d: round(float(v), 1) for d, v in zip(
            self.DIMENSIONS,
            [composition, color, lighting, sharpness, content, creativity],
        )}

    # ─── Public scoring API ──────────────────────────────────────────────

    def _score_image_sync(
        self,
        image_path: str,
        use_llm: bool = False,
        llm_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        同步底层评分(供 async score_image / score_batch 复用)

        Returns 始终是结构化 dict, 见模块 docstring
        """
        result: Dict[str, Any] = {
            "success": False,
            "overall_score": 0.0,
            "dimensions": {},
            "models_used": [],
            "model_scores": {},
            "confidence": "low",
            "error": None,
        }

        # 1) 读取图像(失败就 early return)
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as e:
            result["error"] = f"Failed to open image: {e}"
            return result

        scores: Dict[str, float] = {}
        dimensions: Dict[str, List[float]] = {}

        # 2) Q-Align(失败不影响其他)
        if use_llm or not llm_models or "q_align" in (llm_models or []):
            q = self._score_q_align(image)
            if q:
                scores["q_align"] = float(q["overall"])

        # 3) LAION
        if use_llm or not llm_models or "laion" in (llm_models or []) or "laion_aesthetic" in (llm_models or []):
            la = self._score_laion(image)
            if la:
                scores["laion"] = float(la["overall"])
                if "dimensions" in la:
                    for d in self.DIMENSIONS:
                        dimensions.setdefault(d, []).append(la["dimensions"].get(d, 0))

        # 4) MUSIQ
        if use_llm or not llm_models or "musiq" in (llm_models or []):
            mu = self._score_musiq(image)
            if mu:
                scores["musiq"] = float(mu["overall"])

        # 5) Pillow baseline(始终)
        try:
            pillow_scores = self._pillow_6dim(image)
            for d in self.DIMENSIONS:
                dimensions.setdefault(d, []).append(pillow_scores.get(d, 0))
        except Exception as e:
            result["error"] = f"Pillow baseline failed: {e}"
            # 仍继续 — 至少返回 models_used

        # 6) 加权聚合
        if scores:
            total_weight = sum(self.MODEL_WEIGHTS.get(m, 1.0 / len(scores)) for m in scores)
            overall = sum(
                scores[m] * self.MODEL_WEIGHTS.get(m, 1.0 / len(scores)) / total_weight
                for m in scores
            )
        else:
            # 全部 ML 模型挂了 — 退到纯 Pillow
            try:
                if not pillow_scores:
                    pillow_scores = self._pillow_6dim(image)
                overall = sum(pillow_scores.values()) / max(len(pillow_scores), 1)
                scores["pillow_fallback"] = round(float(overall), 1)
            except Exception as e:
                result["error"] = (result["error"] or "") + f"; fallback failed: {e}"
                return result

        dim_avg = {d: round(float(np.mean(v)), 1) for d, v in dimensions.items() if v}

        n_models = len([m for m in scores if m != "pillow_fallback"])
        confidence = "high" if n_models >= 2 else "medium" if n_models == 1 else "low"

        result.update({
            "success": True,
            "overall_score": round(float(overall), 1),
            "dimensions": dim_avg,
            "models_used": list(scores.keys()),
            "model_scores": {m: round(float(s), 1) for m, s in scores.items()},
            "confidence": confidence,
        })
        return result

    async def score_image(
        self,
        image_path: str,
        use_llm: bool = False,
        llm_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        异步评分入口 — 路由层使用。

        始终返回结构化 dict(从不抛异常, 失败信息写入 `error` 字段)。
        """
        try:
            return self._score_image_sync(image_path, use_llm=use_llm, llm_models=llm_models)
        except Exception as e:
            return {
                "success": False,
                "overall_score": 0.0,
                "dimensions": {},
                "models_used": [],
                "model_scores": {},
                "confidence": "low",
                "error": str(e),
            }

    async def score_batch(
        self,
        image_paths: List[str],
        use_llm: bool = False,
    ) -> List[Dict[str, Any]]:
        """批量评分 — 单图失败不影响其他"""
        results: List[Dict[str, Any]] = []
        for p in image_paths:
            try:
                results.append(await self.score_image(p, use_llm=use_llm))
            except Exception as e:
                results.append({
                    "success": False,
                    "overall_score": 0.0,
                    "dimensions": {},
                    "models_used": [],
                    "model_scores": {},
                    "confidence": "low",
                    "error": str(e),
                })
        return results

    async def score_directory(
        self,
        directory: str,
        extensions: tuple = ('.jpg', '.jpeg', '.png', '.webp', '.bmp'),
        use_llm: bool = False,
    ) -> List[Dict[str, Any]]:
        """目录扫描 + 评分"""
        if not directory or not os.path.isdir(directory):
            return []
        paths: List[str] = []
        try:
            for name in os.listdir(directory):
                if name.lower().endswith(extensions):
                    paths.append(os.path.join(directory, name))
        except Exception:
            return []
        return await self.score_batch(paths, use_llm=use_llm)

    def batch_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """聚合批量结果统计"""
        total = len(results)
        scored = sum(1 for r in results if r.get("success"))
        failed = total - scored
        scores = [r.get("overall_score", 0.0) for r in results if r.get("success")]
        avg = round(float(np.mean(scores)), 2) if scores else 0.0
        return {
            "total": total,
            "scored": scored,
            "failed": failed,
            "average_score": avg,
        }

    # ─── Elo 公开 API(线程安全) ─────────────────────────────────────────

    def elo_register(
        self,
        image_id: str,
        image_name: str = "",
        initial_rating: float = ELO_DEFAULT_RATING,
    ) -> EloEntry:
        """注册新图片到 Elo 排行榜(若已存在则返回现有)"""
        import time
        with self._elo_lock:
            entry = self._elo_entries.get(image_id)
            if entry is None:
                entry = EloEntry(
                    image_id=image_id,
                    image_name=image_name or image_id,
                    rating=float(initial_rating),
                    registered_at=time.time(),
                )
                self._elo_entries[image_id] = entry
            return entry

    def elo_get_entry(self, image_id: str) -> Optional[EloEntry]:
        with self._elo_lock:
            return self._elo_entries.get(image_id)

    def elo_compare(
        self,
        image_a_id: str,
        image_b_id: str,
        winner: str,
        image_a_name: str = "",
        image_b_name: str = "",
    ) -> Optional[EloComparison]:
        """
        Elo 成对比较 — winner ∈ {"a", "b", "draw"}

        Returns None 当参数非法,否则返回 EloComparison
        """
        if winner not in ("a", "b", "draw"):
            return None
        if not image_a_id or not image_b_id or image_a_id == image_b_id:
            return None

        with self._elo_lock:
            entry_a = self.elo_register(image_a_id, image_a_name or image_a_id)
            entry_b = self.elo_register(image_b_id, image_b_name or image_b_id)

            expected_a = 1.0 / (1.0 + 10 ** ((entry_b.rating - entry_a.rating) / 400.0))
            expected_b = 1.0 - expected_a

            if winner == "a":
                score_a, score_b = 1.0, 0.0
            elif winner == "b":
                score_a, score_b = 0.0, 1.0
            else:  # draw
                score_a = score_b = 0.5

            delta_a = self.ELO_K_FACTOR * (score_a - expected_a)
            delta_b = self.ELO_K_FACTOR * (score_b - expected_b)

            entry_a.rating = round(entry_a.rating + delta_a, 2)
            entry_b.rating = round(entry_b.rating + delta_b, 2)
            entry_a.games += 1
            entry_b.games += 1
            if winner == "a":
                entry_a.wins += 1
                entry_b.losses += 1
            elif winner == "b":
                entry_b.wins += 1
                entry_a.losses += 1
            else:
                entry_a.draws += 1
                entry_b.draws += 1

            self._elo_history.append({
                "image_a_id": image_a_id,
                "image_b_id": image_b_id,
                "winner": winner,
                "image_a_new": entry_a.rating,
                "image_b_new": entry_b.rating,
            })

            return EloComparison(
                image_a_id=image_a_id,
                image_b_id=image_b_id,
                image_a_new=entry_a.rating,
                image_b_new=entry_b.rating,
                elo_delta=round(delta_a, 2),
                expected_a=round(expected_a, 4),
                expected_b=round(expected_b, 4),
                winner=winner,
            )

    def elo_ranking(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self._elo_lock:
            sorted_entries = sorted(
                self._elo_entries.values(),
                key=lambda e: e.rating,
                reverse=True,
            )
            sliced = sorted_entries[offset: offset + limit]
            return [
                {**e.to_dict(), "rank": offset + idx + 1}
                for idx, e in enumerate(sliced)
            ]

    def elo_stats(self) -> Dict[str, Any]:
        with self._elo_lock:
            entries = list(self._elo_entries.values())
            total = len(entries)
            if total == 0:
                return {
                    "total_entries": 0,
                    "total_comparisons": 0,
                    "average_rating": 0.0,
                    "highest_rating": 0.0,
                    "lowest_rating": 0.0,
                    "total_games": 0,
                }
            ratings = [e.rating for e in entries]
            return {
                "total_entries": total,
                "total_comparisons": len(self._elo_history),
                "average_rating": round(float(np.mean(ratings)), 2),
                "highest_rating": round(float(max(ratings)), 2),
                "lowest_rating": round(float(min(ratings)), 2),
                "total_games": sum(e.games for e in entries),
            }


# ─── Singleton factory ──────────────────────────────────────────────────────

_ensemble_engine: Optional[EnsembleAestheticEngine] = None
_factory_lock = threading.Lock()


def get_ensemble_aesthetic() -> EnsembleAestheticEngine:
    """原工厂名 — 保持向后兼容"""
    global _ensemble_engine
    if _ensemble_engine is None:
        with _factory_lock:
            if _ensemble_engine is None:
                _ensemble_engine = EnsembleAestheticEngine()
    return _ensemble_engine


def get_aesthetic_engine() -> EnsembleAestheticEngine:
    """
    新工厂名 — 路由层 `from engines.aesthetic_engine import get_aesthetic_engine` 使用

    内部委托给 `get_ensemble_aesthetic`,确保全进程单例
    """
    return get_ensemble_aesthetic()


def reset_aesthetic_engine() -> None:
    """测试用 — 重置单例, 主要给单元测试和 hot-reload"""
    global _ensemble_engine
    with _factory_lock:
        _ensemble_engine = None
