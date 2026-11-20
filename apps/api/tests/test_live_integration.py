"""End-to-end tests against a real PostgreSQL + Redis (run with INTEGRATION_DATABASE_URL set).

    INTEGRATION_DATABASE_URL=postgresql+asyncpg://... INTEGRATION_REDIS_URL=redis://... pytest tests/test_live_integration.py
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

DB = os.environ.get("INTEGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="INTEGRATION_DATABASE_URL not set")

SECRET_RAW = b"creator-intelligence-test-secret!"
def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture()
def client():
    import httpx
    import app.main as main  # noqa: F401  (settings already loaded with the env above)
    from app.db import engine

    async def make():
        import app.ratelimit as rl
        rl._redis = None  # each test runs on a fresh event loop
        await engine.dispose()
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")
    return make


def _sign(body: bytes, wid=None, ts=None):
    wid = wid or f"msg_{uuid.uuid4().hex}"
    ts = int(time.time()) if ts is None else ts
    sig = base64.b64encode(hmac.new(SECRET_RAW, f"{wid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": str(ts), "webhook-signature": f"v1,{sig}", "content-type": "application/json"}


async def _register(c, email=None, name="Asha Rao"):
    email = email or f"u{uuid.uuid4().hex[:10]}@example.com"
    r = await c.post("/v1/auth/register", json={"email": email, "password": "long-password-123",
                                                "display_name": name, "workspace_name": "WS"})
    assert r.status_code == 201, r.text
    return r.json()


def _google(payload):
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload
    cm = AsyncMock()
    cm.__aenter__.return_value.get = AsyncMock(return_value=resp)
    return patch("app.auth.httpx.AsyncClient", return_value=cm)


def test_username_login_and_generic_errors(client):
    async def t():
        c = await client()
        reg = await _register(c, name="Asha Rao")
        assert reg["user"]["username"].startswith("asha_rao_")
        ok = await c.post("/v1/auth/login", json={"identifier": reg["user"]["username"], "password": "long-password-123"})
        assert ok.status_code == 200
        ok2 = await c.post("/v1/auth/login", json={"email": reg["user"]["email"], "password": "long-password-123"})
        assert ok2.status_code == 200  # legacy body shape still works
        bad = await c.post("/v1/auth/login", json={"identifier": reg["user"]["username"], "password": "nope"})
        missing = await c.post("/v1/auth/login", json={"identifier": "nobody_1234", "password": "nope"})
        assert bad.status_code == missing.status_code == 401
        assert bad.json()["detail"] == missing.json()["detail"]
    run(t())


def test_google_audience_and_account_takeover_defence(client):
    async def t():
        c = await client()
        base = {"iss": "accounts.google.com", "exp": str(int(time.time()) + 600), "email_verified": "true",
                "sub": f"g{uuid.uuid4().hex[:8]}"}
        victim = f"v{uuid.uuid4().hex[:8]}@example.com"
        with _google({**base, "aud": "someone-else", "email": victim}):
            assert (await c.post("/v1/auth/google", json={"credential": "x" * 40})).status_code == 401
        with _google({**base, "aud": "ci-test.apps.googleusercontent.com", "email": victim, "email_verified": "false"}):
            assert (await c.post("/v1/auth/google", json={"credential": "x" * 40})).status_code == 401
        squatter = await _register(c, email=victim)
        with _google({**base, "aud": "ci-test.apps.googleusercontent.com", "email": victim, "name": "Victim"}):
            r = await c.post("/v1/auth/google", json={"credential": "x" * 40})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["id"] == squatter["user"]["id"] and r.json()["user"]["email_verified"] is True
        # the squatter's password no longer works
        assert (await c.post("/v1/auth/login", json={"identifier": victim, "password": "long-password-123"})).status_code == 401
    run(t())


def test_unverified_admin_email_is_not_admin(client):
    async def t():
        c = await client()
        reg = await _register(c, email=f"boss{uuid.uuid4().hex[:4]}@example.com")
        with patch("app.admin_routes.settings.admin_emails", reg["user"]["email"]):
            assert (await c.get("/v1/admin/overview", headers={"Authorization": f"Bearer {reg['access_token']}"})).status_code == 403
        h = {"Authorization": f"Bearer {reg['access_token']}"}
        assert (await c.get("/v1/admin/overview", headers=h)).status_code == 403
        r = await c.put("/v1/billing/workspace-plan", headers=h, json={"workspace_id": reg["workspace"]["id"], "plan": "pro"})
        assert r.status_code == 403  # customers cannot grant themselves a paid plan
    run(t())


def test_usage_debit_is_atomic_and_idempotent(client):
    async def t():
        c = await client()
        reg = await _register(c)
        h, ws = {"Authorization": f"Bearer {reg['access_token']}"}, reg["workspace"]["id"]
        plan = (await c.get(f"/v1/billing/workspace-plan?workspace_id={ws}", headers=h)).json()
        assert plan["plan"] == "free" and plan["credits"] == 100

        async def use(key, units=30):
            return await c.post("/v1/billing/usage", headers=h, json={"workspace_id": ws, "action": "seo_audit",
                                                                     "units": units, "idempotency_key": key})
        results = await asyncio.gather(*[use(f"key-{i}-{uuid.uuid4().hex[:6]}") for i in range(5)])
        assert sorted(r.status_code for r in results) == [201, 201, 201, 402, 402]
        dup_key = f"dup-{uuid.uuid4().hex}"
        await c.post("/v1/billing/usage", headers=h, json={"workspace_id": ws, "action": "xx", "units": 1, "idempotency_key": dup_key})
        again = await c.post("/v1/billing/usage", headers=h, json={"workspace_id": ws, "action": "xx", "units": 1, "idempotency_key": dup_key})
        assert again.status_code == 201, again.text
        assert again.json()["duplicate"] is True and again.json()["balance"] == 9
    run(t())


def test_dodo_webhook_exactly_once_renewal_refund(client):
    async def t():
        c = await client()
        reg = await _register(c)
        h, ws = {"Authorization": f"Bearer {reg['access_token']}"}, reg["workspace"]["id"]
        await c.get(f"/v1/billing/workspace-plan?workspace_id={ws}", headers=h)  # free 100

        async def hook(event, headers=None):
            body = json.dumps(event).encode()
            return await c.post("/v1/billing/dodo/webhook", content=body, headers=headers or _sign(body))

        sub, pay = f"sub_{uuid.uuid4().hex[:10]}", f"pay_{uuid.uuid4().hex[:10]}"
        ev = {"type": "payment.succeeded", "data": {"payment_id": pay, "subscription_id": sub, "total_amount": 99900,
              "currency": "INR", "metadata": {"app": "creator_intelligence", "workspace_id": ws, "plan": "creator",
                                              "interval": "monthly"}}}
        body = json.dumps(ev).encode()
        signed = _sign(body)
        bad = dict(signed, **{"webhook-signature": "v1," + base64.b64encode(b"z" * 32).decode()})
        assert (await hook(ev, bad)).status_code == 401
        assert (await hook(ev, _sign(body, ts=int(time.time()) - 3600))).status_code == 401
        assert (await hook(ev, signed)).status_code == 200
        assert (await hook(ev, signed)).json().get("duplicate") is True
        assert (await hook(ev)).status_code == 200  # new webhook id, same payment: no second grant
        st = (await c.get(f"/v1/billing/workspace-plan?workspace_id={ws}", headers=h)).json()
        assert st["plan"] == "creator" and st["credits"] == 2100
        # subscription.active must not grant again; renewal payment without metadata resolves via subscription id
        assert (await hook({"type": "subscription.active", "data": {"subscription_id": sub, "metadata": {"app": "creator_intelligence",
                "workspace_id": ws, "plan": "creator"}}})).status_code == 200
        assert (await hook({"type": "payment.succeeded", "data": {"payment_id": f"pay_r_{uuid.uuid4().hex[:8]}",
                "subscription_id": sub, "metadata": {}}})).status_code == 200
        st = (await c.get(f"/v1/billing/workspace-plan?workspace_id={ws}", headers=h)).json()
        assert st["credits"] == 4100
        # refund reverses the first payment once
        refund = {"type": "refund.succeeded", "data": {"payment_id": pay, "metadata": {}}}
        await hook(refund)
        await hook(refund)
        st = (await c.get(f"/v1/billing/workspace-plan?workspace_id={ws}", headers=h)).json()
        assert st["credits"] == 2100
        # cancellation downgrades the plan, keeps credits
        await hook({"type": "subscription.cancelled", "data": {"subscription_id": sub, "metadata": {}}})
        st = (await c.get(f"/v1/billing/workspace-plan?workspace_id={ws}", headers=h)).json()
        assert st["plan"] == "free" and st["credits"] >= 2100
        # other apps' events are ignored; unresolvable ones ask Dodo to retry
        assert (await hook({"type": "payment.succeeded", "data": {"payment_id": "pay_ovd", "metadata": {"app": "ovd_editor"}}})).status_code == 200
        unresolved = {"type": "payment.succeeded", "data": {"payment_id": "pay_x", "metadata": {"app": "creator_intelligence"}}}
        assert (await hook(unresolved)).status_code == 503
    run(t())
