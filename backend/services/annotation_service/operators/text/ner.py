"""annot.text.ner — named-entity recognition operator.

Inputs:
    items: list of dicts {text: str, entities?: [{start, end, label, text?}]}
    params:
        entity_types: list = []         — empty=allow-all; otherwise whitelist
        min_length: int = 1
        allow_overlap: bool = False
        merge_strategy: str = "longest"  — longest | first | last
        case_sensitive: bool = False

Each entity: {start:int, end:int, label:str, text?:str}. text is auto-filled from input.

Returns per-item: {item_index, ok, count, entities: [...], text_length}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List


def _validate(ent: Dict[str, Any], text: str) -> Dict[str, Any]:
    start = int(ent.get("start", 0))
    end = int(ent.get("end", start))
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    txt = ent.get("text")
    if txt is None:
        txt = text[start:end]
    return {
        "id": ent.get("id") or f"ent_{uuid.uuid4().hex[:8]}",
        "start": start,
        "end": end,
        "label": str(ent.get("label", "entity")),
        "text": txt,
        "score": float(ent.get("score", 1.0)),
    }


def _drop_overlap(ents: List[Dict[str, Any]], strategy: str) -> List[Dict[str, Any]]:
    if not ents:
        return ents
    if strategy == "longest":
        ents = sorted(ents, key=lambda e: -(e["end"] - e["start"]))
    elif strategy == "first":
        ents = sorted(ents, key=lambda e: e["start"])
    elif strategy == "last":
        ents = sorted(ents, key=lambda e: e["start"], reverse=True)
    out: List[Dict[str, Any]] = []
    for e in ents:
        if not any(e["start"] < o["end"] and o["start"] < e["end"] for o in out):
            out.append(e)
    return out


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    types = set(str(x) for x in params.get("entity_types") or [])
    min_len = int(params.get("min_length", 1))
    no_overlap = not bool(params.get("allow_overlap", False))
    strategy = str(params.get("merge_strategy", "longest"))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            rec.update({"ok": False, "count": 0, "entities": [],
                        "error": "missing_text"})
            out.append(rec)
            continue
        text = item["text"]
        ents_raw = item.get("entities", []) or []
        ents = [_validate(e, text) for e in ents_raw]
        if types:
            ents = [e for e in ents if e["label"] in types]
        ents = [e for e in ents if (e["end"] - e["start"]) >= min_len]
        if no_overlap:
            ents = _drop_overlap(ents, strategy)
        ents.sort(key=lambda e: e["start"])
        rec.update({
            "ok": True,
            "text_length": len(text),
            "count": len(ents),
            "entities": ents,
        })
        out.append(rec)
    return out