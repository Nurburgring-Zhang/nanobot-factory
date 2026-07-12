"""label_glm4v — GLM-4V multimodal annotation.

Zhipu AI's GLM-4V model — image captioning + classification + structured
output. Falls back to a deterministic mock.

Inputs:
    image:    str
    task:     str  — "caption"|"classify"|"extract"
    prompt:   str
    options:  list[str]  — required when task == "classify"
    lang:     str  — "en"|"zh"

Outputs:
    task:        str
    result:      str | list | dict  — task-specific payload
    confidence:  float
"""

import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    now_iso,
    post_json,
    require_non_empty,
    stable_seed,
)


_VALID_TASKS = {"caption", "classify", "extract"}


class Glm4VInput(BaseModel):
    image: str = Field(...)
    task: str = Field(default="caption")
    prompt: str = Field(default="请描述这张图片。", min_length=1)
    options: List[str] = Field(default_factory=list)
    lang: str = Field(default="zh")
    model: str = Field(default="glm-4v-plus")

    @field_validator("task")
    @classmethod
    def _task_ok(cls, v: str) -> str:
        v = (v or "caption").lower().strip()
        if v not in _VALID_TASKS:
            raise ValueError(f"task must be one of {sorted(_VALID_TASKS)}")
        return v


async def label_glm4v(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = Glm4VInput.model_validate(input.params or {})
        require_non_empty(payload.prompt, "prompt")
        if payload.task == "classify" and len(payload.options) < 2:
            raise ValueError("classify task needs >=2 options")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://open.bigmodel.cn/api/paas/v4/image/understand",
            {
                "model": payload.model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": payload.image}},
                    {"type": "text", "text": payload.prompt},
                ]}],
            },
            timeout=8.0,
        )

    if live and isinstance(live, dict):
        try:
            text = str(live["choices"][0]["message"]["content"]).strip()
            result_payload = _shape_result(text, payload.task, payload.options, payload.lang)
            return build_output(
                success=True,
                result={"task": payload.task, "result": result_payload, "lang": payload.lang,
                        "model": payload.model, "timestamp": now_iso()},
                source="live", confidence=0.88,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        except (KeyError, TypeError, IndexError):
            pass

    # Offline mock.
    seed = stable_seed(payload.image, payload.task, payload.prompt, payload.lang)
    mock_text = _mock_text(payload.task, payload.options, payload.lang, seed)
    result_payload = _shape_result(mock_text, payload.task, payload.options, payload.lang)
    return build_output(
        success=True,
        result={"task": payload.task, "result": result_payload, "lang": payload.lang,
                "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _shape_result(text: str, task: str, options: List[str], lang: str) -> Any:
    if task == "classify" and options:
        for opt in options:
            if opt and opt in text:
                return opt
        return options[0]
    if task == "extract":
        return {"text": text, "language": lang}
    return text  # caption


def _mock_text(task: str, options: List[str], lang: str, seed: int) -> str:
    if task == "classify" and options:
        return options[seed % len(options)]
    if lang == "zh":
        return "图中包含主要内容,细节丰富,整体构图清晰。"
    return "The image contains a clear main subject with rich detail."


__all__ = ["label_glm4v", "Glm4VInput"]