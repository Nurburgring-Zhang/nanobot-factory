"""annot.text.qa_pair — question/answer pair annotation operator.

Inputs:
    items: list of dicts {id?, question: str, answers: [{text, start?, end?, score?}], context?: str}
    params:
        max_answers: int = 5
        min_answer_length: int = 1
        max_answer_length: int = 10000
        require_context: bool = False
        validate_offsets: bool = True       — if True, verify answer.start/end lies in context
        deduplicate: bool = True           — drop duplicate texts

Returns per-item: {item_index, ok, question_length, answer_count, answers: [...]}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List


def _validate(ans: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": ans.get("id") or f"ans_{uuid.uuid4().hex[:8]}",
        "text": str(ans.get("text", "")),
        "start": int(ans["start"]) if ans.get("start") is not None else None,
        "end": int(ans["end"]) if ans.get("end") is not None else None,
        "score": float(ans.get("score", 1.0)),
    }


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_a = int(params.get("max_answers", 5))
    min_len = int(params.get("min_answer_length", 1))
    max_len = int(params.get("max_answer_length", 10000))
    require_ctx = bool(params.get("require_context", False))
    validate_off = bool(params.get("validate_offsets", True))
    dedup = bool(params.get("deduplicate", True))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            rec.update({"ok": False, "answer_count": 0, "answers": [],
                        "error": "missing_question"})
            out.append(rec)
            continue
        ctx = item.get("context")
        if require_ctx and not isinstance(ctx, str):
            rec.update({"ok": False, "answer_count": 0, "answers": [],
                        "error": "missing_context"})
            out.append(rec)
            continue
        raw_ans = item.get("answers", []) or []
        ans = [_validate(a) for a in raw_ans]
        ans = [a for a in ans if min_len <= len(a["text"]) <= max_len]
        if validate_off and isinstance(ctx, str):
            for a in ans:
                if a["start"] is not None and a["end"] is not None:
                    if a["start"] < 0 or a["end"] > len(ctx) or a["start"] > a["end"]:
                        a["start"] = None
                        a["end"] = None
                    elif ctx[a["start"]:a["end"]] != a["text"]:
                        # offsets don't match text → drop offsets
                        a["start"] = None
                        a["end"] = None
        ans.sort(key=lambda a: a["score"], reverse=True)
        if dedup:
            seen: set = set()
            uniq: List[Dict[str, Any]] = []
            for a in ans:
                key = a["text"].strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(a)
            ans = uniq
        ans = ans[:max_a]
        rec.update({
            "ok": True,
            "id": item.get("id"),
            "question_length": len(item["question"]),
            "has_context": isinstance(ctx, str),
            "context_length": len(ctx) if isinstance(ctx, str) else 0,
            "answer_count": len(ans),
            "answers": ans,
        })
        out.append(rec)
    return out