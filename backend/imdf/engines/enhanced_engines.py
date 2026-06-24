"""增强能力引擎 — 数据去重/语音分析/视频分析 + 最优本地模型"""
import os, json, hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 1. 数据去重引擎 (3层去重: 精确→感知→语义)
# ============================================================

class DedupLevel(str, Enum):
    EXACT = "exact"        # MD5哈希
    PERCEPTUAL = "perceptual"  # pHash/SSIM
    SEMANTIC = "semantic"     # CLIP嵌入

@dataclass
class DedupResult:
    total: int
    exact_dups: int = 0
    perceptual_dups: int = 0
    semantic_dups: int = 0
    unique: int = 0
    groups: List[List[str]] = None  # 每组重复文件

class DedupEngine:
    """三层数据去重引擎"""
    
    def __init__(self):
        self.model_cache = {}
    
    def _md5_hash(self, filepath: str) -> str:
        """精确去重 — MD5"""
        h = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    
    def _phash(self, filepath: str) -> str:
        """感知去重 — pHash"""
        try:
            from PIL import Image
            import imagehash
            img = Image.open(filepath)
            return str(imagehash.phash(img))
        except Exception:
            return ""
    
    def _ssim_hash(self, filepath: str) -> tuple:
        """感知去重 — SSIM特征"""
        try:
            from PIL import Image
            import numpy as np
            img = Image.open(filepath).convert('L').resize((64, 64))
            arr = np.array(img)
            # 简化SSIM: 分块求均值作为特征
            features = []
            for i in range(0, 64, 8):
                for j in range(0, 64, 8):
                    features.append(float(np.mean(arr[i:i+8, j:j+8])))
            return tuple(round(f) for f in features)
        except Exception:
            return ()
    
    def _clip_embedding(self, filepath: str) -> List[float]:
        """语义去重 — CLIP嵌入(最优)"""
        try:
            from transformers import CLIPModel, CLIPProcessor
            from PIL import Image
            
            if "clip" not in self.model_cache:
                self.model_cache["clip"] = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                self.model_cache["clip_proc"] = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            
            img = Image.open(filepath).convert("RGB")
            inputs = self.model_cache["clip_proc"](images=img, return_tensors="pt")
            outputs = self.model_cache["clip"].get_image_features(**inputs)
            return outputs.detach().numpy()[0].tolist()
        except Exception:
            # Fallback: pHash
            return [float(h) for h in str(self._phash(filepath)).replace('0','').replace('f','1')][:512] or [0]*512
    
    def deduplicate(self, filepaths: List[str], level: DedupLevel = DedupLevel.PERCEPTUAL) -> DedupResult:
        """执行去重,返回去重结果"""
        result = DedupResult(total=len(filepaths), groups=[])
        
        # Level 1: MD5精确去重
        md5_map: Dict[str, List[str]] = {}
        for fp in filepaths:
            try:
                h = self._md5_hash(fp)
                md5_map.setdefault(h, []).append(fp)
            except Exception as e: logger.error(f"Operation failed: {e}")
        
        result.exact_dups = sum(len(g)-1 for g in md5_map.values() if len(g)>1)
        
        if level == DedupLevel.EXACT:
            result.unique = len(md5_map)
            return result
        
        # Level 2: 感知去重 (pHash)
        unique_files = [g[0] for g in md5_map.values()]
        phash_map: Dict[str, List[str]] = {}
        for fp in unique_files:
            ph = self._phash(fp)
            if ph:
                phash_map.setdefault(ph, []).append(fp)
        
        result.perceptual_dups = sum(len(g)-1 for g in phash_map.values() if len(g)>1)
        
        if level == DedupLevel.PERCEPTUAL:
            result.unique = len(phash_map)
            return result
        
        # Level 3: 语义去重 (CLIP)
        still_unique = [g[0] for g in phash_map.values()]
        embeddings = {}
        for fp in still_unique:
            try:
                emb = self._clip_embedding(fp)
                embeddings[fp] = emb
            except Exception as e: logger.error(f"Operation failed: {e}")
        
        # 余弦相似度聚类
        import math
        def cosine(a, b):
            dot = sum(ai*bi for ai,bi in zip(a,b))
            na = math.sqrt(sum(ai*ai for ai in a))
            nb = math.sqrt(sum(bi*bi for bi in b))
            return dot/(na*nb) if na*nb > 0 else 0
        
        SEMANTIC_THRESHOLD = 0.95
        semantic_groups = []
        processed = set()
        for fp, emb in embeddings.items():
            if fp in processed: continue
            group = [fp]
            for fp2, emb2 in embeddings.items():
                if fp2 in processed or fp2 == fp: continue
                if cosine(emb, emb2) > SEMANTIC_THRESHOLD:
                    group.append(fp2)
                    processed.add(fp2)
            processed.add(fp)
            semantic_groups.append(group)
        
        result.semantic_dups = sum(len(g)-1 for g in semantic_groups if len(g)>1)
        result.unique = len(semantic_groups)
        return result
    
    # ================================================================
    # 🔧 商用级清洗质量增强 (1. 清洗质量报告)
    # ================================================================
    def cleaning_quality_report(self, filepaths: List[str],
                                level: DedupLevel = DedupLevel.PERCEPTUAL) -> Dict:
        """生成清洗质量报告: 清洗率/误清洗率/各层效果"""
        before_count = len(filepaths)
        result = self.deduplicate(filepaths, level)
        after_count = result.unique
        
        # 清洗率
        cleaning_rate = (before_count - after_count) / before_count if before_count > 0 else 0
        
        # 各层去重贡献
        exact_removed = result.exact_dups
        perceptual_removed = result.perceptual_dups
        semantic_removed = result.semantic_dups
        total_removed = exact_removed + perceptual_removed + semantic_removed
        
        report = {
            "before_cleaning": before_count,
            "after_cleaning": after_count,
            "removed_count": total_removed,
            "cleaning_rate": round(cleaning_rate, 4),
            "cleaning_rate_pct": f"{round(cleaning_rate * 100, 1)}%",
            "layer_breakdown": {
                "exact_md5": {"removed": exact_removed, "pct": round(exact_removed / total_removed * 100, 1) if total_removed > 0 else 0},
                "perceptual_phash": {"removed": perceptual_removed, "pct": round(perceptual_removed / total_removed * 100, 1) if total_removed > 0 else 0},
                "semantic_clip": {"removed": semantic_removed, "pct": round(semantic_removed / total_removed * 100, 1) if total_removed > 0 else 0},
            },
            "industry_benchmark": {
                "expected_cleaning_rate": "5-15% (web-scale data)",
                "acceptable_range": "1-30% (depends on source diversity)",
                "status": "normal" if 0.01 <= cleaning_rate <= 0.30 else "anomaly"
            }
        }
        return report
    
    # ================================================================
    # 🔧 商用级清洗质量增强 (2. Golden data校验)
    # ================================================================
    def validate_with_golden(self, filepaths: List[str],
                             golden_pairs: List[Tuple[str, str, bool]]) -> Dict:
        """
        Golden data校验: 已知脏数据对→验证清洗效果
        golden_pairs: [(file_a, file_b, should_be_marked_duplicate), ...]
        """
        results = []
        true_positives = 0  # 应去重,实际去重
        false_positives = 0  # 不应去重,实际去重
        true_negatives = 0  # 不应去重,实际未去重
        false_negatives = 0  # 应去重,实际未去重
        
        for fp_a, fp_b, should_dedup in golden_pairs:
            # 检查是否被去重引擎识别为重复
            md5_a = self._md5_hash(fp_a)
            md5_b = self._md5_hash(fp_b)
            ph_a = self._phash(fp_a)
            ph_b = self._phash(fp_b)
            
            is_exact_dup = md5_a == md5_b
            is_perceptual_dup = ph_a == ph_b if (ph_a and ph_b) else False
            
            # 语义相似度
            try:
                emb_a = self._clip_embedding(fp_a)
                emb_b = self._clip_embedding(fp_b)
                import math
                dot = sum(ai*bi for ai,bi in zip(emb_a, emb_b))
                na = math.sqrt(sum(ai*ai for ai in emb_a))
                nb = math.sqrt(sum(bi*bi for bi in emb_b))
                sim = dot/(na*nb) if na*nb > 0 else 0
                is_semantic_dup = sim > 0.95
            except Exception:
                is_semantic_dup = False
            
            detected = is_exact_dup or is_perceptual_dup or is_semantic_dup
            
            if should_dedup and detected:
                true_positives += 1
                status = "tp"
            elif not should_dedup and detected:
                false_positives += 1
                status = "fp"
            elif not should_dedup and not detected:
                true_negatives += 1
                status = "tn"
            else:
                false_negatives += 1
                status = "fn"
            
            results.append({
                "pair": (fp_a, fp_b),
                "should_dedup": should_dedup,
                "detected": detected,
                "exact_dup": is_exact_dup,
                "perceptual_dup": is_perceptual_dup,
                "semantic_dup": is_semantic_dup,
                "status": status
            })
        
        total = len(golden_pairs)
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "golden_pairs_tested": total,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "true_negatives": true_negatives,
            "false_negatives": false_negatives,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "misclassification_rate": round((false_positives + false_negatives) / total, 4) if total > 0 else 0,
            "quality": "excellent" if f1 > 0.95 else "good" if f1 > 0.85 else "acceptable" if f1 > 0.75 else "needs_improvement",
            "details": results,
            "status": "complete"
        }
    
    # ================================================================
    # 🔧 商用级清洗质量增强 (3. 清洗前后对比审计)
    # ================================================================
    def cleaning_audit(self, before_files: List[str],
                       after_files: List[str],
                       sample_pairs: int = 5) -> Dict:
        """清洗前后对比审计: 抽样展示被移除的重复项"""
        before_set = set(before_files)
        after_set = set(after_files)
        removed_files = before_set - after_set
        
        # 找出被移除文件对应的保留文件(重复组的代表)
        sample_audit = []
        removed_list = list(removed_files)
        
        for removed in removed_list[:sample_pairs]:
            # 尝试找到与它重复的保留文件
            kept_counterpart = None
            reason = "unknown"
            
            try:
                rm_md5 = self._md5_hash(removed)
            except Exception:
                rm_md5 = None
            
            for kept in after_files:
                try:
                    kept_md5 = self._md5_hash(kept)
                    if rm_md5 and kept_md5 == rm_md5:
                        kept_counterpart = kept
                        reason = "exact_md5"
                        break
                except Exception as e:
                    logger.error(f"Operation failed: {e}")
            
            if not kept_counterpart:
                try:
                    rm_ph = self._phash(removed)
                except Exception:
                    rm_ph = None
                
                for kept in after_files:
                    try:
                        kept_ph = self._phash(kept)
                        if rm_ph and kept_ph and rm_ph == kept_ph:
                            kept_counterpart = kept
                            reason = "perceptual_phash"
                            break
                    except Exception as e:
                        logger.error(f"Operation failed: {e}")
            
            sample_audit.append({
                "removed_file": removed,
                "kept_counterpart": kept_counterpart,
                "dedup_reason": reason,
                "action": "removed_as_duplicate"
            })
        
        # 文件大小对比
        try:
            before_total_size = sum(os.path.getsize(f) for f in before_files if os.path.exists(f))
            after_total_size = sum(os.path.getsize(f) for f in after_files if os.path.exists(f))
        except Exception:
            before_total_size = 0
            after_total_size = 0
        
        return {
            "before_count": len(before_files),
            "after_count": len(after_files),
            "removed_count": len(removed_files),
            "retention_rate": round(len(after_files) / len(before_files), 4) if before_files else 0,
            "before_total_size_bytes": before_total_size,
            "after_total_size_bytes": after_total_size,
            "storage_saved_bytes": before_total_size - after_total_size,
            "storage_saved_pct": round((before_total_size - after_total_size) / before_total_size * 100, 1) if before_total_size > 0 else 0,
            "sample_audit": sample_audit,
            "timestamp": datetime.now().isoformat(),
            "status": "complete"
        }


