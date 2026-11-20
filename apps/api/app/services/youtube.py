"""Google OAuth and YouTube API integration with encrypted credential storage."""
from __future__ import annotations
import base64, hashlib, secrets, json
from datetime import datetime, timezone
from typing import Any
from cryptography.fernet import Fernet, InvalidToken
import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import YouTubeChannel

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

def _fernet() -> Fernet:
    key = settings.youtube_token_encryption_key
    if not key:
        raise RuntimeError("YOUTUBE_TOKEN_ENCRYPTION_KEY is required")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError("YOUTUBE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()

def decrypt_token(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Stored YouTube credential cannot be decrypted") from exc

def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge

async def create_oauth_state(redis: Redis, user_id: str, workspace_id: str, verifier: str) -> str:
    state = secrets.token_urlsafe(32)
    await redis.set(f"youtube:oauth:{state}", json.dumps({"user_id":user_id,"workspace_id":workspace_id,"verifier":verifier}), ex=600, nx=True)
    return state

async def consume_oauth_state(redis: Redis, state: str) -> dict[str, str] | None:
    # Redis GETDEL prevents callback replay on supported Redis versions.
    value = await redis.getdel(f"youtube:oauth:{state}")
    return json.loads(value) if value else None

def authorization_url(state: str, challenge: str) -> str:
    from urllib.parse import urlencode
    params = {
      "client_id":settings.google_client_id,
      "redirect_uri":settings.google_youtube_redirect_uri,
      "response_type":"code",
      "scope":"https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly",
      "access_type":"offline","prompt":"consent","include_granted_scopes":"true",
      "state":state,"code_challenge":challenge,"code_challenge_method":"S256"
    }
    return f"{GOOGLE_AUTH}?{urlencode(params)}"

async def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(GOOGLE_TOKEN, data={
            "code":code,"client_id":settings.google_client_id,
            "client_secret":settings.google_client_secret,
            "redirect_uri":settings.google_youtube_redirect_uri,
            "grant_type":"authorization_code","code_verifier":verifier
        })
        response.raise_for_status()
        return response.json()

async def fetch_channel(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{YOUTUBE_API}/channels",params={"part":"snippet,statistics,contentDetails","mine":"true"},headers={"Authorization":f"Bearer {access_token}"})
        response.raise_for_status()
        data=response.json()
    if not data.get("items"):
        raise ValueError("The Google account has no accessible YouTube channel")
    channel=data["items"][0]
    return {"id":channel["id"],"title":channel["snippet"].get("title",""),"description":channel["snippet"].get("description",""),"thumbnail_url":channel["snippet"].get("thumbnails",{}).get("default",{}).get("url"),"subscriber_count":channel.get("statistics",{}).get("subscriberCount"),"video_count":channel.get("statistics",{}).get("videoCount"),"view_count":channel.get("statistics",{}).get("viewCount")}

async def save_channel(db: AsyncSession, user_id, workspace_id, profile: dict[str, Any], token: dict[str, Any]) -> YouTubeChannel:
    existing=await db.scalar(select(YouTubeChannel).where(YouTubeChannel.channel_id==profile["id"]))
    expiry=token.get("expires_in")
    expires_at=datetime.now(timezone.utc)+__import__("datetime").timedelta(seconds=int(expiry)) if expiry else None
    if existing:
        existing.workspace_id=workspace_id
        existing.connected_by=user_id
        existing.title=profile["title"]
        existing.description=profile["description"]
        existing.thumbnail_url=profile["thumbnail_url"]
        existing.access_token_encrypted=encrypt_token(token["access_token"])
        if token.get("refresh_token"): existing.refresh_token_encrypted=encrypt_token(token["refresh_token"])
        existing.token_expires_at=expires_at
        existing.scopes=token.get("scope","").split()
        existing.updated_at=datetime.now(timezone.utc)
        row=existing
    else:
        row=YouTubeChannel(workspace_id=workspace_id,connected_by=user_id,channel_id=profile["id"],title=profile["title"],description=profile["description"],thumbnail_url=profile["thumbnail_url"],access_token_encrypted=encrypt_token(token["access_token"]),refresh_token_encrypted=encrypt_token(token["refresh_token"]) if token.get("refresh_token") else None,token_expires_at=expires_at,scopes=token.get("scope","").split())
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row

async def list_channels(db: AsyncSession, workspace_id) -> list[YouTubeChannel]:
    result=await db.scalars(select(YouTubeChannel).where(YouTubeChannel.workspace_id==workspace_id).order_by(YouTubeChannel.created_at.desc()))
    return list(result)

async def disconnect_channel(db: AsyncSession, workspace_id, channel_id: str) -> bool:
    row=await db.scalar(select(YouTubeChannel).where(YouTubeChannel.workspace_id==workspace_id,YouTubeChannel.channel_id==channel_id))
    if not row: return False
    await db.delete(row); await db.commit(); return True
