"""
P4-10-W2: CRM HTTP API
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr

from . import (
    TIERS, TIER_LABELS, INDUSTRIES, SIZES,
    FOLLOWUP_TYPES, FOLLOWUP_LABELS,
    CONTACT_ROLES, CONTACT_ROLE_LABELS,
    create_customer, get_customer, list_customers, update_customer, delete_customer, add_followup,
    create_contact, list_contacts, get_contact, update_contact, delete_contact,
    on_plan_upgrade,
    recompute_customer_score, recompute_all_scores, get_top_leads, get_lead_stats,
)
from .segments import (
    Segment, define_segment, evaluate_segment, match_customers,
    list_segments, get_segment, delete_segment, update_segment_count,
    evaluate_all_segments, get_segment_stats, create_preset, PRESET_TEMPLATES,
    SUPPORTED_FIELDS, SUPPORTED_OPS, COMBINATORS,
)

router_customers = APIRouter(prefix="/api/v1/crm/customers", tags=["crm-customers"])
router_contacts = APIRouter(prefix="/api/v1/crm/contacts", tags=["crm-contacts"])
router_leads = APIRouter(prefix="/api/v1/crm/leads", tags=["crm-leads"])
router_segments = APIRouter(prefix="/api/v1/crm/segments", tags=["crm-segments"])


# ---------------- Customers ----------------
class CustomerCreate(BaseModel):
    company_name: str
    contact_name: str
    email: str
    phone: str = ""
    industry: str = "其他"
    size: str = "1-10"
    tier: str = "individual"
    tags: List[str] = []
    manager_id: Optional[str] = None


class CustomerUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    tier: Optional[str] = None
    tags: Optional[List[str]] = None
    manager_id: Optional[str] = None
    status: Optional[str] = None
    lifetime_value: Optional[float] = None


class FollowupCreate(BaseModel):
    type: str = Field(..., description="communication/contract/payment/complaint/other")
    content: str
    by: str = "system"


@router_customers.get("/_meta")
def meta():
    return {
        "tiers": [{"key": k, "label": v} for k, v in TIER_LABELS.items()],
        "industries": INDUSTRIES,
        "sizes": SIZES,
        "followup_types": [{"key": k, "label": v} for k, v in FOLLOWUP_LABELS.items()],
    }


@router_customers.post("")
def create(req: CustomerCreate):
    try:
        c = create_customer(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # P1-1: 新建客户自动打分
    recompute_customer_score(c)
    return c.to_dict()


@router_customers.get("")
def list_all(
    tier: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    manager_id: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    items = list_customers(tier=tier, industry=industry, manager_id=manager_id, tag=tag, search=search)
    return {"items": [c.to_dict() for c in items], "total": len(items)}


@router_customers.get("/{customer_id}")
def get_one(customer_id: str):
    c = get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return c.to_dict()


@router_customers.patch("/{customer_id}")
def update(customer_id: str, req: CustomerUpdate):
    c = update_customer(customer_id, **{k: v for k, v in req.model_dump().items() if v is not None})
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return c.to_dict()


@router_customers.delete("/{customer_id}")
def delete(customer_id: str):
    ok = delete_customer(customer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="customer not found")
    return {"deleted": True}


@router_customers.post("/{customer_id}/followups")
def add_fu(customer_id: str, req: FollowupCreate):
    try:
        fu = add_followup(customer_id, req.type, req.content, req.by)
    except KeyError:
        raise HTTPException(status_code=404, detail="customer not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return fu


@router_customers.post("/{customer_id}/upgrade")
def upgrade(customer_id: str, new_plan: str):
    try:
        return on_plan_upgrade(customer_id, new_plan)
    except KeyError:
        raise HTTPException(status_code=404, detail="customer not found")


# ---------------- Contacts ----------------
class ContactCreate(BaseModel):
    customer_id: str
    name: str
    role: str
    email: str = ""
    phone: str = ""
    is_primary: bool = False


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary: Optional[bool] = None


@router_contacts.get("/_meta")
def contact_meta():
    return {"roles": [{"key": k, "label": v} for k, v in CONTACT_ROLE_LABELS.items()]}


@router_contacts.post("")
def create_c(req: ContactCreate):
    try:
        c = create_contact(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    return c.to_dict()


@router_contacts.get("")
def list_c(customer_id: str = Query(...)):
    return {"items": [c.to_dict() for c in list_contacts(customer_id)], "total": len(list_contacts(customer_id))}


@router_contacts.get("/{contact_id}")
def get_c(contact_id: str):
    c = get_contact(contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="contact not found")
    return c.to_dict()


@router_contacts.patch("/{contact_id}")
def update_c(contact_id: str, req: ContactUpdate):
    c = update_contact(contact_id, **{k: v for k, v in req.model_dump().items() if v is not None})
    if not c:
        raise HTTPException(status_code=404, detail="contact not found")
    return c.to_dict()


@router_contacts.delete("/{contact_id}")
def delete_c(contact_id: str):
    ok = delete_contact(contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="contact not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# P1-1: Lead scoring 路由
# ---------------------------------------------------------------------------
@router_leads.get("/top")
def top_leads(
    limit: int = Query(20, ge=1, le=200),
    grade: Optional[str] = Query(None, pattern="^(A|B|C|D)$"),
):
    items = get_top_leads(limit=limit, grade=grade)
    return {
        "items": [c.to_dict() for c in items],
        "total": len(items),
        "filter_grade": grade,
    }


@router_leads.get("/stats")
def lead_stats():
    return get_lead_stats()


@router_leads.post("/recompute")
def recompute_scores(customer_id: Optional[str] = Query(None)):
    """单客户或全量重算 lead score."""
    if customer_id:
        c = get_customer(customer_id)
        if not c:
            raise HTTPException(status_code=404, detail="customer not found")
        res = recompute_customer_score(c)
        return {"customer_id": customer_id, "score": res}
    n = recompute_all_scores()
    return {"recomputed": n}


@router_customers.post("/{customer_id}/rescore")
def rescore_customer(customer_id: str):
    """手动触发单个客户打分刷新 (在添加跟进/更新后)."""
    c = get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    res = recompute_customer_score(c)
    return {"customer_id": customer_id, "score": res}


# ---------------------------------------------------------------------------
# P1-9: 客户细分 (Segments) 路由
# ---------------------------------------------------------------------------
class DefineSegmentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=512)
    rules: dict


@router_segments.get("/_meta")
def segments_meta():
    return {
        "supported_fields": sorted(SUPPORTED_FIELDS),
        "supported_ops": sorted(SUPPORTED_OPS),
        "combinators": sorted(COMBINATORS),
        "presets": list(PRESET_TEMPLATES.keys()),
    }


@router_segments.post("")
def define_seg(req: DefineSegmentRequest):
    try:
        s = define_segment(
            name=req.name, description=req.description, rules=req.rules,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return s.to_dict()


@router_segments.post("/preset/{preset_key}")
def define_preset(preset_key: str):
    try:
        s = create_preset(preset_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return s.to_dict()


@router_segments.get("")
def list_segs():
    items = list_segments()
    # 自动 refresh count
    update_segment_count()
    return {"count": len(items), "items": [s.to_dict() for s in items]}


@router_segments.get("/stats")
def segments_stats():
    return get_segment_stats()


@router_segments.get("/{segment_id}")
def get_seg(segment_id: str):
    s = get_segment(segment_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"segment {segment_id!r} not found")
    return s.to_dict()


@router_segments.get("/{segment_id}/customers")
def get_seg_customers(segment_id: str):
    s = get_segment(segment_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"segment {segment_id!r} not found")
    matches = match_customers(s)
    return {
        "segment_id": segment_id,
        "count": len(matches),
        "items": [c.to_dict() for c in matches],
    }


@router_segments.delete("/{segment_id}")
def del_seg(segment_id: str):
    if not delete_segment(segment_id):
        raise HTTPException(status_code=404, detail=f"segment {segment_id!r} not found")
    return {"deleted": True, "segment_id": segment_id}