# ============================================================
# 2. 语音分析引擎 (ASR/说话人识别/情感)
# ============================================================

class SpeechEngine:
    """语音分析 — ASR + 说话人识别 + 情感分析"""
    
    MODELS = {
        "asr": "openai/whisper-large-v3",  # 1.5GB, 最优ASR
        "asr_tiny": "openai/whisper-tiny",  # 39MB, 轻量
        "diarization": "pyannote/speaker-diarization-3.1",  # 说话人分离
        "emotion": "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition",  # 语音情感
    }
    
    def __init__(self):
        self._whisper = None
        self._emotion = None
    
    def transcribe(self, audio_path: str, language: str = "zh") -> Dict:
        """语音转文字 (Whisper large-v3)"""
        try:
            import whisper
            if not self._whisper:
                print("加载 Whisper large-v3 (1.5GB)...")
                self._whisper = whisper.load_model("large-v3")
            
            result = self._whisper.transcribe(audio_path, language=language)
            segments = [{"start": s["start"], "end": s["end"], "text": s["text"]} 
                       for s in result.get("segments", [])]
            return {
                "success": True,
                "text": result["text"],
                "language": result.get("language", language),
                "segments": segments,
                "duration": segments[-1]["end"] if segments else 0
            }
        except ImportError:
            return {"success": False, "error": "pip install openai-whisper"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}
    
    def speaker_diarization(self, audio_path: str) -> Dict:
        """说话人分离"""
        try:
            from pyannote.audio import Pipeline
            pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                                use_auth_token=os.environ.get("HF_TOKEN"))
            diarization = pipeline(audio_path)
            speakers = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speakers.append({"start": turn.start, "end": turn.end, "speaker": speaker})
            return {"success": True, "speakers": len(set(s["speaker"] for s in speakers)),
                    "segments": speakers}
        except ImportError:
            return {"success": False, "error": "pip install pyannote.audio"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}
    
    def emotion_analysis(self, audio_path: str) -> Dict:
        """语音情感分析"""
        try:
            import torch, librosa
            from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
            
            if not self._emotion:
                self._emotion = Wav2Vec2ForSequenceClassification.from_pretrained(
                    "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition")
                self._emotion_proc = Wav2Vec2Processor.from_pretrained(
                    "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition")
            
            audio, sr = librosa.load(audio_path, sr=16000)
            inputs = self._emotion_proc(audio, sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                logits = self._emotion(**inputs).logits
            scores = torch.softmax(logits, dim=-1)[0]
            emotions = ["angry", "calm", "disgust", "fearful", "happy", "neutral", "sad", "surprised"]
            return {
                "success": True,
                "emotions": {e: float(s) for e, s in zip(emotions, scores)}
            }
        except ImportError:
            return {"success": False, "error": "pip install transformers librosa torch"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}


# ============================================================
# 3. 视频分析引擎 (场景检测/关键帧/动作识别)
# ============================================================

class VideoEngine:
    """视频分析 — 场景检测 + 关键帧 + 内容理解"""
    
    MODELS = {
        "scene_detect": "PySceneDetect (算法,无需模型)",
        "action": "MCG-NJU/videomae-base-finetuned-kinetics",  # 400类动作
        "caption": "Salesforce/blip2-opt-2.7b",  # 视频描述
    }
    
    def scene_detection(self, video_path: str, threshold: float = 30.0) -> Dict:
        """场景切换检测"""
        try:
            import scenedetect
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector
            
            video = VideoManager([video_path])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            
            video.start()
            scene_manager.detect_scenes(frame_source=video)
            scenes = scene_manager.get_scene_list()
            
            return {
                "success": True,
                "scenes": len(scenes),
                "segments": [{"start": s[0].get_seconds(), "end": s[1].get_seconds()} 
                            for s in scenes[:50]]  # 最多50个
            }
        except ImportError:
            return {"success": False, "error": "pip install scenedetect[opencv]"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}
    
    def keyframe_extraction(self, video_path: str, max_frames: int = 10) -> Dict:
        """提取关键帧"""
        import subprocess, tempfile, os
        
        tmpdir = tempfile.mkdtemp()
        try:
            # 用ffmpeg提取I帧(关键帧)
            cmd = ["ffmpeg", "-i", video_path, "-vf", f"select=eq(pict_type\\,I)", 
                   "-vsync", "vfr", "-frames:v", str(max_frames),
                   f"{tmpdir}/keyframe_%03d.jpg", "-y"]
            subprocess.run(cmd, capture_output=True, timeout=30)
            
            frames = sorted([f for f in os.listdir(tmpdir) if f.endswith('.jpg')])
            return {
                "success": True,
                "keyframes": len(frames),
                "paths": [os.path.join(tmpdir, f) for f in frames]
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}
    
    def action_recognition(self, video_path: str) -> Dict:
        """动作识别 (VideoMAE)"""
        try:
            import torch
            from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor
            
            # VideoMAE需要抽样16帧
            import subprocess, tempfile, os
            tmpdir = tempfile.mkdtemp()
            subprocess.run(["ffmpeg", "-i", video_path, "-vf", "fps=1", 
                          "-frames:v", "16", f"{tmpdir}/frame_%02d.jpg", "-y"],
                         capture_output=True, timeout=20)
            
            from PIL import Image
            frames = [Image.open(os.path.join(tmpdir, f)) for f in 
                     sorted(os.listdir(tmpdir)) if f.endswith('.jpg')][:16]
            
            if len(frames) < 8:
                return {"success": True, "actions": [{"label": "视频过短", "score": 1.0}]}
            
            processor = VideoMAEImageProcessor.from_pretrained("MCG-NJU/videomae-base-finetuned-kinetics")
            model = VideoMAEForVideoClassification.from_pretrained("MCG-NJU/videomae-base-finetuned-kinetics")
            
            inputs = processor([frames], return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs)
            
            probs = torch.softmax(outputs.logits, dim=-1)[0]
            top5 = torch.topk(probs, 5)
            return {
                "success": True,
                "actions": [{"label": model.config.id2label[idx.item()], 
                            "score": float(score)} 
                           for idx, score in zip(top5.indices, top5.values)]
            }
        except ImportError:
            return {"success": False, "error": "pip install transformers torch"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}


# 单例
_dedup: DedupEngine = None
_speech: SpeechEngine = None
_video: VideoEngine = None

def get_dedup(): global _dedup; _dedup = _dedup or DedupEngine(); return _dedup
def get_speech(): global _speech; _speech = _speech or SpeechEngine(); return _speech
def get_video(): global _video; _video = _video or VideoEngine(); return _video
