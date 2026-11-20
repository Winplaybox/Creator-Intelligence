"""Manual YouTube monetization milestone tracker (Wave 12). Thresholds are configurable."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/monetization", tags=["monetization"])


class YPPMetrics(BaseModel):
    workspace_id: UUID
    channel_id: str = Field(min_length=5, max_length=64)
    channel_name: str = Field(default="", max_length=240)
    subscribers: int = Field(ge=0, le=2_000_000_000)
    public_watch_hours_365d: float = Field(default=0, ge=0, le=100_000_000)
    shorts_views_90d: int = Field(default=0, ge=0, le=2_000_000_000)
    thresholds: dict = Field(default_factory=lambda: {
        "subscribers": 1000,
        "public_watch_hours_365d": 4000,
        "shorts_views_90d": 10_000_000,
    })
    notes: str = Field(default="", max_length=2000)


async def require_membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    membership = await db.scalar(select(Membership).where(
        Membership.user_id == user.id, Membership.workspace_id == workspace_id
    ))
    if membership is None:
        from fastapi import HTTPException
        raise HTTPException(403, "Workspace access required")
    return membership


def evaluate(metrics: YPPMetrics):
    thresholds = metrics.thresholds
    sub_target = int(thresholds.get("subscribers", 1000))
    watch_target = float(thresholds.get("public_watch_hours_365d", 4000))
    shorts_target = int(thresholds.get("shorts_views_90d", 10_000_000))
    subscriber_met = metrics.subscribers >= sub_target
    watch_met = metrics.public_watch_hours_365d >= watch_target
    shorts_met = metrics.shorts_views_90d >= shorts_target
    return {
        "thresholds": {"subscribers": sub_target, "public_watch_hours_365d": watch_target, "shorts_views_90d": shorts_target},
        "criteria": {
            "subscribers": {"current": metrics.subscribers, "target": sub_target, "met": subscriber_met},
            "public_watch_hours_365d": {"current": metrics.public_watch_hours_365d, "target": watch_target, "met": watch_met},
            "shorts_views_90d": {"current": metrics.shorts_views_90d, "target": shorts_target, "met": shorts_met},
        },
        "long_form_path_signal": subscriber_met and watch_met,
        "shorts_path_signal": subscriber_met and shorts_met,
        "note": "Milestone signals only. These metrics and thresholds do not verify YouTube eligibility, policy compliance, account status, or the current official YPP rules.",
    }


@router.post("/ypp/snapshot", status_code=201)
async def save_ypp_snapshot(body: YPPMetrics, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_membership(db, user, body.workspace_id)
    evaluation = evaluate(body)
    snapshot_at = datetime.now(timezone.utc).isoformat()
    payload = {"channel_id": body.channel_id, "channel_name": body.channel_name.strip(),
        "snapshot_at": snapshot_at, "metrics": body.model_dump(exclude={"workspace_id", "notes"}),
        "evaluation": evaluation, "notes": body.notes.strip()}
    record = CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="ypp_tracker",
        title=f"YPP snapshot {body.channel_name or body.channel_id}", payload=payload, status="snapshot")
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "saved": True, "evaluation": evaluation, "snapshot_at": snapshot_at}


@router.get("/ypp/history")
async def ypp_history(workspace_id: UUID, channel_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "ypp_tracker")
    if channel_id:
        query = query.where(CreatorRecord.payload["channel_id"].as_string() == channel_id)
    rows = await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {"workspace_id": str(workspace_id), "snapshots": [
        {"id": str(row.id), "created_at": row.created_at.isoformat(), "payload": row.payload} for row in rows
    ], "limit": limit, "offset": offset}
