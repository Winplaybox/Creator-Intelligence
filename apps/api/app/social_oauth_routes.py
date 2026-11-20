"""Workspace-scoped Meta OAuth connection endpoints (Wave 24).

Tokens are encrypted before persistence and are never returned by these routes.
OAuth state is single-use and stored in Redis with a short expiry.
"""
from __future__ import annotations
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID
import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/social/oauth", tags=["social-oauth"])
PROVIDERS = {"facebook", "instagram"}
META_BASE = "https://graph.facebook.com"

def _fernet() -> Fernet:
    key = settings.social_token_encryption_key or settings.youtube_token_encryption_key
    if not key:
        raise RuntimeError("SOCIAL_TOKEN_ENCRYPTION_KEY is required")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError("Social token encryption key is invalid") from exc

def _encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()

async def _membership(db: AsyncSession, user: User, workspace_id: UUID):
    row = await db.scalar(select(Membership).where(
        Membership.user_id == user.id, Membership.workspace_id == workspace_id
    ))
    if row is None:
        raise HTTPException(403, "Workspace access required")
    return row

def _redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)

def _meta_version() -> str:
    return settings.meta_graph_version.strip()

@router.get("/{provider}/connect")
async def connect(provider: str, workspace_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unsupported social provider")
    if not settings.meta_client_id or not settings.meta_client_secret or not settings.meta_oauth_redirect_uri:
        raise HTTPException(503, "Meta OAuth is not configured")
    try:
        _fernet()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    await _membership(db, user, workspace_id)
    state = secrets.token_urlsafe(32)
    scopes = ["pages_show_list", "pages_read_engagement", "pages_manage_posts", "business_management"]
    if provider == "instagram":
        scopes.extend(["instagram_basic", "instagram_content_publish"])
    redis = _redis()
    try:
        await redis.set(f"meta:oauth:{state}", json.dumps({
            "user_id": str(user.id), "workspace_id": str(workspace_id), "provider": provider
        }), ex=600, nx=True)
    finally:
        await redis.aclose()
    params = {
        "client_id": settings.meta_client_id, "redirect_uri": settings.meta_oauth_redirect_uri,
        "response_type": "code", "state": state, "scope": ",".join(scopes),
    }
    return RedirectResponse("https://www.facebook.com/" + _meta_version() + "/dialog/oauth?" + urlencode(params), status_code=302)

@router.get("/callback")
async def callback(code: str | None = None, state: str | None = None, error: str | None = None,
                  db: AsyncSession = Depends(get_db)):
    base = settings.web_base_url.rstrip("/") + "/settings/connections"
    if error:
        return RedirectResponse(base + "?meta=denied", status_code=303)
    if not code or not state:
        raise HTTPException(400, "Missing OAuth code or state")
    redis = _redis()
    try:
        raw = await redis.getdel(f"meta:oauth:{state}")
    finally:
        await redis.aclose()
    if not raw:
        raise HTTPException(400, "OAuth state expired or already used")
    try:
        context = json.loads(raw)
        user_id, workspace_id, provider = UUID(context["user_id"]), UUID(context["workspace_id"]), context["provider"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid OAuth state")
    if provider not in PROVIDERS:
        raise HTTPException(400, "Invalid OAuth provider")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Account unavailable")
    await _membership(db, user, workspace_id)
    version = _meta_version()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.get(f"{META_BASE}/{version}/oauth/access_token", params={
                "client_id": settings.meta_client_id, "client_secret": settings.meta_client_secret,
                "redirect_uri": settings.meta_oauth_redirect_uri, "code": code,
            })
            token_response.raise_for_status()
            token_data = token_response.json()
            short_token = token_data["access_token"]
            long_response = await client.get(f"{META_BASE}/{version}/oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": settings.meta_client_id,
                "client_secret": settings.meta_client_secret, "fb_exchange_token": short_token,
            })
            long_response.raise_for_status()
            token_data = long_response.json()
            token = token_data["access_token"]
            profile_response = await client.get(f"{META_BASE}/{version}/me", params={"fields":"id,name","access_token":token})
            profile_response.raise_for_status()
            profile = profile_response.json()
            pages_response = await client.get(f"{META_BASE}/{version}/me/accounts", params={
                "fields":"id,name,access_token,instagram_business_account{id,username}",
                "access_token":token,
            })
            pages_response.raise_for_status()
            pages = pages_response.json().get("data", [])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, "Meta OAuth exchange failed") from exc
    expires_in = int(token_data.get("expires_in", 0) or 0)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
    account_rows = []
    for page in pages:
        page_token = page.get("access_token") or token
        page_record = {
            "provider": "facebook", "account_id": str(page.get("id", "")),
            "account_name": page.get("name", ""), "profile_url": None,
            "token_encrypted": _encrypt(page_token), "token_expires_at": expires_at.isoformat() if expires_at else None,
            "connected_by": str(user.id), "connection_type": "oauth", "meta_user_id": profile.get("id"),
        }
        if page_record["account_id"]:
            account_rows.append(page_record)
        ig = page.get("instagram_business_account")
        if provider == "instagram" and isinstance(ig, dict) and ig.get("id"):
            account_rows.append({
                "provider": "instagram", "account_id": str(ig["id"]),
                "account_name": ig.get("username") or page.get("name", ""),
                "profile_url": None, "token_encrypted": _encrypt(page_token),
                "token_expires_at": expires_at.isoformat() if expires_at else None,
                "connected_by": str(user.id), "connection_type": "oauth",
                "facebook_page_id": str(page.get("id", "")),
            })
    if not account_rows:
        raise HTTPException(422, "No Facebook Page or Instagram Business account was found for this Meta login")
    for account in account_rows:
        existing = await db.scalar(select(CreatorRecord).where(
            CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "social_account",
            CreatorRecord.payload["platform"].as_string() == account["provider"],
            CreatorRecord.payload["account_id"].as_string() == account["account_id"],
            CreatorRecord.status == "connected",
        ))
        if existing:
            existing.payload = {**(existing.payload or {}), **account}
            existing.status = "connected"
            existing.title = f"{account['provider']}: {account['account_name'] or account['account_id']}"
        else:
            db.add(CreatorRecord(workspace_id=workspace_id, created_by=user.id, module="social_account",
                title=f"{account['provider']}: {account['account_name'] or account['account_id']}",
                payload=account, status="connected"))
    await db.commit()
    return RedirectResponse(base + "?meta=connected", status_code=303)

@router.delete("/{provider}/{record_id}", status_code=204)
async def disconnect(provider: str, record_id: UUID, workspace_id: UUID = Query(...),
                    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unsupported social provider")
    await _membership(db, user, workspace_id)
    record = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.id == record_id, CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "social_account",
        CreatorRecord.payload["platform"].as_string() == provider,
    ))
    if record is None:
        raise HTTPException(404, "Social account connection not found")
    payload = dict(record.payload or {})
    payload.pop("token_encrypted", None)
    payload.pop("token_expires_at", None)
    payload["credential_status"] = "revoked"
    record.payload = payload
    record.status = "removed"
    await db.commit()
