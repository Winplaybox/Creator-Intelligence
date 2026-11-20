"""Workspace publishing queue and worker lease API (Wave 10).

This module coordinates queue records; it does not publish to social platforms.
A worker must claim an item, perform provider publishing, and report the result.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/publishing", tags=["publishing-queue"])


class QueueCreateRequest(BaseModel):
    workspace_id: UUID
    title: str = Field(min_length=3, max_length=240)
    platform: str = Field(min_length=2, max_length=40)
    scheduled_at: datetime | None = None
    content: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class QueueResultRequest(BaseModel):
    workspace_id: UUID
    result: dict = Field(default_factory=dict)


class QueueCancelRequest(BaseModel):
    workspace_id: UUID


async def require_membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    member = await db.scalar(select(Membership).where(
        Membership.user_id == user.id,
        Membership.workspace_id == workspace_id,
    ))
    if member is None:
        raise HTTPException(403, "Workspace access required")
    return member


@router.post("/queue", status_code=201)
async def enqueue(
    body: QueueCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, body.workspace_id)
    platform = body.platform.strip().lower()
    title = body.title.strip()
    if not platform or not title:
        raise HTTPException(422, "Title and platform must not be blank")
    scheduled = body.scheduled_at
    if scheduled and scheduled.tzinfo is None:
        raise HTTPException(422, "scheduled_at must include timezone")
    payload = {
        "platform": platform,
        "content": body.content,
        "metadata": body.metadata,
        "attempts": 0,
        "last_error": None,
        "lease": None,
    }
    record = CreatorRecord(
        workspace_id=body.workspace_id,
        created_by=user.id,
        module="publishing_queue",
        title=title,
        payload=payload,
        status="queued",
        due_at=scheduled,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "status": record.status, "scheduled_at": record.due_at.isoformat() if record.due_at else None}


@router.get("/queue")
async def list_queue(
    workspace_id: UUID,
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "publishing_queue",
    )
    if status:
        query = query.where(CreatorRecord.status == status)
    rows = await db.scalars(query.order_by(asc(CreatorRecord.due_at)).offset(offset).limit(limit))
    return {
        "workspace_id": str(workspace_id),
        "items": [
            {"id": str(r.id), "title": r.title, "status": r.status, "scheduled_at": r.due_at.isoformat() if r.due_at else None,
             "payload": r.payload, "created_at": r.created_at.isoformat()}
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.post("/queue/claim")
async def claim_next(
    workspace_id: UUID,
    lease_seconds: int = Query(300, ge=30, le=1800),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, workspace_id)
    now = datetime.now(timezone.utc)
    stmt = (
        select(CreatorRecord)
        .where(
            CreatorRecord.workspace_id == workspace_id,
            CreatorRecord.module == "publishing_queue",
            CreatorRecord.status == "queued",
            (CreatorRecord.due_at.is_(None)) | (CreatorRecord.due_at <= now),
        )
        .order_by(asc(CreatorRecord.due_at), asc(CreatorRecord.created_at))
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    record = await db.scalar(stmt)
    if record is None:
        return {"claimed": False, "item": None}
    payload = dict(record.payload or {})
    token = UUID(int=__import__("uuid").uuid4().int).hex
    expires = now + timedelta(seconds=lease_seconds)
    payload["lease"] = {"token": token, "expires_at": expires.isoformat(), "worker_user_id": str(user.id)}
    payload["attempts"] = int(payload.get("attempts", 0)) + 1
    record.payload = payload
    record.status = "processing"
    await db.commit()
    return {
        "claimed": True,
        "lease_token": token,
        "lease_expires_at": expires.isoformat(),
        "item": {"id": str(record.id), "title": record.title, "platform": payload.get("platform"), "content": payload.get("content"), "metadata": payload.get("metadata")},
    }


async def _leased_record(db: AsyncSession, item_id: UUID, workspace_id: UUID, token: str):
    record = await db.scalar(
        select(CreatorRecord).where(
            CreatorRecord.id == item_id,
            CreatorRecord.workspace_id == workspace_id,
            CreatorRecord.module == "publishing_queue",
        ).with_for_update()
    )
    if record is None:
        raise HTTPException(404, "Queue item not found")
    payload = dict(record.payload or {})
    lease = payload.get("lease") or {}
    if record.status != "processing" or lease.get("token") != token:
        raise HTTPException(409, "Invalid or expired worker lease")
    try:
        expiry = datetime.fromisoformat(lease.get("expires_at", "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(409, "Invalid worker lease")
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(409, "Worker lease expired")
    return record, payload


@router.post("/queue/{item_id}/complete")
async def complete_item(
    item_id: UUID,
    body: QueueResultRequest,
    lease_token: str = Query(min_length=16, max_length=64),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, body.workspace_id)
    record, payload = await _leased_record(db, item_id, body.workspace_id, lease_token)
    payload["provider_result"] = body.result
    payload["lease"] = None
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    record.payload = payload
    record.status = "published"
    await db.commit()
    return {"id": str(record.id), "status": record.status}


@router.post("/queue/{item_id}/fail")
async def fail_item(
    item_id: UUID,
    body: QueueResultRequest,
    lease_token: str = Query(min_length=16, max_length=64),
    retry: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, body.workspace_id)
    record, payload = await _leased_record(db, item_id, body.workspace_id, lease_token)
    error = str(body.result.get("error", "Publishing failed"))[:2000]
    payload["last_error"] = error
    payload["lease"] = None
    payload["failed_at"] = datetime.now(timezone.utc).isoformat()
    record.payload = payload
    record.status = "queued" if retry else "failed"
    await db.commit()
    return {"id": str(record.id), "status": record.status, "last_error": error}


@router.post("/queue/{item_id}/cancel")
async def cancel_item(
    item_id: UUID,
    body: QueueCancelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, body.workspace_id)
    record = await db.scalar(
        select(CreatorRecord).where(
            CreatorRecord.id == item_id,
            CreatorRecord.workspace_id == body.workspace_id,
            CreatorRecord.module == "publishing_queue",
        ).with_for_update()
    )
    if record is None:
        raise HTTPException(404, "Queue item not found")
    if record.status not in {"queued", "failed"}:
        raise HTTPException(409, "Only queued or failed items can be cancelled")
    record.status = "cancelled"
    await db.commit()
    return {"id": str(record.id), "status": record.status}
