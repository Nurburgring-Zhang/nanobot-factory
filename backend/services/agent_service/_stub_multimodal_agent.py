"""Lightweight fallback MultimodalAgent used when imdf.multimodal isn't importable."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ...imdf.multimodal.types import (
    AgentRequest,
    AgentResponse,
    AgentToolCall,
    AgentToolName,
    MediaRef,
)


@dataclass
class StubMultimodalAgent:
    """Pure stub used when the imdf.multimodal package is unavailable.

    Returns a deterministic AgentResponse with the same shape as the real
    implementation — enough for the agent-service smoke tests to pass.
    """

    name: str = "multimodal-agent-stub"

    @property
    def tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": AgentToolName.IMAGE_UNDERSTAND.value, "description": "stub", "args_schema": {}},
            {"name": AgentToolName.VIDEO_SUMMARIZE.value, "description": "stub", "args_schema": {}},
            {"name": AgentToolName.DOCUMENT_PARSE.value, "description": "stub", "args_schema": {}},
            {"name": AgentToolName.VOICE_TRANSCRIBE.value, "description": "stub", "args_schema": {}},
            {"name": AgentToolName.CROSS_MODAL_SEARCH.value, "description": "stub", "args_schema": {}},
        ]

    def invoke(self, req: AgentRequest) -> AgentResponse:
        tool_calls = [
            AgentToolCall(tool=AgentToolName.CROSS_MODAL_SEARCH, args={"query": req.prompt}, result={"answer": "[stub] multimodal agent response"})
        ]
        return AgentResponse(
            request_id=req.request_id,
            text=f"[stub] multimodal agent processed: {req.prompt}",
            tool_calls=tool_calls,
            elapsed_ms=0.1,
        )