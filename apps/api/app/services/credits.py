"""Workspace plans and the append-only credit ledger (balance = SUM(amount)).

All writes serialise on the workspace's subscription row (SELECT ... FOR UPDATE), so concurrent
debits can never overspend, and the (workspace, kind, reference) unique key makes every grant,
debit and reversal exactly-once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CreditLedgerEntry, WorkspaceSubscription

PLANS = {
    "free": {"monthly_credits": 100, "max_channels": 1, "features": ["basic_research", "trend_scoring"]},
    "creator": {"monthly_credits": 2000, "max_channels": 3, "features": ["research", "analytics", "thumbnail_experiments"]},
    "pro": {"monthly_credits": 10000, "max_channels": 10, "features": ["advanced_analytics", "workflows", "priority_queue"]},
}
INTERVALS = ("monthly", "yearly")


def product_id(plan: str, interval: str) -> str:
    return (getattr(settings, f"dodo_product_{plan}_{interval}", "") or "").strip()


def plan_for_product(pid: str) -> tuple[str, str] | None:
    if not pid:
        return None
    for plan in PLANS:
        for interval in INTERVALS:
            if product_id(plan, interval) == pid:
                return plan, interval
    return None


def credits_for(plan: str, interval: str) -> int:
    monthly = int(PLANS.get(plan, {}).get("monthly_credits", 0))
    return monthly * 12 if interval == "yearly" else monthly


async def lock_workspace(db: AsyncSession, workspace_id: UUID) -> WorkspaceSubscription:
    """Row lock that serialises every balance change for one workspace."""
    await db.execute(insert(WorkspaceSubscription).values(
        workspace_id=workspace_id, plan="free", status="active", updated_at=datetime.now(timezone.utc)
    ).on_conflict_do_nothing(index_elements=["workspace_id"]))
    return await db.scalar(select(WorkspaceSubscription).where(WorkspaceSubscription.workspace_id == workspace_id).with_for_update())


async def balance(db: AsyncSession, workspace_id: UUID) -> int:
    return int(await db.scalar(select(func.coalesce(func.sum(CreditLedgerEntry.amount), 0))
                               .where(CreditLedgerEntry.workspace_id == workspace_id)) or 0)


async def _insert_once(db: AsyncSession, workspace_id: UUID, amount: int, kind: str, reference: str,
                       description: str = "", actor: UUID | None = None) -> bool:
    res = await db.execute(insert(CreditLedgerEntry).values(
        workspace_id=workspace_id, amount=amount, kind=kind, reference=reference[:160], description=description[:240],
        actor_user_id=actor, created_at=datetime.now(timezone.utc),
    ).on_conflict_do_nothing(constraint="uq_credit_ledger_once").returning(CreditLedgerEntry.id))
    return res.scalar() is not None


async def grant(db: AsyncSession, workspace_id: UUID, amount: int, kind: str, reference: str, description: str = "",
                actor: UUID | None = None) -> bool:
    await lock_workspace(db, workspace_id)
    return await _insert_once(db, workspace_id, int(amount), kind, reference, description, actor)


async def grant_free_monthly(db: AsyncSession, workspace_id: UUID, plan: str) -> None:
    if plan != "free":
        return
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    await grant(db, workspace_id, PLANS["free"]["monthly_credits"], "free_monthly", month, f"Free plan credits {month}")


async def debit(db: AsyncSession, workspace_id: UUID, units: int, reference: str, description: str,
                actor: UUID | None) -> dict:
    await lock_workspace(db, workspace_id)
    existing = await db.scalar(select(CreditLedgerEntry).where(
        CreditLedgerEntry.workspace_id == workspace_id, CreditLedgerEntry.kind == "usage",
        CreditLedgerEntry.reference == reference[:160]))
    if existing:
        return {"ok": True, "duplicate": True, "balance": await balance(db, workspace_id)}
    current = await balance(db, workspace_id)
    if current < units:
        return {"ok": False, "duplicate": False, "balance": current}
    await _insert_once(db, workspace_id, -int(units), "usage", reference, description, actor)
    return {"ok": True, "duplicate": False, "balance": current - int(units)}


async def reverse(db: AsyncSession, workspace_id: UUID, granted: int, reference: str, reason: str) -> bool:
    """Claw back a refunded/disputed grant, never below zero."""
    await lock_workspace(db, workspace_id)
    amount = min(int(granted), max(0, await balance(db, workspace_id)))
    return await _insert_once(db, workspace_id, -amount, "payment_reversal", reference, reason)
