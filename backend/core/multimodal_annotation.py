"""多模态标注系统"""
import cv2, json, logging, uuid, os, tempfile
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class AnnotationType(str, Enum):
    BBOX = "bbox"
    POLYGON = "polygon" 
    KEYPOINT = "keypoint"
    SEGMENTATION = "segmentation"
    TRANSCRIPT = "transcript"
    CLASSIFICATION = "classification"

class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"

class VideoAnnotation:
    """视频标注——帧提取+bbox跟踪"""
    
    @staticmethod
    def extract_frames(video_path: str, interval: int = 30) -> List[Dict]:
        """从视频中按间隔提取帧"""
        if not os.path.exists(video_path):
            return []
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        frames = []
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % interval == 0:
                # 保存帧为临时文件
                h, w = frame.shape[:2]
                frames.append({
                    "frame_index": frame_count,
                    "timestamp": frame_count / 30.0,  # 假设30fps
                    "width": w,
                    "height": h,
                    "data": frame  # numpy array
                })
            frame_count += 1
        cap.release()
        logger.info(f"Extracted {len(frames)} frames from {video_path} (interval={interval})")
        return frames
    
    @staticmethod
    def propagate_bbox(frames: List[Dict], start_frame: int, bbox: List[float]) -> List[Dict]:
        """简单的bbox帧间传播（基于位置不变假设）"""
        annotations = []
        for f in frames:
            if f["frame_index"] >= start_frame:
                annotations.append({
                    "frame_index": f["frame_index"],
                    "timestamp": f["timestamp"],
                    "bbox": bbox,
                    "type": "bbox",
                    "propagated": f["frame_index"] != start_frame
                })
        return annotations

class AudioAnnotation:
    """音频标注——波形可视化+文本转写"""
    
    @staticmethod
    def transcribe(audio_path: str) -> Dict:
        """音频转写（使用whisper或本地引擎）"""
        result = {
            "text": "",
            "segments": [],
            "duration": 0.0,
            "language": ""
        }
        if not os.path.exists(audio_path):
            return result
        
        # 尝试本地whisper
        try:
            import whisper
            model = whisper.load_model("base")
            transcription = model.transcribe(audio_path)
            result["text"] = transcription.get("text", "")
            result["segments"] = [
                {"start": s.get("start", 0), "end": s.get("end", 0), "text": s.get("text", "")}
                for s in transcription.get("segments", [])
            ]
            result["duration"] = transcription.get("duration", 0)
            result["language"] = transcription.get("language", "")
        except ImportError:
            logger.warning("whisper not installed, using fallback")
            # 获取音频时长作为fallback
            try:
                import soundfile as sf
                data, sr = sf.read(audio_path)
                result["duration"] = len(data) / sr
            except:
                result["duration"] = 0
        return result
    
    @staticmethod
    def get_waveform(audio_path: str, samples: int = 200) -> List[float]:
        """提取音频波形数据"""
        try:
            import soundfile as sf
            data, sr = sf.read(audio_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)  # mono
            # 降采样到samples个点
            step = max(1, len(data) // samples)
            waveform = [float(abs(data[i])) for i in range(0, len(data), step)][:samples]
            return waveform
        except:
            return []

class MultimodalAnnotationManager:
    """多模态标注管理器——统一所有媒体类型的标注"""
    
    def __init__(self):
        self._annotations: Dict[str, List[Dict]] = {}
    
    def create_annotation(self, media_id: str, media_type: MediaType, 
                         annotation_type: AnnotationType, data: Dict) -> str:
        ann_id = f"ann_{uuid.uuid4().hex[:12]}"
        ann = {
            "id": ann_id,
            "media_id": media_id,
            "media_type": media_type.value,
            "annotation_type": annotation_type.value,
            "data": data,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        if media_id not in self._annotations:
            self._annotations[media_id] = []
        self._annotations[media_id].append(ann)
        return ann_id
    
    def get_annotations(self, media_id: str) -> List[Dict]:
        return self._annotations.get(media_id, [])
    
    def update_annotation(self, ann_id: str, data: Dict) -> bool:
        for media_id, anns in self._annotations.items():
            for ann in anns:
                if ann["id"] == ann_id:
                    ann["data"] = data
                    ann["updated_at"] = datetime.now().isoformat()
                    return True
        return False
    
    def delete_annotation(self, ann_id: str) -> bool:
        for media_id in list(self._annotations.keys()):
            self._annotations[media_id] = [a for a in self._annotations[media_id] if a["id"] != ann_id]
            if not self._annotations[media_id]:
                del self._annotations[media_id]
            return True
        return False

_annotation_manager = None
def get_annotation_manager():
    global _annotation_manager
    if _annotation_manager is None:
        _annotation_manager = MultimodalAnnotationManager()
    return _annotation_manager
