"""Plan catalog, workspace credit balance and metered usage. Payments live in billing_dodo.py."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.config import settings
from app.models import CreatorRecord, Membership, User, WorkspaceSubscription
from app.services import credits

router = APIRouter(prefix="/v1/billing", tags=["billing-usage"])
PLANS = credits.PLANS


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
    return {"plans": [{"name": name, **data, "purchasable": name == "free" or credits.product_id(name, "monthly") != ""}
                      for name, data in PLANS.items()]}


@router.post("/usage", status_code=201)
async def record_usage(body: UsageRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Debits credits for a metered action, exactly once per idempotency key. 402 when the balance is too low."""
    await membership(db, user, body.workspace_id)
    sub = await db.get(WorkspaceSubscription, body.workspace_id)
    await credits.grant_free_monthly(db, body.workspace_id, sub.plan if sub and sub.status == "active" else "free")
    result = await credits.debit(db, body.workspace_id, body.units, f"usage:{body.idempotency_key}",
                                 f"{body.action.strip()}"[:240], user.id)
    if not result["ok"]:
        await db.rollback()
        raise HTTPException(402, {"error": "Insufficient credits", "balance": result["balance"], "required": body.units})
    payload = {"action": body.action.strip(), "units": body.units, "idempotency_key": body.idempotency_key,
        "metadata": body.metadata, "recorded_at": datetime.now(timezone.utc).isoformat(), "actor_user_id": str(user.id)}
    if not result["duplicate"]:
        db.add(CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="usage_ledger",
            title=f"Usage: {body.action.strip()}", payload=payload, status="recorded"))
    await db.commit()
    return {"duplicate": result["duplicate"], "balance": result["balance"], "entry": payload}


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
    sub = await db.get(WorkspaceSubscription, workspace_id)
    plan = sub.plan if sub and sub.status == "active" else "free"
    await credits.grant_free_monthly(db, workspace_id, plan)
    await db.commit()
    return {"workspace_id": str(workspace_id), "plan": plan, "status": sub.status if sub else "active",
            "renews_at": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
            "catalog": PLANS.get(plan), "credits": await credits.balance(db, workspace_id), "configured": sub is not None}


@router.put("/workspace-plan")
async def set_workspace_plan(body: PlanRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Platform-admin override only (comped accounts, support). Customers change plans through checkout."""
    allowed = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    if not user.email_verified or user.email.lower() not in allowed:
        raise HTTPException(403, "Plans are changed through checkout")
    plan = body.plan.strip().lower()
    if plan not in PLANS:
        raise HTTPException(422, "Unknown plan")
    sub = await db.get(WorkspaceSubscription, body.workspace_id, with_for_update=True)
    if sub is None:
        sub = WorkspaceSubscription(workspace_id=body.workspace_id)
        db.add(sub)
    sub.plan, sub.status, sub.updated_at = plan, "active", datetime.now(timezone.utc)
    db.add(CreatorRecord(workspace_id=body.workspace_id, created_by=user.id, module="workspace_plan", title=f"Plan set: {plan}",
        payload={"plan": plan, "changed_at": datetime.now(timezone.utc).isoformat(), "actor_user_id": str(user.id),
                 "source": "platform_admin"}, status="configured"))
    await db.commit()
    return {"workspace_id": str(body.workspace_id), "plan": plan, "configured": True}
