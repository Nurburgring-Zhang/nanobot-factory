"""数据交付审核流程引擎"""
from __future__ import annotations
import time
import copy
import hashlib
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Delivery:
    """交付物"""
    id: str
    dataset_version: str
    requester: str
    status: str = "draft"  # draft / submitted / in_review / approved / rejected
    reviewer: Optional[str] = None
    reviews: List[DeliveryReview] = field(default_factory=list)
    content_hash: Optional[str] = None
    version_history: List[str] = field(default_factory=list)  # previous version ids

    def compute_hash(self, content: str) -> str:
        h = hashlib.sha256(content.encode()).hexdigest()
        self.content_hash = h
        return h


@dataclass
class DeliveryReview:
    """审核记录"""
    delivery_id: str
    reviewer: str
    verdict: str  # approved / rejected / needs_revision
    comments: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class DataDelivery:
    """数据交付管理 - 审核流程、多人审核链、版本对比"""

    def __init__(self):
        self.deliveries: Dict[str, Delivery] = {}
        self._review_chain: Dict[str, List[str]] = {}  # delivery_id -> ordered reviewer list

    # ── lifecycle ──

    def create_delivery(self, delivery_id: str, dataset_version: str,
                        requester: str) -> Delivery:
        d = Delivery(id=delivery_id, dataset_version=dataset_version,
                     requester=requester)
        self.deliveries[delivery_id] = d
        return d

    def submit_for_review(self, delivery_id: str,
                          content: str = "") -> bool:
        d = self.deliveries.get(delivery_id)
        if not d or d.status != "draft":
            return False
        if content:
            d.compute_hash(content)
        d.status = "submitted"
        return True

    # ── review chain (multi-person) ──

    def set_review_chain(self, delivery_id: str,
                         reviewers: List[str]):
        """设置多人审核链 - 按顺序审核"""
        self._review_chain[delivery_id] = reviewers

    def get_current_reviewer(self, delivery_id: str) -> Optional[str]:
        chain = self._review_chain.get(delivery_id, [])
        d = self.deliveries.get(delivery_id)
        if not d:
            return None
        reviewed_count = len([r for r in d.reviews if r.verdict in ("approved", "rejected")])
        if reviewed_count < len(chain):
            return chain[reviewed_count]
        return None

    def review_delivery(self, delivery_id: str, reviewer: str,
                        verdict: str, comments: str = "",
                        metrics: Optional[Dict] = None) -> bool:
        d = self.deliveries.get(delivery_id)
        if not d or d.status not in ("submitted", "in_review"):
            return False

        # check chain order
        current = self.get_current_reviewer(delivery_id)
        if current and current != reviewer:
            return False  # not this reviewer's turn

        review = DeliveryReview(
            delivery_id=delivery_id,
            reviewer=reviewer,
            verdict=verdict,
            comments=comments,
            metrics=metrics or {},
        )
        d.reviews.append(review)
        d.reviewer = reviewer

        if verdict == "approved":
            d.status = "in_review"
            # check if all reviewers approved
            chain = self._review_chain.get(delivery_id, [reviewer])
            approved_count = len([r for r in d.reviews if r.verdict == "approved"])
            if approved_count >= len(chain):
                d.status = "approved"
        elif verdict == "rejected":
            d.status = "rejected"
        elif verdict == "needs_revision":
            d.status = "draft"

        return True

    def approve(self, delivery_id: str, reviewer: str,
                comments: str = "") -> bool:
        return self.review_delivery(delivery_id, reviewer, "approved", comments)

    def reject(self, delivery_id: str, reviewer: str,
               comments: str = "") -> bool:
        return self.review_delivery(delivery_id, reviewer, "rejected", comments)

    def request_revision(self, delivery_id: str, reviewer: str,
                         comments: str = "") -> bool:
        return self.review_delivery(delivery_id, reviewer, "needs_revision", comments)

    # ── version compare ──

    def compare_versions(self, delivery_id_a: str,
                         delivery_id_b: str) -> dict:
        """版本对比：比较两个交付物的版本号、状态、审核历史"""
        d_a = self.deliveries.get(delivery_id_a)
        d_b = self.deliveries.get(delivery_id_b)
        if not d_a or not d_b:
            return {"error": "one or both deliveries not found"}

        return {
            "left": {
                "id": d_a.id,
                "dataset_version": d_a.dataset_version,
                "status": d_a.status,
                "content_hash": d_a.content_hash,
                "review_count": len(d_a.reviews),
            },
            "right": {
                "id": d_b.id,
                "dataset_version": d_b.dataset_version,
                "status": d_b.status,
                "content_hash": d_b.content_hash,
                "review_count": len(d_b.reviews),
            },
            "version_match": d_a.dataset_version == d_b.dataset_version,
            "hash_match": d_a.content_hash == d_b.content_hash,
            "both_approved": d_a.status == "approved" and d_b.status == "approved",
        }
