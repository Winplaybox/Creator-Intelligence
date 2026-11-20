"""Google OAuth login using per-user identity and server-side token verification."""
from __future__ import annotations
import json, secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import make_response, slugify
from app.config import settings
from app.db import get_db
from app.models import User, Workspace, Membership, RefreshSession
from app.security import new_refresh_token, hash_refresh_token

router = APIRouter(prefix="/v1/auth/google", tags=["google-oauth"])
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"

def _redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)

@router.get("/start")
async def start_google_login():
    if not settings.google_client_id or not settings.google_oauth_redirect_uri:
        raise HTTPException(503, "Google OAuth is not configured")
    state = secrets.token_urlsafe(32)
    redis = _redis()
    try:
        nonce = secrets.token_urlsafe(24)\n        await redis.set(f"google:oauth:{state}", nonce, ex=600, nx=True)
    finally:
        await redis.aclose()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",\n        "nonce": nonce,
    }
    return RedirectResponse(GOOGLE_AUTH + "?" + urlencode(params), status_code=302)

@router.get("/callback")
async def google_callback(code: str | None = None, state: str | None = None,
                        error: str | None = None, response: Response = None,
                        db: AsyncSession = Depends(get_db)):
    base = settings.web_base_url.rstrip("/")
    if error:
        return RedirectResponse(base + "/login?google=denied", status_code=303)
    if not code or not state:
        raise HTTPException(400, "Missing OAuth code or state")
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_oauth_redirect_uri:
        raise HTTPException(503, "Google OAuth is not configured")
    redis = _redis()
    try:
        consumed = await redis.getdel(f"google:oauth:{state}")
    finally:
        await redis.aclose()
    if not consumed:
        raise HTTPException(400, "OAuth state expired or already used")
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(GOOGLE_TOKEN, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        })
        if token_response.status_code != 200:
            raise HTTPException(401, "Google code exchange failed")
        token_data = token_response.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise HTTPException(401, "Google did not return an ID token")
        verify_response = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
        if verify_response.status_code != 200:
            raise HTTPException(401, "Google ID token validation failed")
        claims = verify_response.json()
    if claims.get("aud") != settings.google_client_id or claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com") or claims.get("nonce") != consumed:
        raise HTTPException(401, "Invalid Google token audience or issuer")
    if claims.get("email_verified") not in (True, "true"):
        raise HTTPException(403, "Google email must be verified")
    email = str(claims.get("email", "")).strip().lower()
    subject = str(claims.get("sub", "")).strip()
    if not email or not subject:
        raise HTTPException(401, "Google identity is incomplete")
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        display_name = str(claims.get("name") or email.split("@")[0])[:120]
        user = User(email=email, password_hash=None, display_name=display_name, email_verified=True)
        workspace = Workspace(name=f"{display_name}'s workspace", slug=slugify(display_name))
        db.add_all([user, workspace])
        await db.flush()
        db.add(Membership(user_id=user.id, workspace_id=workspace.id, role="owner"))
    elif not user.is_active:
        raise HTTPException(403, "Account disabled")
    membership = await db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id).limit(1))
    if membership is None:
        workspace = Workspace(name=f"{user.display_name or email}'s workspace", slug=slugify(user.display_name or email))
        db.add(workspace)
        await db.flush()
        membership = Membership(user_id=user.id, workspace_id=workspace.id, role="owner")
        db.add(membership)
    workspace = await db.get(Workspace, membership.workspace_id)
    refresh_token = new_refresh_token()
    db.add(RefreshSession(user_id=user.id, token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_days)))
    await db.commit()
    response = RedirectResponse(base + "/auth/callback", status_code=303)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", path="/v1/auth", max_age=settings.jwt_refresh_days * 86400)
    access, ttl = __import__("app.security", fromlist=["create_access_token"]).create_access_token(user.id)
    # Access token is delivered via a short-lived one-time Redis ticket, never URL query parameters.
    ticket = secrets.token_urlsafe(32)
    redis = _redis()
    try:
        await redis.set(f"google:ticket:{ticket}", json.dumps({"access_token": access, "expires_in": ttl,
            "user_id": str(user.id), "workspace_id": str(workspace.id)}), ex=60, nx=True)
    finally:
        await redis.aclose()
    response.headers["Location"] = base + "/auth/callback?ticket=" + ticket
    return response

@router.post("/ticket")
async def redeem_ticket(ticket: str, db: AsyncSession = Depends(get_db)):
    redis = _redis()
    try:
        raw = await redis.getdel(f"google:ticket:{ticket}")
    finally:
        await redis.aclose()
    if not raw:
        raise HTTPException(401, "Ticket expired or already used")
    data = json.loads(raw)
    user = await db.get(User, data["user_id"])
    workspace = await db.get(Workspace, data["workspace_id"])
    membership = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace.id))
    if not user or not workspace or not membership or not user.is_active:
        raise HTTPException(401, "Account unavailable")
    return {"access_token": data["access_token"], "expires_in": data["expires_in"],
        "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name},
        "workspace": {"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug, "role": membership.role}}
