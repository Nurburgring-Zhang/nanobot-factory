"""P4-7-W2: MultimodalAgent — tool-using multimodal agent (Gemini Omni style).

The agent receives an arbitrary combination of (text + image + video + audio +
document) and decides which tool(s) to invoke.  Built-in tools:

* ``image_understand``    — wraps CrossModalUnderstanding (caption / vqa)
* ``video_summarize``     — wraps CrossModalUnderstanding + RAG
* ``document_parse``      — wraps parsers.DocumentParser
* ``voice_transcribe``    — wraps parsers.AudioParser (ASR stub)
* ``cross_modal_search``  — wraps MultimodalRAG

The agent optionally persists each invocation to MemoryPalace (P4-3-W1) and
exposes its tools via an MCP server stub (P4-3-W2).  Both integrations degrade
gracefully when those modules aren't installed.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .parsers import ParsedMedia, parse_media
from .rag import MultimodalRAG
from .types import (
    AgentRequest,
    AgentResponse,
    AgentToolCall,
    AgentToolName,
    MediaRef,
    ModalKind,
    UnderstandingTask,
)
from .understanding import CrossModalUnderstanding

logger = logging.getLogger(__name__)


# ── tool implementations ───────────────────────────────────────────────────
@dataclass
class _ToolSpec:
    name: AgentToolName
    description: str
    args_schema: Dict[str, Any]
    run: Callable[..., Dict[str, Any]]


def _tool_image_understand(und: CrossModalUnderstanding, refs: List[MediaRef], query: Optional[str]) -> Dict[str, Any]:
    image_refs = [m for m in refs if m.kind == ModalKind.IMAGE] or refs
    resp = und.understand(_mk_und_request(UnderstandingTask.VQA, image_refs, query or "describe"))
    return {"text": resp.text, "label": resp.label, "score": resp.score, "model": resp.model}


def _tool_video_summarize(und: CrossModalUnderstanding, refs: List[MediaRef], query: Optional[str]) -> Dict[str, Any]:
    video_refs = [m for m in refs if m.kind == ModalKind.VIDEO] or refs
    resp = und.understand(_mk_und_request(UnderstandingTask.CAPTION, video_refs, query or "summarize the video"))
    return {"summary": resp.text, "model": resp.model, "elapsed_ms": resp.elapsed_ms}


def _tool_document_parse(refs: List[MediaRef], query: Optional[str]) -> Dict[str, Any]:
    doc_refs = [m for m in refs if m.kind == ModalKind.DOCUMENT] or refs
    parsed_list: List[ParsedMedia] = [parse_media(m) for m in doc_refs]
    return {
        "chunks": [p.text for p in parsed_list for _ in (p.chunks or [p.text])][:20],
        "doc_count": len(parsed_list),
        "head": parsed_list[0].text[:200] if parsed_list else "",
    }


def _tool_voice_transcribe(und: CrossModalUnderstanding, refs: List[MediaRef], query: Optional[str]) -> Dict[str, Any]:
    audio_refs = [m for m in refs if m.kind in (ModalKind.AUDIO, ModalKind.VIDEO)] or refs
    resp = und.understand(_mk_und_request(UnderstandingTask.ASR, audio_refs, "transcribe"))
    return {"transcript": resp.text, "elapsed_ms": resp.elapsed_ms}


def _tool_cross_modal_search(rag: MultimodalRAG, refs: List[MediaRef], query: Optional[str]) -> Dict[str, Any]:
    if not refs and not query:
        return {"hits": [], "answer": ""}
    qref = refs[0] if refs else MediaRef(kind=ModalKind.TEXT, text=query or "")
    items = rag.search(qref, top_k=5)
    out = rag.answer(qref, top_k=5)
    return {"hits": [it.to_dict() for it in items], "answer": out.get("text", "")}


def _mk_und_request(task: UnderstandingTask, refs: List[MediaRef], query: str):
    from .types import UnderstandingRequest
    return UnderstandingRequest(task=task, media=refs, query=query)


# ── planner: pick tools from prompt + media ────────────────────────────────
_TOOL_KEYWORDS: Dict[AgentToolName, List[str]] = {
    AgentToolName.IMAGE_UNDERSTAND: ["image", "picture", "photo", "图中", "图片", "看图", "describe"],
    AgentToolName.VIDEO_SUMMARIZE: ["video", "movie", "clip", "视频", "summarize"],
    AgentToolName.DOCUMENT_PARSE: ["document", "pdf", "docx", "paper", "文档", "论文", "parse", "extract"],
    AgentToolName.VOICE_TRANSCRIBE: ["audio", "voice", "speech", "mp3", "音频", "转录", "asr", "transcribe"],
    AgentToolName.CROSS_MODAL_SEARCH: ["search", "find", "lookup", "查询", "搜索", "rag"],
}


def _default_plan(prompt: str, media: List[MediaRef]) -> List[AgentToolName]:
    """Pick tools based on (a) media types and (b) prompt keywords."""
    plan: List[AgentToolName] = []
    pl = (prompt or "").lower()
    kind_set = {m.kind for m in media}
    if ModalKind.IMAGE in kind_set:
        plan.append(AgentToolName.IMAGE_UNDERSTAND)
    if ModalKind.VIDEO in kind_set:
        plan.append(AgentToolName.VIDEO_SUMMARIZE)
    if ModalKind.DOCUMENT in kind_set:
        plan.append(AgentToolName.DOCUMENT_PARSE)
    if ModalKind.AUDIO in kind_set:
        plan.append(AgentToolName.VOICE_TRANSCRIBE)
    for tool, kws in _TOOL_KEYWORDS.items():
        if tool in plan:
            continue
        if any(k.lower() in pl for k in kws):
            plan.append(tool)
    if not plan:
        plan.append(AgentToolName.CROSS_MODAL_SEARCH)
    return plan[:4]


def _synth_text(prompt: str, tool_calls: List[AgentToolCall]) -> str:
    if not tool_calls:
        return f"No tools invoked. Echo: {prompt}"
    chunks = []
    for tc in tool_calls:
        if tc.tool == AgentToolName.IMAGE_UNDERSTAND:
            chunks.append(f"[image-understanding] {tc.result.get('text', '')[:200]}")
        elif tc.tool == AgentToolName.VIDEO_SUMMARIZE:
            chunks.append(f"[video-summary] {tc.result.get('summary', '')[:200]}")
        elif tc.tool == AgentToolName.DOCUMENT_PARSE:
            chunks.append(f"[document] head={tc.result.get('head', '')[:120]}")
        elif tc.tool == AgentToolName.VOICE_TRANSCRIBE:
            chunks.append(f"[transcript] {tc.result.get('transcript', '')[:200]}")
        elif tc.tool == AgentToolName.CROSS_MODAL_SEARCH:
            chunks.append(f"[search] {tc.result.get('answer', '')[:200]}")
    return " ".join(chunks) + f"\nUser: {prompt}"


# ── memory + MCP bridges (graceful degradation) ───────────────────────────
def _try_save_memory(session_id: Optional[str], request_id: str, payload: Dict[str, Any]) -> List[str]:
    """Save invocation summary to MemoryPalace.  Returns list of memory_ids."""
    if not os.environ.get("MULTIMODAL_AGENT_MEMORY", "1") == "1":
        return []
    try:
        from services.agent_service.memory_palace import get_palace  # type: ignore
        palace = get_palace()
        # best-effort API — adapt to whatever shape MemoryPalace exposes
        if hasattr(palace, "save"):
            mid = palace.save(scope=session_id or "multimodal", key=request_id, value=payload)
            return [str(mid)]
        if hasattr(palace, "add"):
            mid = palace.add(scope=session_id or "multimodal", content=payload)
            return [str(mid)]
    except Exception as exc:
        logger.debug("MemoryPalace save failed: %s", exc)
    return []


def _try_mcp_register(tools: List[AgentToolName]) -> Dict[str, Any]:
    """Register tools with the MCP server.  Returns registration status."""
    try:
        from services.agent_service.mcp import get_server  # type: ignore
        server = get_server()
        out = {"registered": 0, "names": []}
        for t in tools:
            if hasattr(server, "register_tool"):
                server.register_tool(name=t.value, handler=None)
                out["registered"] += 1
                out["names"].append(t.value)
        return out
    except Exception as exc:
        logger.debug("MCP register failed: %s", exc)
        return {"registered": 0, "names": [t.value for t in tools], "note": str(exc)}


# ── main agent ─────────────────────────────────────────────────────────────
class MultimodalAgent:
    """Tool-using multimodal agent."""

    def __init__(
        self,
        understanding: Optional[CrossModalUnderstanding] = None,
        rag: Optional[MultimodalRAG] = None,
    ) -> None:
        self.understanding = understanding or CrossModalUnderstanding()
        self.rag = rag or MultimodalRAG()
        self._tools: Dict[AgentToolName, _ToolSpec] = {
            AgentToolName.IMAGE_UNDERSTAND: _ToolSpec(
                AgentToolName.IMAGE_UNDERSTAND, "Understand an image", {"query": "string"},
                lambda refs, query: _tool_image_understand(self.understanding, refs, query),
            ),
            AgentToolName.VIDEO_SUMMARIZE: _ToolSpec(
                AgentToolName.VIDEO_SUMMARIZE, "Summarize a video", {"query": "string"},
                lambda refs, query: _tool_video_summarize(self.understanding, refs, query),
            ),
            AgentToolName.DOCUMENT_PARSE: _ToolSpec(
                AgentToolName.DOCUMENT_PARSE, "Parse a document", {},
                lambda refs, query: _tool_document_parse(refs, query),
            ),
            AgentToolName.VOICE_TRANSCRIBE: _ToolSpec(
                AgentToolName.VOICE_TRANSCRIBE, "Transcribe audio/video", {},
                lambda refs, query: _tool_voice_transcribe(self.understanding, refs, query),
            ),
            AgentToolName.CROSS_MODAL_SEARCH: _ToolSpec(
                AgentToolName.CROSS_MODAL_SEARCH, "Cross-modal RAG search", {"query": "string"},
                lambda refs, query: _tool_cross_modal_search(self.rag, refs, query),
            ),
        }
        self._tool_calls_total = 0

    @property
    def tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": s.name.value, "description": s.description, "args_schema": s.args_schema}
            for s in self._tools.values()
        ]

    # ── core entry ──────────────────────────────────────────────────────
    def invoke(self, req: AgentRequest) -> AgentResponse:
        t0 = time.time()
        plan = _default_plan(req.prompt, req.media)
        tool_calls: List[AgentToolCall] = []
        for tool_name in plan:
            spec = self._tools.get(tool_name)
            if spec is None:
                continue
            try:
                result = spec.run(refs=req.media, query=req.prompt)
            except Exception as exc:
                result = {"error": str(exc)}
            tool_calls.append(AgentToolCall(tool=tool_name, args={"query": req.prompt, "media_count": len(req.media)}, result=result))
            self._tool_calls_total += 1
        text = _synth_text(req.prompt, tool_calls)
        output_media: List[MediaRef] = []  # future: when agent can generate, fill here
        memory_ids: List[str] = []
        if req.save_to_memory:
            memory_ids = _try_save_memory(
                req.session_id,
                req.request_id,
                {"prompt": req.prompt, "tools": [tc.tool.value for tc in tool_calls], "result_preview": text[:200]},
            )
        elapsed = round((time.time() - t0) * 1000, 2)
        return AgentResponse(
            request_id=req.request_id,
            text=text,
            tool_calls=tool_calls,
            output_media=output_media,
            memory_ids=memory_ids,
            elapsed_ms=elapsed,
        )

    def invoke_batch(self, requests: List[AgentRequest]) -> List[AgentResponse]:
        return [self.invoke(r) for r in requests]

    # ── MCP surface ─────────────────────────────────────────────────────
    def register_mcp_tools(self) -> Dict[str, Any]:
        return _try_mcp_register(list(self._tools.keys()))