"""Workspace notification inbox API (Wave 15)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


class NotificationCreate(BaseModel):
    workspace_id: UUID
    recipient_user_id: UUID
    kind: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=240)
    message: str = Field(default="", max_length=4000)
    link: str | None = Field(default=None, max_length=2048)
    data: dict = Field(default_factory=dict)


async def membership(db: AsyncSession, user: User, workspace_id: UUID):
    row = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id))
    if not row:
        raise HTTPException(403, "Workspace access required")
    return row


@router.post("", status_code=201)
async def create_notification(body: NotificationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    sender_membership = await membership(db, user, body.workspace_id)
    recipient_membership = await db.scalar(select(Membership).where(
        Membership.user_id == body.recipient_user_id, Membership.workspace_id == body.workspace_id
    ))
    if recipient_membership is None:
        raise HTTPException(422, "Recipient must be a workspace member")
    if sender_membership.role.lower() not in {"owner", "admin"} and body.recipient_user_id != user.id:
        raise HTTPException(403, "Only workspace owners/admins may notify other members")
    record = CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="notification",
        title=body.title.strip(), status="unread",
        payload={"recipient_user_id": str(body.recipient_user_id), "kind": body.kind.strip(),
                 "message": body.message.strip(), "link": body.link, "data": body.data,
                 "created_at": datetime.now(timezone.utc).isoformat(), "read_at": None})
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "status": record.status, "notification": record.payload}


@router.get("")
async def list_notifications(workspace_id: UUID, unread_only: bool = False,
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    query = select(CreatorRecord).where(CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "notification",
        CreatorRecord.payload["recipient_user_id"].as_string() == str(user.id))
    if unread_only:
        query = query.where(CreatorRecord.status == "unread")
    rows = await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {"workspace_id": str(workspace_id), "items": [
        {"id": str(row.id), "status": row.status, "title": row.title, "payload": row.payload,
         "created_at": row.created_at.isoformat()} for row in rows
    ], "limit": limit, "offset": offset}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: UUID, workspace_id: UUID, db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    record = await db.scalar(select(CreatorRecord).where(CreatorRecord.id == notification_id,
        CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "notification",
        CreatorRecord.payload["recipient_user_id"].as_string() == str(user.id)).with_for_update())
    if record is None:
        raise HTTPException(404, "Notification not found")
    if record.status != "read":
        record.status = "read"
        payload = dict(record.payload or {})
        payload["read_at"] = datetime.now(timezone.utc).isoformat()
        record.payload = payload
        await db.commit()
    return {"id": str(record.id), "status": record.status}


@router.post("/read-all")
async def mark_all_read(workspace_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    rows = await db.scalars(select(CreatorRecord).where(CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "notification", CreatorRecord.status == "unread",
        CreatorRecord.payload["recipient_user_id"].as_string() == str(user.id)).with_for_update())
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for record in rows:
        record.status = "read"
        payload = dict(record.payload or {})
        payload["read_at"] = now
        record.payload = payload
        count += 1
    await db.commit()
    return {"marked_read": count}
