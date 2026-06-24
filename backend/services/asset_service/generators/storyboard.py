"""P4-5-W1: Storyboard Generator — LLM-decomposed 5-20 shot breakdown.

Pipeline (借鉴 OpenMontage + Gemini Omni):
  1. Take a story script (free-form Chinese / English) + character list +
     visual style preset.
  2. Decompose into ``5-20`` shots. Each shot has:
     * ``shot_id`` (sequential)
     * ``scene`` (location)
     * ``description`` (what happens visually)
     * ``characters`` (List[str]) — which characters are in the shot
     * ``dialogue`` (optional — character lines)
     * ``camera`` (shot type: close-up / medium / wide / aerial / tracking)
     * ``duration_seconds`` (recommended, default 4s)
     * ``transition`` (cut / fade / dissolve / wipe)
     * ``reference_assets`` (auto-linked: character reference URLs + style)
     * ``background_music`` (auto-recommended: e.g. "calm lo-fi")
  3. Optionally render each shot into an actual image / video via
     ``/render`` — kicks off image + video generators per shot.

Implementation:
  * **Mock** — deterministic shot decomposition based on script length
    (one shot per ~150 chars, clamped to [5, 20]).
  * **Real (LLM-driven)** — call the chat adapter via
    ``call_provider_smart`` with kind="chat", parse the structured JSON
    response. Falls back to mock on failure.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..characters.storage import get_character

logger = logging.getLogger(__name__)


# Shot type whitelist (controlled vocabulary for LLM / mock consistency)
ALLOWED_SHOT_TYPES = frozenset({
    "close-up", "medium", "wide", "extreme-wide", "aerial",
    "over-shoulder", "tracking", "dolly", "handheld", "static",
})

ALLOWED_TRANSITIONS = frozenset({
    "cut", "fade", "dissolve", "wipe", "iris", "smash-cut", "match-cut",
})

# Style presets (visual styles for shot color/lighting)
ALLOWED_STYLE_PRESETS = frozenset({
    "cinematic", "anime", "watercolor", "noir", "sci-fi", "fantasy",
    "documentary", "comic", "storybook", "cyberpunk", "period-drama",
})

DEFAULT_SHOT_DURATION = 4
MIN_SHOT_DURATION, MAX_SHOT_DURATION = 1, 30

MIN_SHOTS, MAX_SHOTS = 5, 20


# ═══════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StoryboardShot:
    shot_id: int
    scene: str
    description: str
    characters: List[str] = field(default_factory=list)
    dialogue: Optional[str] = None
    camera: str = "medium"
    duration_seconds: int = DEFAULT_SHOT_DURATION
    transition: str = "cut"
    reference_assets: List[str] = field(default_factory=list)
    background_music: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoryboardGenerateRequest:
    script: str
    character_ids: List[str] = field(default_factory=list)
    style: str = "cinematic"
    target_shot_count: int = 10  # hint, clamped to [MIN_SHOTS, MAX_SHOTS]
    model: Optional[str] = None  # LLM model for decomposition (None → mock)
    provider_id: Optional[str] = None
    mock: bool = True
    user_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "StoryboardGenerateRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        script = str(payload.get("script") or "").strip()
        if not script:
            raise ValueError("script is required")
        if len(script) > 30000:
            raise ValueError("script must be <= 30000 chars")
        style = str(payload.get("style") or "cinematic").strip().lower()
        if style not in ALLOWED_STYLE_PRESETS:
            raise ValueError(f"unsupported style: {style!r}; allowed={sorted(ALLOWED_STYLE_PRESETS)}")
        target = int(payload.get("target_shot_count") or 10)
        target = max(MIN_SHOTS, min(MAX_SHOTS, target))
        return cls(
            script=script,
            character_ids=[str(c)[:64] for c in (payload.get("character_ids") or []) if c][:16],
            style=style,
            target_shot_count=target,
            model=payload.get("model"),
            provider_id=payload.get("provider_id"),
            mock=bool(payload.get("mock", True)),
            user_id=payload.get("user_id"),
        )


@dataclass
class StoryboardGenerateResponse:
    storyboard_id: str
    shots: List[StoryboardShot]
    style: str
    character_ids: List[str]
    mock: bool
    elapsed_ms: int
    cost_usd: float
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoryboardRenderRequest:
    storyboard_id: str
    render_image: bool = True
    render_video: bool = False
    skip_shot_ids: List[int] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "StoryboardRenderRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        storyboard_id = str(payload.get("storyboard_id") or "").strip()
        if not storyboard_id:
            raise ValueError("storyboard_id is required")
        return cls(
            storyboard_id=storyboard_id,
            render_image=bool(payload.get("render_image", True)),
            render_video=bool(payload.get("render_video", False)),
            skip_shot_ids=[int(x) for x in (payload.get("skip_shot_ids") or []) if str(x).isdigit()][:20],
        )


@dataclass
class StoryboardRenderResponse:
    storyboard_id: str
    rendered_shots: int
    image_urls: List[str] = field(default_factory=list)
    video_urls: List[str] = field(default_factory=list)
    cost_usd: float = 0.0
    elapsed_ms: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# Mock decomposition (deterministic, no external deps)
# ═══════════════════════════════════════════════════════════════════════════════

_PARAGRAPH_RE = re.compile(r"[。\.!?！？\n]+")


def _split_into_sentences(script: str) -> List[str]:
    """Split script on CJK + ASCII sentence boundaries."""
    parts = _PARAGRAPH_RE.split(script)
    return [p.strip() for p in parts if p and p.strip()]


def _scene_guess(sentence: str) -> str:
    """Naive scene extraction — first noun-phrase after location keywords."""
    s = sentence.lower()
    location_map = {
        "城市": "城市街景", "city": "城市街景", "街道": "街道",
        "森林": "森林深处", "forest": "森林深处",
        "海边": "海滩", "beach": "海滩",
        "山": "山脉", "mountain": "山脉",
        "室内": "室内场景", "room": "室内场景", "办公室": "办公室",
        "太空": "太空", "space": "太空", "宇宙": "宇宙",
        "沙漠": "沙漠", "desert": "沙漠",
        "雪": "雪原", "snow": "雪原",
        "夜": "夜景", "night": "夜景",
        "酒吧": "酒吧", "bar": "酒吧",
        "教室": "教室", "classroom": "教室",
    }
    for k, v in location_map.items():
        if k in s:
            return v
    return "未指定场景"


def _camera_pick(idx: int, n: int) -> str:
    """Cycle through shot types for visual variety."""
    cycle = ["medium", "wide", "close-up", "over-shoulder", "tracking", "extreme-wide"]
    return cycle[idx % len(cycle)]


def _transition_pick(idx: int, n: int) -> str:
    if idx == 0:
        return "fade"
    if idx == n - 1:
        return "fade"
    return "cut"


_BGM_BY_STYLE = {
    "cinematic": "epic orchestral",
    "anime": "uplifting J-pop",
    "watercolor": "calm piano",
    "noir": "dark jazz",
    "sci-fi": "synthwave",
    "fantasy": "mystical orchestral",
    "documentary": "neutral ambient",
    "comic": "playful lo-fi",
    "storybook": "gentle acoustic",
    "cyberpunk": "industrial electronic",
    "period-drama": "guzheng traditional",
}


def _mock_decompose(req: StoryboardGenerateRequest) -> List[StoryboardShot]:
    """Deterministic mock decomposition — no external services."""
    sentences = _split_into_sentences(req.script)
    if not sentences:
        sentences = [req.script[:200] or "(空脚本)"]

    # Derive shot count: target ~ proportional to script length but bounded
    target = req.target_shot_count
    if len(sentences) < target:
        # split long sentences to reach target
        expanded: List[str] = []
        per = max(1, len(sentences) // max(1, target))
        for s in sentences:
            if len(s) > 200:
                # split on comma
                chunks = [c.strip() for c in re.split(r"[，,；;]", s) if c.strip()]
                expanded.extend(chunks)
            else:
                expanded.append(s)
        sentences = expanded
    if not sentences:
        sentences = [req.script[:200] or "(空)"]

    # Pick target shots evenly across the sentence list
    n = max(MIN_SHOTS, min(MAX_SHOTS, target))
    if len(sentences) >= n:
        idx_step = len(sentences) / n
        chosen = [sentences[int(i * idx_step)] for i in range(n)]
    else:
        chosen = sentences + ["(续) " + s for s in sentences[: n - len(sentences)]]
        chosen = chosen[:n]

    # Resolve character reference URLs
    char_refs: Dict[str, List[str]] = {}
    for cid in req.character_ids:
        c = get_character(cid)
        if c is not None:
            char_refs[cid] = [r.url for r in (c.reference_images or [])][:3]

    bgm = _BGM_BY_STYLE.get(req.style, "neutral ambient")

    shots: List[StoryboardShot] = []
    for i, sent in enumerate(chosen):
        scene = _scene_guess(sent)
        cam = _camera_pick(i, n)
        tr = _transition_pick(i, n)
        # Dialogue heuristic: extract dialogue between matched quote pairs.
        # Support CJK quote pairs (「」, 『』) and ASCII ("" / '').
        dialogue = None
        for opener, closer in (("「", "」"), ("『", "』"), ('"', '"'), ("'", "'")):
            try:
                m = re.search(
                    re.escape(opener) + r"(.+?)" + re.escape(closer),
                    sent,
                )
                if m:
                    dialogue = m.group(1).strip()
                    break
            except Exception:
                continue
        if m:
            dialogue = m.group(1).strip()

        # Auto-link character refs (round-robin)
        refs: List[str] = []
        for cid in req.character_ids:
            for url in char_refs.get(cid, []):
                if url and url not in refs:
                    refs.append(url)

        shots.append(StoryboardShot(
            shot_id=i + 1,
            scene=scene,
            description=sent[:280],
            characters=list(req.character_ids),
            dialogue=dialogue,
            camera=cam,
            duration_seconds=DEFAULT_SHOT_DURATION,
            transition=tr,
            reference_assets=refs[:6],
            background_music=bgm,
        ))

    return shots


# ═══════════════════════════════════════════════════════════════════════════════
# LLM decomposition (best-effort — falls back to mock on any failure)
# ═══════════════════════════════════════════════════════════════════════════════

_STORYBOARD_PROMPT_TEMPLATE = """你是专业分镜师. 将下面的故事脚本拆解为恰好 {n} 个分镜.

