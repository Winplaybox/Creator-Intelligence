"""Plan catalog and workspace usage ledger foundation (Wave 17). No payment processing."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/billing", tags=["billing-usage"])
PLANS = {
    "free": {"monthly_credits": 100, "max_channels": 1, "features": ["basic_research", "trend_scoring"]},
    "creator": {"monthly_credits": 2000, "max_channels": 3, "features": ["research", "analytics", "thumbnail_experiments"]},
    "pro": {"monthly_credits": 10000, "max_channels": 10, "features": ["advanced_analytics", "workflows", "priority_queue"]},
}


class UsageRequest(BaseModel):
    workspace_id: UUID
    action: str = Field(min_length=2, max_length=80)
    units: int = Field(ge=1, le=1_000_000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    metadata: dict = Field(default_factory=dict)


class PlanRequest(BaseModel):
    workspace_id: UUID
    plan: str = Field(min_length=2, max_length=32)


async def membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    row = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id))
    if row is None:
        raise HTTPException(403, "Workspace access required")
    return row


@router.get("/plans")
async def list_plans():
    return {"plans": [{"name": name, **data} for name, data in PLANS.items()],
            "note": "Catalog placeholders; not purchasable until payment and entitlement enforcement are implemented."}


@router.post("/usage", status_code=201)
async def record_usage(body: UsageRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    member = await membership(db, user, body.workspace_id)
    if member.role.lower() not in {"owner", "admin"}:
        raise HTTPException(403, "Workspace owner or admin required to record usage")
    existing = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.workspace_id == body.workspace_id, CreatorRecord.module == "usage_ledger",
        CreatorRecord.payload["idempotency_key"].as_string() == body.idempotency_key
    ))
    if existing:
        return {"id": str(existing.id), "duplicate": True, "entry": existing.payload}
    payload = {"action": body.action.strip(), "units": body.units, "idempotency_key": body.idempotency_key,
        "metadata": body.metadata, "recorded_at": datetime.now(timezone.utc).isoformat(), "actor_user_id": str(user.id)}
    record = CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="usage_ledger",
        title=f"Usage: {body.action.strip()}", payload=payload, status="recorded")
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "duplicate": False, "entry": payload}


@router.get("/usage")
async def usage_summary(workspace_id: UUID, action: str | None = Query(default=None, max_length=80),
    limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    query = select(CreatorRecord).where(CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "usage_ledger")
    if action:
        query = query.where(CreatorRecord.payload["action"].as_string() == action)
    rows = list(await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit)))
    return {"workspace_id": str(workspace_id), "entries": [
        {"id": str(row.id), "payload": row.payload, "created_at": row.created_at.isoformat()} for row in rows
    ], "total_units_in_page": sum(int(row.payload.get("units", 0)) for row in rows), "limit": limit, "offset": offset}


@router.get("/workspace-plan")
async def workspace_plan(workspace_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await membership(db, user, workspace_id)
    record = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "workspace_plan"
    ).order_by(desc(CreatorRecord.created_at)).limit(1))
    if record is None:
        return {"workspace_id": str(workspace_id), "plan": "free", "catalog": PLANS["free"], "configured": False}
    plan = record.payload.get("plan", "free")
    return {"workspace_id": str(workspace_id), "plan": plan, "catalog": PLANS.get(plan), "configured": True}


@router.put("/workspace-plan")
async def set_workspace_plan(body: PlanRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    member = await membership(db, user, body.workspace_id)
    if member.role.lower() != "owner":
        raise HTTPException(403, "Workspace owner required")
    plan = body.plan.strip().lower()
    if plan not in PLANS:
        raise HTTPException(422, "Unknown plan")
    record = CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="workspace_plan",
        title=f"Plan set: {plan}", payload={"plan": plan, "changed_at": datetime.now(timezone.utc).isoformat(),
        "actor_user_id": str(user.id), "source": "manual_admin"}, status="configured")
    db.add(record)
    await db.commit()
    return {"workspace_id": str(body.workspace_id), "plan": plan, "configured": True,
            "note": "Manual plan configuration only; no payment, subscription renewal, or feature gating is wired."}
