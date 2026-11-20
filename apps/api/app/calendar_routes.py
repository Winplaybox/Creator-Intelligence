"""Workspace-scoped content calendar and approval workflow (Wave 7)."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/workflows", tags=["content-calendar"])

CalendarStatus = Literal["draft", "planned", "needs_review", "approved", "rejected", "in_production", "published"]


class CalendarCreateRequest(BaseModel):
    workspace_id: UUID
    title: str = Field(min_length=3, max_length=240)
    topic: str = Field(default="", max_length=160)
    scheduled_at: datetime | None = None
    platform: str = Field(default="youtube", min_length=2, max_length=40)
    notes: str = Field(default="", max_length=4000)


class CalendarStatusRequest(BaseModel):
    workspace_id: UUID
    status: CalendarStatus
    notes: str = Field(default="", max_length=2000)


async def require_calendar_membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.workspace_id == workspace_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Workspace access required")
    return membership


@router.post("/calendar", status_code=201)
async def create_calendar_item(
    body: CalendarCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_calendar_membership(db, user, body.workspace_id)
    title = body.title.strip()
    platform = body.platform.strip().lower()
    if not title or not platform:
        raise HTTPException(422, detail="Title and platform must not be blank")
    payload = {
        "topic": body.topic.strip(),
        "platform": platform,
        "scheduled_at": body.scheduled_at.isoformat() if body.scheduled_at else None,
        "notes": body.notes.strip(),
        "approval_history": [],
    }
    record = CreatorRecord(
        workspace_id=body.workspace_id,
        created_by=user.id,
        module="content_calendar",
        title=title,
        payload=payload,
        status="draft",
        due_at=body.scheduled_at,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {
        "id": str(record.id),
        "status": record.status,
        "title": record.title,
        "payload": record.payload,
        "scheduled_at": record.due_at.isoformat() if record.due_at else None,
    }


@router.get("/calendar")
async def list_calendar_items(
    workspace_id: UUID,
    status: CalendarStatus | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_calendar_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "content_calendar",
    )
    if status:
        query = query.where(CreatorRecord.status == status)
    rows = await db.scalars(
        query.order_by(asc(CreatorRecord.due_at), desc(CreatorRecord.created_at)).offset(offset).limit(limit)
    )
    return {
        "workspace_id": str(workspace_id),
        "items": [
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "payload": row.payload,
                "scheduled_at": row.due_at.isoformat() if row.due_at else None,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.patch("/calendar/{item_id}/status")
async def update_calendar_status(
    item_id: UUID,
    body: CalendarStatusRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    membership = await require_calendar_membership(db, user, body.workspace_id)
    record = await db.scalar(
        select(CreatorRecord).where(
            CreatorRecord.id == item_id,
            CreatorRecord.workspace_id == body.workspace_id,
            CreatorRecord.module == "content_calendar",
        )
    )
    if record is None:
        raise HTTPException(404, detail="Calendar item not found")

    transitions = {
        "draft": {"planned", "needs_review"},
        "planned": {"draft", "needs_review"},
        "needs_review": {"approved", "rejected", "draft"},
        "rejected": {"draft", "needs_review"},
        "approved": {"in_production", "planned"},
        "in_production": {"approved", "published"},
        "published": set(),
    }
    previous_status = record.status
    if body.status not in transitions.get(previous_status, set()):
        raise HTTPException(409, detail=f"Invalid status transition: {previous_status} -> {body.status}")
    if body.status in {"approved", "rejected"} and membership.role.lower() not in {"owner", "admin"}:
        raise HTTPException(403, detail="Only workspace owners or admins can approve or reject content")

    payload = dict(record.payload or {})
    history = list(payload.get("approval_history", []))
    history.append({
        "from": previous_status,
        "to": body.status,
        "note": body.notes.strip(),
        "actor_id": str(user.id),
        "at": datetime.now(timezone.utc).isoformat(),
    })
    payload["approval_history"] = history
    record.status = body.status
    record.payload = payload
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "status": record.status, "payload": record.payload}
