"""Workspace-scoped trend snapshot persistence and history (Wave 8)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User
from app.trend_scoring import rank_video_signals

router = APIRouter(prefix="/v1/workflows", tags=["trend-history"])


class TrendSnapshotRequest(BaseModel):
    workspace_id: UUID
    region: str = Field(default="IN", min_length=2, max_length=2, pattern="^[A-Za-z]{2}$")
    source: str = Field(default="manual", min_length=1, max_length=32)
    videos: list[dict] = Field(min_length=1, max_length=50)


async def require_trend_membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.workspace_id == workspace_id,
        )
    )
    if membership is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Workspace access required")
    return membership


@router.post("/trend-snapshot", status_code=201)
async def save_trend_snapshot(
    body: TrendSnapshotRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_trend_membership(db, user, body.workspace_id)
    scored = rank_video_signals(body.videos)
    snapshot_at = datetime.now(timezone.utc).isoformat()
    region = body.region.upper()
    payload = {
        "snapshot_at": snapshot_at,
        "region": region,
        "source": body.source.strip(),
        "videos": scored,
        "count": len(scored),
        "disclaimer": "Trend signals are heuristic scores computed from supplied public metrics and timestamps; they are not predictions.",
    }
    record = CreatorRecord(
        workspace_id=body.workspace_id,
        created_by=user.id,
        module="trend_history",
        title=f"Trend snapshot {region} {snapshot_at[:10]}",
        payload=payload,
        status="snapshot",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"snapshot_id": str(record.id), "saved": True, "snapshot": payload}


@router.get("/trend-history")
async def trend_history(
    workspace_id: UUID,
    region: str | None = Query(default=None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_trend_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "trend_history",
    )
    if region:
        query = query.where(CreatorRecord.payload["region"].as_string() == region.upper())
    rows = await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {
        "workspace_id": str(workspace_id),
        "region": region.upper() if region else None,
        "snapshots": [
            {"id": str(row.id), "created_at": row.created_at.isoformat(), "payload": row.payload}
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }
