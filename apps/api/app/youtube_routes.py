"""Workspace-scoped YouTube channel connection endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.auth import current_user
from app.models import User, Membership, YouTubeChannel
from app.config import settings
from app.services.youtube import pkce_pair, create_oauth_state, consume_oauth_state, authorization_url, exchange_code, fetch_channel, save_channel, list_channels, disconnect_channel

router=APIRouter(prefix="/v1/youtube",tags=["youtube"])
def redis_client() -> Redis:
    return Redis.from_url(settings.redis_url,decode_responses=True)
async def membership(db:AsyncSession,user:User,workspace_id:UUID):
    row=await db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.workspace_id==workspace_id))
    if not row: raise HTTPException(403,"Workspace membership required")
    return row

@router.get("/connect")
async def connect(workspace_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    await membership(db,user,workspace_id)
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_youtube_redirect_uri:
        raise HTTPException(503,"YouTube OAuth is not configured")
    redis=redis_client()
    try:
        verifier,challenge=pkce_pair()
        state=await create_oauth_state(redis,str(user.id),str(workspace_id),verifier)
        return RedirectResponse(authorization_url(state,challenge),status_code=302)
    finally:
        await redis.aclose()

@router.get("/callback")
async def callback(request:Request,code:str|None=None,state:str|None=None,error:str|None=None,db:AsyncSession=Depends(get_db)):
    if error: return RedirectResponse(f"{settings.web_base_url}/settings/connections?youtube=denied",status_code=303)
    if not code or not state: raise HTTPException(400,"Missing OAuth code or state")
    redis=redis_client()
    try:
        payload=await consume_oauth_state(redis,state)
    finally:
        await redis.aclose()
    if not payload: raise HTTPException(400,"OAuth state expired or already used")
    user=await db.get(User,UUID(payload["user_id"]))
    workspace_id=UUID(payload["workspace_id"])
    if not user or not user.is_active: raise HTTPException(401,"Account unavailable")
    await membership(db,user,workspace_id)
    try:
        token=await exchange_code(code,payload["verifier"])
        profile=await fetch_channel(token["access_token"])
        row=await save_channel(db,user.id,workspace_id,profile,token)
    except Exception as exc:
        # Do not leak provider response bodies or tokens into logs.
        raise HTTPException(502,"YouTube connection failed. Please retry.") from exc
    return RedirectResponse(f"{settings.web_base_url}/settings/connections?youtube=connected&channel={row.channel_id}",status_code=303)

@router.get("/channels")
async def channels(workspace_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    await membership(db,user,workspace_id)
    rows=await list_channels(db,workspace_id)
    return [{"channel_id":r.channel_id,"title":r.title,"description":r.description,"thumbnail_url":r.thumbnail_url,"connected_at":r.created_at,"token_expires_at":r.token_expires_at} for r in rows]

@router.delete("/channels/{channel_id}",status_code=204)
async def disconnect(channel_id:str,workspace_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    await membership(db,user,workspace_id)
    if not await disconnect_channel(db,workspace_id,channel_id): raise HTTPException(404,"Channel not found")
