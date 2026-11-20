"""Thumbnail experiment tracking (Wave 11); metrics are supplied by the creator."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/thumbnail-experiments", tags=["thumbnail-experiments"])


class Variant(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    asset_url: str | None = Field(default=None, max_length=2048)
    hypothesis: str = Field(default="", max_length=1000)


class ExperimentCreate(BaseModel):
    workspace_id: UUID
    title: str = Field(min_length=3, max_length=240)
    video_id: str | None = Field(default=None, max_length=64)
    variants: list[Variant] = Field(min_length=2, max_length=5)


class VariantMetrics(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    impressions: int = Field(ge=0, le=2_000_000_000)
    clicks: int = Field(ge=0, le=2_000_000_000)
    views: int = Field(default=0, ge=0, le=2_000_000_000)


class ExperimentResultsRequest(BaseModel):
    workspace_id: UUID
    metrics: list[VariantMetrics] = Field(min_length=2, max_length=5)


async def membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    row = await db.scalar(select(Membership).where(
        Membership.user_id == user.id, Membership.workspace_id == workspace_id
    ))
    if row is None:
        raise HTTPException(403, "Workspace access required")
    return row


@router.post("", status_code=201)
async def create_experiment(body: ExperimentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, body.workspace_id)
    labels = [variant.label.strip().casefold() for variant in body.variants]
    if any(not label for label in labels) or len(set(labels)) != len(labels):
        raise HTTPException(422, "Variant labels must be non-empty and unique")
    payload = {
        "video_id": body.video_id,
        "variants": [variant.model_dump() for variant in body.variants],
        "metrics": [],
        "winner": None,
        "status": "active",
    }
    record = CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="thumbnail_experiment",
                          title=body.title.strip(), payload=payload, status="active")
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "status": record.status, "title": record.title, "payload": record.payload}


@router.get("")
async def list_experiments(workspace_id: UUID, status: str | None = Query(default=None, max_length=20),
                           limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                           db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "thumbnail_experiment",
    )
    if status:
        query = query.where(CreatorRecord.status == status)
    rows = await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {"workspace_id": str(workspace_id), "experiments": [
        {"id": str(row.id), "title": row.title, "status": row.status, "payload": row.payload,
         "created_at": row.created_at.isoformat()} for row in rows
    ], "limit": limit, "offset": offset}


@router.post("/{experiment_id}/metrics")
async def record_metrics(experiment_id: UUID, body: ExperimentResultsRequest,
                        db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, body.workspace_id)
    record = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.id == experiment_id,
        CreatorRecord.workspace_id == body.workspace_id,
        CreatorRecord.module == "thumbnail_experiment",
    ).with_for_update())
    if record is None:
        raise HTTPException(404, "Experiment not found")
    payload = dict(record.payload or {})
    if record.status != "active":
        raise HTTPException(409, "Metrics can only be recorded for active experiments")
    expected = {v["label"].strip().casefold() for v in payload.get("variants", [])}
    actual = [m.label.strip().casefold() for m in body.metrics]
    if set(actual) != expected or len(actual) != len(expected):
        raise HTTPException(422, "Metrics must include exactly one entry for each experiment variant")
    normalized = []
    for metric in body.metrics:
        ctr = round(metric.clicks / metric.impressions * 100, 4) if metric.impressions else None
        normalized.append({**metric.model_dump(), "ctr_pct": ctr})
    enough_data = all(item["impressions"] >= 100 for item in normalized)
    winner = None
    if enough_data:
        winner = max(normalized, key=lambda item: item["ctr_pct"] if item["ctr_pct"] is not None else -1)["label"]
    payload["metrics"] = normalized
    payload["winner"] = winner
    payload["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    payload["evaluation_note"] = "CTR comparison is descriptive. A minimum of 100 impressions per variant is a low-data guardrail, not statistical significance."
    record.payload = payload
    await db.commit()
    return {"id": str(record.id), "winner": winner, "sufficient_sample": enough_data, "metrics": normalized,
            "note": payload["evaluation_note"]}


@router.post("/{experiment_id}/close")
async def close_experiment(experiment_id: UUID, workspace_id: UUID, db: AsyncSession = Depends(get_db),
                          user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    record = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.id == experiment_id,
        CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "thumbnail_experiment",
    ).with_for_update())
    if record is None:
        raise HTTPException(404, "Experiment not found")
    if record.status != "active":
        raise HTTPException(409, "Experiment is already closed")
    record.status = "closed"
    payload = dict(record.payload or {})
    payload["closed_at"] = datetime.now(timezone.utc).isoformat()
    record.payload = payload
    await db.commit()
    return {"id": str(record.id), "status": record.status, "winner": payload.get("winner")}
