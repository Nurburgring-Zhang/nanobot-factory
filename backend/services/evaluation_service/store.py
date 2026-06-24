"""P3-2-W2 evaluation-service in-memory store.

Persists evaluations + bad cases to JSON files under ``data_dir``.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class EvaluationStore:
    """Key-value store for evaluation tasks and bad cases."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._evaluations: Dict[str, Dict[str, Any]] = {}
        self._bad_cases: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────
    def _eval_path(self) -> Path:
        return self.data_dir / "evaluations.json"

    def _bc_path(self) -> Path:
        return self.data_dir / "bad_cases.json"

    def _load(self):
        if self._eval_path().exists():
            try:
                with self._eval_path().open("r", encoding="utf-8") as fp:
                    self._evaluations = json.load(fp) or {}
            except Exception:
                self._evaluations = {}
        if self._bc_path().exists():
            try:
                with self._bc_path().open("r", encoding="utf-8") as fp:
                    self._bad_cases = json.load(fp) or {}
            except Exception:
                self._bad_cases = {}

    def _save_evals(self):
        with self._eval_path().open("w", encoding="utf-8") as fp:
            json.dump(self._evaluations, fp, ensure_ascii=False, indent=2)

    def _save_bcs(self):
        with self._bc_path().open("w", encoding="utf-8") as fp:
            json.dump(self._bad_cases, fp, ensure_ascii=False, indent=2)

    # ── evaluations ──────────────────────────────────────────────────────
    def create_evaluation(
        self,
        name: str,
        model_name: str,
        dataset_name: str,
        dataset_version: str,
        metrics: List[str],
        sample_size: int,
        description: str = "",
    ) -> Dict[str, Any]:
        eid = uuid.uuid4().hex[:16]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        e = {
            "id": eid,
            "name": name,
            "description": description,
            "model_name": model_name,
            "dataset_name": dataset_name,
            "dataset_version": dataset_version,
            "metrics": metrics,
            "sample_size": sample_size,
            "status": "pending",
            "created_at": now,
            "started_at": "",
            "completed_at": "",
            "sample_results": [],
            "summary": {},
        }
        self._evaluations[eid] = e
        self._save_evals()
        return e

    def list_evaluations(
        self,
        model_name: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        out = list(self._evaluations.values())
        if model_name:
            out = [e for e in out if e["model_name"] == model_name]
        if status_filter:
            out = [e for e in out if e["status"] == status_filter]
        out.sort(key=lambda e: e["created_at"], reverse=True)
        return out[offset : offset + limit]

    def get_evaluation(self, eval_id: str) -> Optional[Dict[str, Any]]:
        return self._evaluations.get(eval_id)

    def update_evaluation(self, eval_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        e = self._evaluations.get(eval_id)
        if not e:
            return None
        e.update(fields)
        self._save_evals()
        return e

    def count_evaluations(self) -> int:
        return len(self._evaluations)

    # ── bad cases ────────────────────────────────────────────────────────
    def add_bad_case(
        self,
        evaluation_id: str,
        sample_id: str,
        reason: str,
        sample: Dict[str, Any],
    ) -> Dict[str, Any]:
        cid = uuid.uuid4().hex[:16]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        bc = {
            "id": cid,
            "evaluation_id": evaluation_id,
            "sample_id": sample_id,
            "reason": reason,
            "sample": sample,
            "status": "open",
            "created_at": now,
            "updated_at": now,
            "note": "",
        }
        self._bad_cases[cid] = bc
        self._save_bcs()
        return bc

    def list_bad_cases(
        self,
        evaluation_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        out = list(self._bad_cases.values())
        if evaluation_id:
            out = [b for b in out if b["evaluation_id"] == evaluation_id]
        if status_filter:
            out = [b for b in out if b["status"] == status_filter]
        out.sort(key=lambda b: b["created_at"], reverse=True)
        return out[offset : offset + limit]

    def get_bad_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        return self._bad_cases.get(case_id)

    def update_bad_case(self, case_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        bc = self._bad_cases.get(case_id)
        if not bc:
            return None
        fields["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        bc.update(fields)
        self._save_bcs()
        return bc

    def count_bad_cases(self) -> int:
        return len(self._bad_cases)