输出要求: 严格 JSON 数组, 每个元素包含字段:
  shot_id (int), scene (str), description (str),
  characters (List[str]), dialogue (str|null), camera (str),
  duration_seconds (int 1-30), transition (str),
  reference_assets (List[str]), background_music (str|null)

约束:
- shot_id 从 1 开始顺序
- camera 必须是: {shot_types}
- transition 必须是: {transitions}
- visual style: {style}
- background_music: 给出最匹配的情绪标签

脚本:
\"\"\"
{script}
\"\"\"

只输出 JSON 数组, 不要 markdown 代码块, 不要其他文字.
"""


async def _llm_decompose(req: StoryboardGenerateRequest, *, fallback: List[StoryboardShot]) -> tuple[List[StoryboardShot], float, List[str]]:
    """Try the LLM route; on any failure, return the fallback (mock) shots.

    Returns ``(shots, cost_usd, warnings)``.
    """
    warnings: List[str] = []
    if req.mock or req.model is None:
        return fallback, 0.0, []

    try:
        from imdf.engines.provider_registry import call_provider_smart, _get_provider_config
    except Exception as e:
        warnings.append(f"provider_import_failed: {e!s}")
        return fallback, 0.0, warnings

    prompt = _STORYBOARD_PROMPT_TEMPLATE.format(
        n=req.target_shot_count,
        shot_types=", ".join(sorted(ALLOWED_SHOT_TYPES)),
        transitions=", ".join(sorted(ALLOWED_TRANSITIONS)),
        style=req.style,
        script=req.script[:8000],
    )

    try:
        provider_id = req.provider_id or "openai-compatible"
        provider_cfg = _get_provider_config(provider_id) if callable(_get_provider_config) else {
            "id": provider_id, "protocol": "openai-compatible",
            "apiKey": "", "chatModels": [req.model or "gpt-4o"],
        }
        payload = {
            "model": req.model or "gpt-4o",
            "messages": [
                {"role": "system", "content": "你是专业分镜师, 输出严格 JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }
        result = await call_provider_smart(
            provider_cfg, payload, kind="chat",
            user_id=req.user_id or "anonymous",
        )
        if not result.get("ok"):
            warnings.append(f"provider_failed: {result.get('code')}")
            return fallback, float(result.get("cost_usd") or 0.0), warnings

        content = (result.get("data") or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
        cost = float(result.get("cost_usd") or 0.0)
        if not content:
            return fallback, cost, warnings + ["empty_response"]

        # Parse — try direct, then strip markdown fences
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"```\s*$", "", text)
        try:
            arr = json.loads(text)
        except Exception as e:
            warnings.append(f"json_parse_failed: {e!s}")
            return fallback, cost, warnings
        if not isinstance(arr, list):
            return fallback, cost, warnings + ["not_a_list"]

        # Validate & coerce
        shots: List[StoryboardShot] = []
        for i, item in enumerate(arr[:MAX_SHOTS]):
            if not isinstance(item, dict):
                continue
            try:
                cam = str(item.get("camera") or "medium").strip().lower()
                if cam not in ALLOWED_SHOT_TYPES:
                    cam = "medium"
                tr = str(item.get("transition") or "cut").strip().lower()
                if tr not in ALLOWED_TRANSITIONS:
                    tr = "cut"
                dur = int(item.get("duration_seconds") or DEFAULT_SHOT_DURATION)
                dur = max(MIN_SHOT_DURATION, min(MAX_SHOT_DURATION, dur))
                shots.append(StoryboardShot(
                    shot_id=int(item.get("shot_id") or (i + 1)),
                    scene=str(item.get("scene") or "未指定")[:200],
                    description=str(item.get("description") or "")[:2000],
                    characters=[str(c) for c in (item.get("characters") or [])][:8],
                    dialogue=(str(item.get("dialogue"))[:2000] if item.get("dialogue") else None),
                    camera=cam,
                    duration_seconds=dur,
                    transition=tr,
                    reference_assets=[str(x)[:2048] for x in (item.get("reference_assets") or [])][:6],
                    background_music=(str(item.get("background_music"))[:200] if item.get("background_music") else None),
                ))
            except Exception:
                continue
        if len(shots) < MIN_SHOTS:
            warnings.append(f"too_few_shots: got {len(shots)}; using mock fallback")
            return fallback, cost, warnings
        return shots, cost, warnings
    except Exception as e:
        warnings.append(f"llm_decompose_failed: {e!s}")
        return fallback, 0.0, warnings


# ═══════════════════════════════════════════════════════════════════════════════
# Storyboard cache (process-local)
# ═══════════════════════════════════════════════════════════════════════════════

_STORYBOARD_CACHE: Dict[str, StoryboardGenerateResponse] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════════

class StoryboardGenerator:

    def __init__(self, *, default_mock: bool = True) -> None:
        self.default_mock = default_mock

    def generate(self, req: StoryboardGenerateRequest) -> StoryboardGenerateResponse:
        start = time.time()
        fallback = _mock_decompose(req)
        shots: List[StoryboardShot] = fallback
        cost = 0.0
        warnings: List[str] = []

        if not req.mock:
            try:
                import asyncio
                shots, cost, warnings = asyncio.run(
                    _llm_decompose(req, fallback=fallback)
                )
            except Exception as e:
                warnings.append(f"async_decompose_failed: {e!s}")

        # Clamp final shot count
        shots = shots[:MAX_SHOTS]
        if len(shots) < MIN_SHOTS:
            # pad with mock-derived fallbacks to reach MIN_SHOTS
            extra = fallback[: max(0, MIN_SHOTS - len(shots))]
            shots = shots + extra
            warnings.append("padded_to_min_shots")

        sb_id = f"sb_{uuid.uuid4().hex[:12]}"
        resp = StoryboardGenerateResponse(
            storyboard_id=sb_id,
            shots=shots,
            style=req.style,
            character_ids=list(req.character_ids),
            mock=bool(req.mock or self.default_mock),
            elapsed_ms=int((time.time() - start) * 1000),
            cost_usd=cost,
            warnings=warnings,
        )
        _STORYBOARD_CACHE[sb_id] = resp
        return resp

    def render(self, req: StoryboardRenderRequest) -> StoryboardRenderResponse:
        """Render each shot via image / video generators. Cache by storyboard_id."""
        start = time.time()
        sb = _STORYBOARD_CACHE.get(req.storyboard_id)
        if sb is None:
            raise ValueError(f"storyboard_id not found: {req.storyboard_id}")

        image_urls: List[str] = []
        video_urls: List[str] = []
        cost = 0.0
        warnings: List[str] = []

        skip = set(req.skip_shot_ids or [])
        for shot in sb.shots:
            if shot.shot_id in skip:
                continue
            if req.render_image:
                try:
                    from .image import ImageGenerator, ImageGenerateRequest
                    img = ImageGenerator(default_mock=True).generate(ImageGenerateRequest(
                        prompt=shot.description,
                        reference_images=list(shot.reference_assets),
                        style_preset=sb.style,
                        character_id=(sb.character_ids[0] if sb.character_ids else None),
                        model="dall-e-3",
                        mock=True,
                        n=1,
                    ))
                    image_urls.extend([i.url for i in img.images])
                    cost += img.cost_usd
                except Exception as e:
                    warnings.append(f"shot_{shot.shot_id}_image_failed: {e!s}")
                    image_urls.append(f"https://via.placeholder.com/1024x1024.png?text=shot{shot.shot_id}")
            if req.render_video:
                try:
                    from .video import VideoGenerator, VideoGenerateRequest
                    vid = VideoGenerator(default_mock=True).generate(VideoGenerateRequest(
                        prompt=shot.description,
                        reference_images=list(shot.reference_assets),
                        duration=min(10, shot.duration_seconds),
                        model="kling-2",
                        mock=True,
                    ))
                    video_urls.append(vid.video.url)
                    cost += vid.cost_usd
                except Exception as e:
                    warnings.append(f"shot_{shot.shot_id}_video_failed: {e!s}")

        elapsed = int((time.time() - start) * 1000)
        return StoryboardRenderResponse(
            storyboard_id=req.storyboard_id,
            rendered_shots=len(sb.shots) - len(skip),
            image_urls=image_urls,
            video_urls=video_urls,
            cost_usd=cost,
            elapsed_ms=elapsed,
            warnings=warnings,
        )

    @staticmethod
    def get_cached(storyboard_id: str) -> Optional[StoryboardGenerateResponse]:
        return _STORYBOARD_CACHE.get(storyboard_id)


__all__ = [
    "ALLOWED_SHOT_TYPES",
    "ALLOWED_TRANSITIONS",
    "ALLOWED_STYLE_PRESETS",
    "StoryboardShot",
    "StoryboardGenerateRequest",
    "StoryboardGenerateResponse",
    "StoryboardRenderRequest",
    "StoryboardRenderResponse",
    "StoryboardGenerator",
    "MIN_SHOTS",
    "MAX_SHOTS",
]
