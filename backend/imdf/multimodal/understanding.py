"""P4-7-W2: CrossModalUnderstanding — Gemini Omni style unified understanding.

Supports 8 tasks over arbitrary combinations of (image / video / audio /
document / text):

* ``caption``        — image/video/audio → natural language description
* ``vqa``            — image + question → answer
* ``classification`` — image/audio/video → class label + score
* ``relation``       — multi-media → entity relation graph (text)
* ``sentiment``      — text/image/audio → sentiment label + score
* ``ocr``            — image/document → extracted text
* ``asr``            — audio/video → transcript
* ``reasoning``      — multi-modal reasoning → answer

The engine falls back to deterministic heuristics when no LLM is configured
(during tests).  An optional ``llm_call(prompt: str) -> str`` callable can be
passed in to use any registered model (Claude 3.5 / Gemini 1.5 Pro / GPT-4V
etc.).  The bundled ``anthropic`` / ``google-generativeai`` / ``openai``
clients are imported lazily and only used when their env keys are set.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from .parsers import ParsedMedia, parse_media
from .types import (
    MediaRef,
    ModalKind,
    UnderstandingRequest,
    UnderstandingResponse,
    UnderstandingTask,
)

logger = logging.getLogger(__name__)


# ── LLM adapter (lazy import; safe fallback) ───────────────────────────────
class _LLMAdapter:
    """Tiny adapter that calls Claude / Gemini / GPT-4V when keys exist."""

    def __init__(self) -> None:
        self._impl: Optional[Callable[[str, List[MediaRef]], str]] = None
        self.model = "stub"
        # allow tests to force stub even if API keys are present in the env
        if os.environ.get("MULTIMODAL_LLM_DISABLED") == "1":
            return
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:  # pragma: no cover - optional
                import anthropic  # type: ignore
                client = anthropic.Anthropic()
                self.model = "claude-3-5-sonnet"

                def _call(prompt: str, media: List[MediaRef]) -> str:
                    content: List[Dict[str, Any]] = []
                    for m in media:
                        if m.kind == ModalKind.IMAGE and m.data_b64:
                            content.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": m.mime or "image/png", "data": m.data_b64},
                            })
                        elif m.kind == ModalKind.TEXT and m.text:
                            content.append({"type": "text", "text": m.text})
                    content.append({"type": "text", "text": prompt})
                    resp = client.messages.create(
                        model=self.model, max_tokens=1024, messages=[{"role": "user", "content": content}]
                    )
                    return resp.content[0].text  # type: ignore[index]
                self._impl = _call
            except Exception as exc:
                logger.debug("anthropic init failed: %s", exc)
        if self._impl is None and os.environ.get("GOOGLE_API_KEY"):
            try:  # pragma: no cover - optional
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
                model = genai.GenerativeModel("gemini-1.5-pro")
                self.model = "gemini-1.5-pro"

                def _call(prompt: str, media: List[MediaRef]) -> str:
                    parts: List[Any] = []
                    for m in media:
                        if m.kind == ModalKind.IMAGE and m.data_b64:
                            import base64
                            parts.append({"inline_data": {"mime_type": m.mime or "image/png", "data": m.data_b64}})
                        elif m.kind == ModalKind.TEXT and m.text:
                            parts.append(m.text)
                    parts.append(prompt)
                    resp = model.generate_content(parts)
                    return resp.text or ""
                self._impl = _call
            except Exception as exc:
                logger.debug("gemini init failed: %s", exc)
        if self._impl is None and os.environ.get("OPENAI_API_KEY"):
            try:  # pragma: no cover - optional
                import openai  # type: ignore
                client = openai.OpenAI()
                self.model = "gpt-4o"

                def _call(prompt: str, media: List[MediaRef]) -> str:
                    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
                    for m in media:
                        if m.kind == ModalKind.IMAGE and m.data_b64:
                            content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{m.mime or 'image/png'};base64,{m.data_b64}"},
                            })
                        elif m.kind == ModalKind.TEXT and m.text:
                            content.append({"type": "text", "text": m.text})
                    resp = client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": content}],
                        max_tokens=1024,
                    )
                    return resp.choices[0].message.content or ""
                self._impl = _call
            except Exception as exc:
                logger.debug("openai init failed: %s", exc)

    def call(self, prompt: str, media: List[MediaRef]) -> str:
        if self._impl is None:
            raise RuntimeError("no LLM backend configured")
        return self._impl(prompt, media)


# ── deterministic heuristic fallbacks (used in tests / no-LLM mode) ───────
def _stub_caption(parsed_list: List[ParsedMedia], query: Optional[str]) -> str:
    if not parsed_list:
        return "No media provided."
    parts = []
    for p in parsed_list:
        if p.kind == ModalKind.TEXT:
            parts.append(p.text[:200])
        else:
            meta = p.meta or {}
            if p.kind == ModalKind.IMAGE:
                w, h = meta.get("width"), meta.get("height")
                parts.append(f"Image ({w}x{h}) — visual content described.")
            elif p.kind == ModalKind.VIDEO:
                parts.append(f"Video ({p.duration_sec}s, {p.frames} frames) — moving content.")
            elif p.kind == ModalKind.AUDIO:
                parts.append(f"Audio ({p.duration_sec}s) — sonic content.")
            else:
                parts.append(p.text[:200] or "Document content.")
    base = " ".join(parts)
    if query:
        return f"{base} | Focused on: {query[:120]}"
    return base


def _stub_vqa(parsed_list: List[ParsedMedia], query: Optional[str]) -> str:
    if not query:
        raise ValueError("vqa task requires a query")
    base = _stub_caption(parsed_list, None)
    return f"Answer (based on context): {base[:200]} | Question: {query}"


_LABELS = ["positive", "neutral", "negative"]
def _stub_classification(parsed_list: List[ParsedMedia]) -> Dict[str, Any]:
    label = "image" if parsed_list and parsed_list[0].kind == ModalKind.IMAGE else "other"
    score = 0.7 + (sum(len(p.text) for p in parsed_list) % 30) / 100.0
    return {"label": label, "score": round(min(score, 0.99), 4)}


def _stub_sentiment(parsed_list: List[ParsedMedia]) -> Dict[str, Any]:
    seed = sum(len(p.text) for p in parsed_list)
    label = _LABELS[seed % 3]
    return {"label": label, "score": round(0.55 + (seed % 40) / 100.0, 4)}


def _stub_relation(parsed_list: List[ParsedMedia]) -> str:
    if not parsed_list:
        return ""
    ids = [p.content_hash[:8] for p in parsed_list]
    edges = [(ids[i], ids[i + 1], "co-occurs") for i in range(len(ids) - 1)]
    return "; ".join(f"{a} --[{rel}]--> {b}" for a, b, rel in edges)


# ── main engine ────────────────────────────────────────────────────────────
class CrossModalUnderstanding:
    """Unified cross-modal understanding across 8 tasks."""

    def __init__(self, llm_call: Optional[Callable[[str, List[MediaRef]], str]] = None) -> None:
        self._llm = llm_call
        self._adapter = _LLMAdapter()
        self._model = self._adapter.model if self._llm is None else "custom"

    @property
    def model(self) -> str:
        return self._model

    # ── core entry ──────────────────────────────────────────────────────
    def understand(self, req: UnderstandingRequest) -> UnderstandingResponse:
        t0 = time.time()
        parsed_list = [parse_media(m) for m in req.media if m.kind != ModalKind.TEXT]
        text_media = [m.text or "" for m in req.media if m.kind == ModalKind.TEXT and m.text]
        # citations are always the parsed text from each input
        citations = [
            {"short_id": m.short_id(), "kind": m.kind.value, "url": m.url, "parsed": p.text[:200]}
            for m, p in zip(req.media, parsed_list)
        ] + ([{"kind": "text", "text": t} for t in text_media])

        # dispatch by task
        task = req.task
        text = ""
        label: Optional[str] = None
        score: Optional[float] = None
        llm_used = False
        if task in (UnderstandingTask.CAPTION, UnderstandingTask.VQA, UnderstandingTask.REASONING):
            try:
                text = self._call_llm_or_stub(req, parsed_list, text_media)
                llm_used = True
            except Exception:
                if task == UnderstandingTask.CAPTION:
                    text = _stub_caption(parsed_list, req.query)
                elif task == UnderstandingTask.VQA:
                    text = _stub_vqa(parsed_list, req.query)
                else:  # reasoning
                    text = _stub_vqa(parsed_list, req.query)
        elif task == UnderstandingTask.CLASSIFICATION:
            try:
                cls_prompt = (
                    "Classify the following cross-modal inputs into a single short label "
                    "(1-3 words) and provide a confidence score in [0, 1] as JSON "
                    '{"label": "...", "score": 0.x}. Inputs: '
                    + "; ".join(p.text[:120] for p in parsed_list)
                )
                out = self._call_llm(cls_prompt, req.media)
                llm_used = True
                # crude parse
                import json
                try:
                    j = json.loads(out)
                    label, score = j.get("label"), float(j.get("score", 0.0))
                except Exception:
                    label, score = out.strip().split("\n")[0][:40], 0.5
            except Exception:
                cls = _stub_classification(parsed_list)
                label, score = cls["label"], cls["score"]
        elif task == UnderstandingTask.SENTIMENT:
            try:
                prompt = (
                    "Analyze the sentiment of these cross-modal inputs. "
                    "Reply JSON {\"label\": \"positive|neutral|negative\", \"score\": 0.x}. "
                    + "; ".join(p.text[:120] for p in parsed_list)
                )
                out = self._call_llm(prompt, req.media)
                llm_used = True
                import json
                j = json.loads(out)
                label, score = j.get("label"), float(j.get("score", 0.0))
            except Exception:
                ss = _stub_sentiment(parsed_list)
                label, score = ss["label"], ss["score"]
        elif task == UnderstandingTask.OCR:
            text = "\n".join(p.text for p in parsed_list)  # stub: caption text contains "image OCR"
        elif task == UnderstandingTask.ASR:
            text = "\n".join(p.text for p in parsed_list)
        elif task == UnderstandingTask.RELATION:
            text = _stub_relation(parsed_list)

        elapsed = round((time.time() - t0) * 1000, 2)
        return UnderstandingResponse(
            request_id=req.request_id,
            task=task,
            text=text,
            label=label,
            score=score,
            citations=citations,
            raw={"llm_used": llm_used, "stub": not llm_used, "media_count": len(req.media)},
            elapsed_ms=elapsed,
            model=self.model,
        )

    def understand_batch(self, requests: List[UnderstandingRequest]) -> List[UnderstandingResponse]:
        return [self.understand(r) for r in requests]

    # ── helpers ─────────────────────────────────────────────────────────
    def _call_llm(self, prompt: str, media: List[MediaRef]) -> str:
        if self._llm is not None:
            return self._llm(prompt, media)
        return self._adapter.call(prompt, media)

    def _call_llm_or_stub(self, req: UnderstandingRequest, parsed: List[ParsedMedia], text_media: List[str]) -> str:
        if req.task == UnderstandingTask.CAPTION:
            prompt = "Provide a concise caption for the following cross-modal inputs."
        elif req.task == UnderstandingTask.VQA:
            prompt = f"Answer this question using the cross-modal context.\nQuestion: {req.query}"
        else:  # reasoning
            prompt = (
                "Perform step-by-step cross-modal reasoning to answer the following query.\n"
                f"Query: {req.query}"
            )
        if text_media:
            prompt += "\nText inputs:\n" + "\n".join(text_media)
        if parsed:
            prompt += "\nParsed context:\n" + "\n".join(p.text[:200] for p in parsed)
        return self._call_llm(prompt, req.media)