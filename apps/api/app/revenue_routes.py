"""Workspace-scoped revenue snapshots and trend analysis (Wave 13)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/revenue", tags=["revenue-intelligence"])


class RevenueSnapshotRequest(BaseModel):
    workspace_id: UUID
    channel_id: str = Field(min_length=3, max_length=64)
    channel_name: str = Field(default="", max_length=240)
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    period_start: datetime
    period_end: datetime
    estimated_revenue: float = Field(ge=0, le=1_000_000_000)
    views: int = Field(default=0, ge=0, le=2_000_000_000)
    monetized_playbacks: int = Field(default=0, ge=0, le=2_000_000_000)
    source: str = Field(default="manual", min_length=1, max_length=32)
    notes: str = Field(default="", max_length=2000)


async def require_membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    membership = await db.scalar(select(Membership).where(
        Membership.user_id == user.id, Membership.workspace_id == workspace_id
    ))
    if membership is None:
        raise HTTPException(403, "Workspace access required")
    return membership


def compute_metrics(body: RevenueSnapshotRequest):
    if body.period_end <= body.period_start:
        raise HTTPException(422, "period_end must be after period_start")
    revenue_per_mille_views = (body.estimated_revenue / body.views * 1000) if body.views else None
    revenue_per_mille_playbacks = (body.estimated_revenue / body.monetized_playbacks * 1000) if body.monetized_playbacks else None
    return {
        "currency": body.currency.upper(),
        "period_start": body.period_start.isoformat(),
        "period_end": body.period_end.isoformat(),
        "estimated_revenue": body.estimated_revenue,
        "views": body.views,
        "monetized_playbacks": body.monetized_playbacks,
        "revenue_per_1000_views": round(revenue_per_mille_views, 4) if revenue_per_mille_views is not None else None,
        "revenue_per_1000_monetized_playbacks": round(revenue_per_mille_playbacks, 4) if revenue_per_mille_playbacks is not None else None,
        "source": body.source.strip(),
        "notes": body.notes.strip(),
        "disclaimer": "Revenue metrics are estimates from user-supplied data; RPM-like ratios are descriptive and are not provider-verified.",
    }


@router.post("/snapshot", status_code=201)
async def save_snapshot(body: RevenueSnapshotRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_membership(db, user, body.workspace_id)
    metrics = compute_metrics(body)
    record = CreatorRecord(
        workspace_id=body.workspace_id,
        created_by=user.id,
        module="revenue_snapshot",
        title=f"Revenue snapshot {body.channel_name.strip() or body.channel_id}",
        payload={"channel_id": body.channel_id, "channel_name": body.channel_name.strip(), "captured_at": datetime.now(timezone.utc).isoformat(), **metrics},
        status="snapshot",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "saved": True, "metrics": metrics}


@router.get("/history")
async def revenue_history(
    workspace_id: UUID,
    channel_id: str | None = Query(default=None, max_length=64),
    currency: str | None = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "revenue_snapshot",
    )
    if channel_id:
        query = query.where(CreatorRecord.payload["channel_id"].as_string() == channel_id)
    if currency:
        query = query.where(CreatorRecord.payload["currency"].as_string() == currency.upper())
    rows = await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {
        "workspace_id": str(workspace_id),
        "snapshots": [
            {"id": str(row.id), "created_at": row.created_at.isoformat(), "payload": row.payload}
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/summary")
async def revenue_summary(
    workspace_id: UUID,
    channel_id: str | None = Query(default=None, max_length=64),
    currency: str = Query(default="USD", min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    limit: int = Query(100, ge=2, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await require_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "revenue_snapshot",
        CreatorRecord.payload["currency"].as_string() == currency.upper(),
    )
    if channel_id:
        query = query.where(CreatorRecord.payload["channel_id"].as_string() == channel_id)
    rows = list(await db.scalars(query.order_by(desc(CreatorRecord.created_at)).limit(limit)))
    if not rows:
        return {"workspace_id": str(workspace_id), "currency": currency.upper(), "count": 0, "latest": None, "previous": None, "revenue_delta": None, "revenue_delta_pct": None}
    latest = rows[0].payload
    previous = rows[1].payload if len(rows) > 1 else None
    delta = latest["estimated_revenue"] - previous["estimated_revenue"] if previous else None
    pct = (delta / previous["estimated_revenue"] * 100) if previous and previous["estimated_revenue"] else None
    return {
        "workspace_id": str(workspace_id),
        "currency": currency.upper(),
        "count": len(rows),
        "latest": latest,
        "previous": previous,
        "revenue_delta": round(delta, 4) if delta is not None else None,
        "revenue_delta_pct": round(pct, 4) if pct is not None else None,
        "note": "Snapshots are ordered by capture time; delta compares the two latest captures, not necessarily adjacent accounting periods.",
    }
