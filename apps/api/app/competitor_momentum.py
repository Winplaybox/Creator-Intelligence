"""Wave 9: competitor snapshot momentum comparison."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import current_user
from app.db import get_db
from app.models import User, Membership, CreatorRecord

router = APIRouter(prefix="/v1/competitors", tags=["competitor-intelligence"])

async def require_workspace(db: AsyncSession, user: User, workspace_id: UUID):
    member = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id))
    if not member:
        raise HTTPException(403, "Workspace access required")

@router.get("/momentum")
async def competitor_momentum(workspace_id: UUID, channel_id: str = Query(min_length=5, max_length=40),
                            db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_workspace(db, user, workspace_id)
    rows = await db.scalars(select(CreatorRecord).where(CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "competitors", CreatorRecord.payload["channel_id"].as_string() == channel_id)
        .order_by(desc(CreatorRecord.created_at)).limit(2))
    snapshots = list(rows)
    if not snapshots:
        return {"channel_id": channel_id, "snapshots_available": 0, "momentum": None,
                "note": "Save at least one competitor snapshot to begin tracking."}
    latest = snapshots[0].payload or {}
    current = (latest.get("channel") or {})
    if len(snapshots) < 2:
        return {"channel_id": channel_id, "snapshots_available": 1, "latest": latest,
                "momentum": None, "note": "A second snapshot is needed to calculate changes."}
    previous = snapshots[1].payload or {}
    old = previous.get("channel") or {}
    def delta(key):
        a, b = current.get(key), old.get(key)
        return None if a is None or b is None else int(a) - int(b)
    return {"channel_id": channel_id, "snapshots_available": 2,
        "latest_snapshot_at": latest.get("snapshot_at"), "previous_snapshot_at": previous.get("snapshot_at"),
        "momentum": {"subscriber_delta": delta("subscriber_count"), "view_delta": delta("views"),
                    "video_delta": delta("video_count")},
        "latest": latest, "previous": previous,
        "note": "Differences between manually captured snapshots; not daily rates unless snapshot intervals are considered."}
