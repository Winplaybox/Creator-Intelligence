"""Dodo Payments (merchant of record): hosted checkout + verified, exactly-once webhooks.

Rules:
- Credits/plan change ONLY from a verified `payment.succeeded`, once per payment id.
- `subscription.*` events update plan status; they never grant credits (no double grant).
- Refunds/disputes reverse the payment's grant once. Each webhook-id is processed once.
- The same Dodo account also serves OVD and WinPlayBox Studio, so only events whose metadata
  says app=creator_intelligence are handled here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.models import BillingPayment, BillingWebhookEvent, Membership, User, WorkspaceSubscription
from app.ratelimit import limit
from app.services import credits

log = logging.getLogger("creator.billing")
router = APIRouter(prefix="/v1/billing", tags=["billing"])
APP_TAG = "creator_intelligence"
TOLERANCE_S = 300


class CheckoutRequest(BaseModel):
    workspace_id: UUID
    plan: str = Field(pattern="^(creator|pro)$")
    interval: str = Field(default="monthly", pattern="^(monthly|yearly)$")
    return_path: str = Field(default="/studio?billing=success", max_length=300)


def _base_url() -> str:
    live = settings.dodo_env.lower() == "live" or settings.dodo_api_key.startswith("dodo_live_")
    return "https://live.dodopayments.com" if live else "https://test.dodopayments.com"


@router.post("/checkout")
async def checkout(body: CheckoutRequest, request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(current_user)):
    await limit(request, "checkout", 10, 900, str(user.id))
    m = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == body.workspace_id))
    if m is None or m.role.lower() not in {"owner", "admin"}:
        raise HTTPException(403, "Workspace owner or admin required")
    pid = credits.product_id(body.plan, body.interval)
    if not settings.dodo_api_key or not pid:
        raise HTTPException(503, "This plan is not available for purchase yet")
    path = body.return_path if body.return_path.startswith("/") and not body.return_path.startswith("//") else "/studio"
    payload = {
        "product_cart": [{"product_id": pid, "quantity": 1}],
        "customer": {"email": user.email, "name": user.display_name or user.email},
        "return_url": settings.web_base_url.rstrip("/") + path,
        "metadata": {"app": APP_TAG, "workspace_id": str(body.workspace_id), "plan": body.plan,
                     "interval": body.interval, "ci_user_id": str(user.id)},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{_base_url()}/checkouts", json=payload,
                                  headers={"Authorization": f"Bearer {settings.dodo_api_key}"})
    except httpx.HTTPError:
        raise HTTPException(503, "Payment provider unavailable, please retry")
    if r.status_code not in (200, 201):
        log.warning("dodo checkout failed %s: %s", r.status_code, r.text[:300])
        raise HTTPException(503, "Payment provider unavailable, please retry")
    data = r.json()
    url = data.get("checkout_url") or data.get("payment_link")
    if not url:
        raise HTTPException(503, "Payment provider returned no checkout link")
    return {"checkout_url": url, "session_id": data.get("session_id") or data.get("payment_id")}


def verify_signature(headers, raw: bytes) -> bool:
    secret = settings.dodo_webhook_secret.strip()
    wid, ts, sigs = headers.get("webhook-id", ""), headers.get("webhook-timestamp", ""), headers.get("webhook-signature", "")
    if not (secret and wid and ts.isdigit() and sigs) or abs(time.time() - int(ts)) > TOLERANCE_S:
        return False
    try:
        key = base64.b64decode(secret[6:] if secret.startswith("whsec_") else secret, validate=True)
    except ValueError:
        return False
    expected = base64.b64encode(hmac.new(key, f"{wid}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    return any(v == "v1" and hmac.compare_digest(sig, expected) for v, _, sig in (p.partition(",") for p in sigs.split()))


def _epoch(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _resolve(db: AsyncSession, data: dict, meta: dict) -> tuple[UUID | None, str | None, str]:
    """Workspace + (plan, interval) for an event, from metadata, product id or the stored subscription."""
    ws = None
    if meta.get("workspace_id"):
        try:
            ws = UUID(str(meta["workspace_id"]))
        except ValueError:
            ws = None
    plan, interval = meta.get("plan"), meta.get("interval") or "monthly"
    if plan not in credits.PLANS:
        plan = None
    pid = data.get("product_id") or ((data.get("product_cart") or [{}])[0] or {}).get("product_id")
    found = credits.plan_for_product(pid) if pid else None
    if found:
        plan, interval = found
    sub_id = data.get("subscription_id")
    if (ws is None or plan is None) and sub_id:
        sub = await db.scalar(select(WorkspaceSubscription).where(WorkspaceSubscription.provider_subscription_id == sub_id))
        if sub:
            ws = ws or sub.workspace_id
            plan = plan or sub.plan
    return ws, plan, interval


async def apply_event(db: AsyncSession, event: dict) -> dict:
    kind, data = str(event.get("type") or ""), event.get("data") or {}
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    ours = meta.get("app") == APP_TAG
    if not ours and data.get("subscription_id"):
        ours = bool(await db.scalar(select(WorkspaceSubscription.workspace_id).where(
            WorkspaceSubscription.provider_subscription_id == data["subscription_id"])))
    if not ours and kind.startswith(("refund.", "dispute.")) and data.get("payment_id"):
        ours = bool(await db.get(BillingPayment, data["payment_id"]))
    if not ours:
        return {"ok": True, "action": "ignored_other_app"}

    if kind == "payment.succeeded":
        pay_id = data.get("payment_id")
        ws, plan, interval = await _resolve(db, data, meta)
        if not pay_id or ws is None or plan is None or plan == "free":
            return {"ok": False, "retry": True, "error": "unresolved_payment"}
        if await db.get(BillingPayment, pay_id):
            return {"ok": True, "action": "duplicate_payment"}
        amount = credits.credits_for(plan, interval)
        sub = await credits.lock_workspace(db, ws)
        db.add(BillingPayment(payment_id=pay_id, workspace_id=ws, plan=plan, credits=amount,
                              amount_minor=data.get("total_amount") if isinstance(data.get("total_amount"), int) else None,
                              currency=(data.get("currency") or None), provider_subscription_id=data.get("subscription_id")))
        sub.plan, sub.status, sub.updated_at = plan, "active", datetime.now(timezone.utc)
        if data.get("subscription_id"):
            sub.provider_subscription_id = data["subscription_id"]
        if (data.get("customer") or {}).get("customer_id"):
            sub.provider_customer_id = data["customer"]["customer_id"]
        await credits._insert_once(db, ws, amount, "payment_grant", pay_id, f"{plan} ({interval}) payment")
        return {"ok": True, "action": "granted", "credits": amount}

    if kind in ("refund.succeeded", "dispute.opened", "dispute.lost", "dispute.accepted"):
        pay = await db.get(BillingPayment, data.get("payment_id") or "", with_for_update=True)
        if not pay or pay.status != "granted":
            return {"ok": True, "action": "nothing_to_reverse"}
        pay.status = "refunded" if kind.startswith("refund") else "disputed"
        await credits.reverse(db, pay.workspace_id, pay.credits, pay.payment_id, pay.status)
        sub = await credits.lock_workspace(db, pay.workspace_id)
        if sub.provider_subscription_id in (None, pay.provider_subscription_id):
            sub.plan, sub.status = "free", pay.status
        return {"ok": True, "action": "reversed"}

    if kind.startswith("subscription.") and data.get("subscription_id"):
        ws, plan, _ = await _resolve(db, data, meta)
        if ws is None:
            return {"ok": True, "action": "unknown_subscription"}
        status = kind.split(".", 1)[1]
        sub = await credits.lock_workspace(db, ws)
        if status in ("active", "renewed", "plan_changed", "updated", "unpaused"):
            sub.provider_subscription_id = data["subscription_id"]
            sub.plan, sub.status = plan or sub.plan, "active"
        elif sub.provider_subscription_id == data["subscription_id"]:
            sub.plan, sub.status = "free", status
        sub.current_period_end = _epoch(data.get("next_billing_date")) or sub.current_period_end
        sub.updated_at = datetime.now(timezone.utc)
        return {"ok": True, "action": f"subscription_{status}"}
    return {"ok": True, "action": "ignored_event_type"}


@router.post("/dodo/webhook", include_in_schema=False)
async def dodo_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 1_000_000:
        return JSONResponse({"ok": False}, status_code=413)
    if not verify_signature(request.headers, raw):
        return JSONResponse({"ok": False, "error": "invalid signature"}, status_code=401)
    try:
        event = json.loads(raw)
        assert isinstance(event, dict)
    except (ValueError, AssertionError):
        return JSONResponse({"ok": False}, status_code=400)
    wid = request.headers["webhook-id"][:128]
    claimed = await db.execute(insert(BillingWebhookEvent).values(
        webhook_id=wid, event_type=str(event.get("type") or "")[:64], received_at=datetime.now(timezone.utc)
    ).on_conflict_do_nothing(index_elements=["webhook_id"]).returning(BillingWebhookEvent.webhook_id))
    if claimed.scalar() is None:
        await db.rollback()
        return {"ok": True, "duplicate": True}
    try:
        result = await apply_event(db, event)
    except Exception:
        await db.rollback()
        log.exception("dodo webhook %s failed", wid)
        return JSONResponse({"ok": False}, status_code=500)  # Dodo retries
    if not result.get("ok") and result.get("retry"):
        await db.rollback()  # also forgets the webhook-id claim, so the retry is processed
        return JSONResponse({"ok": False, "error": result.get("error")}, status_code=503)
    ev = await db.get(BillingWebhookEvent, wid)
    ev.result = json.dumps(result)[:500]
    await db.commit()
    return {"ok": True}
