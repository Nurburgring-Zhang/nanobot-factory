"""
P4-10-W2: 工单 HTTP API
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import (
    TICKET_TYPES, TICKET_TYPE_LABELS, PRIORITIES, STATES, SLA_HOURS,
    create_ticket, get_ticket, list_tickets, transition_ticket,
    add_ticket_comment, assign_ticket, sla_stats, on_customer_ticket,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


class TicketCreate(BaseModel):
    type: str = Field(..., description="problem/feature_request/billing/incident")
    priority: str = Field("P3", description="P0/P1/P2/P3")
    subject: str = Field(..., min_length=1, max_length=200)
    description: str
    customer_id: Optional[str] = None
    reporter: str = "anonymous"


class TicketTransition(BaseModel):
    new_status: str
    by: str = "system"


class TicketAssign(BaseModel):
    assignee: str = Field(..., min_length=1)


class TicketComment(BaseModel):
    content: str = Field(..., min_length=1)
    by: str
    internal: bool = False


@router.get("/_meta")
def meta():
    return {
        "types": [{"key": k, "label": v} for k, v in TICKET_TYPE_LABELS.items()],
        "priorities": PRIORITIES,
        "states": STATES,
        "sla_hours": SLA_HOURS,
    }


@router.post("")
def create(req: TicketCreate):
    try:
        data = req.model_dump()
        data["ticket_type"] = data.pop("type")
        t = create_ticket(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return t.to_dict()


@router.get("")
def list_all(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    assignee: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
):
    items = list_tickets(status=status, priority=priority, ticket_type=type, assignee=assignee, customer_id=customer_id)
    return {"items": [t.to_dict() for t in items], "total": len(items)}


@router.get("/sla/stats")
def stats():
    return sla_stats()


@router.get("/{ticket_id}")
def get_one(ticket_id: str):
    t = get_ticket(ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    return t.to_dict()


@router.post("/{ticket_id}/transition")
def transition(ticket_id: str, req: TicketTransition):
    try:
        t = transition_ticket(ticket_id, req.new_status, by=req.by)
    except KeyError:
        raise HTTPException(status_code=404, detail="ticket not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return t.to_dict()


@router.post("/{ticket_id}/assign")
def assign(ticket_id: str, req: TicketAssign):
    try:
        t = assign_ticket(ticket_id, req.assignee)
    except KeyError:
        raise HTTPException(status_code=404, detail="ticket not found")
    return t.to_dict()


@router.post("/{ticket_id}/comments")
def add_comment(ticket_id: str, req: TicketComment):
    try:
        c = add_ticket_comment(ticket_id, req.content, req.by, req.internal)
    except KeyError:
        raise HTTPException(status_code=404, detail="ticket not found")
    return c


@router.post("/_hook/on_customer_ticket")
def hook(customer_id: str, ticket_type: str, subject: str, description: str, priority: str = "P3"):
    t = on_customer_ticket(customer_id, ticket_type, subject, description, priority)
    return t.to_dict()
