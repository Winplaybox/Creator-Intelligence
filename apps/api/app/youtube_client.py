"""Quota-aware YouTube Data API v3 client with token refresh."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.youtube import decrypt_token,encrypt_token
from app.services.youtube_quota import YouTubeQuota,YouTubeQuotaExceeded
from app.config import settings
from app.models import YouTubeChannel
class YouTubeProviderError(RuntimeError): pass
class YouTubeClient:
 def __init__(self,channel:YouTubeChannel,db:AsyncSession,quota:YouTubeQuota|None=None):
  self.channel=channel; self.db=db; self.quota=quota or YouTubeQuota()
 async def access_token(self)->str:
  now=datetime.now(timezone.utc)
  if self.channel.token_expires_at and self.channel.token_expires_at>now+timedelta(seconds=60):
   return decrypt_token(self.channel.access_token_encrypted)
  if not self.channel.refresh_token_encrypted: raise YouTubeProviderError("Channel requires reauthorization")
  refresh=decrypt_token(self.channel.refresh_token_encrypted)
  async with httpx.AsyncClient(timeout=20) as client:
   response=await client.post("https://oauth2.googleapis.com/token",data={"client_id":settings.google_client_id,"client_secret":settings.google_client_secret,"refresh_token":refresh,"grant_type":"refresh_token"})
  if response.status_code>=400: raise YouTubeProviderError("Token refresh failed; reconnect channel")
  data=response.json()
  self.channel.access_token_encrypted=encrypt_token(data["access_token"])
  self.channel.token_expires_at=now+timedelta(seconds=int(data.get("expires_in",3600)))
  self.channel.updated_at=now
  await self.db.commit()
  return data["access_token"]
 async def request(self,endpoint:str,params:dict[str,Any],quota_units:int=1)->dict[str,Any]:
  await self.quota.reserve(quota_units)
  token=await self.access_token()
  async with httpx.AsyncClient(timeout=20) as client:
   response=await client.get(f"https://www.googleapis.com/youtube/v3/{endpoint}",params=params,headers={"Authorization":f"Bearer {token}"})
  if response.status_code==401: raise YouTubeProviderError("YouTube authorization rejected; reconnect channel")
  if response.status_code==403:
   body=response.json().get("error",{}).get("errors",[])
   reason=body[0].get("reason") if body else None
   if reason=="quotaExceeded": raise YouTubeQuotaExceeded("Provider quota exhausted")
   raise YouTubeProviderError("YouTube API permission denied")
  if response.status_code>=400: raise YouTubeProviderError(f"YouTube API returned HTTP {response.status_code}")
  return response.json()
 async def channel_overview(self)->dict[str,Any]:
  data=await self.request("channels",{"part":"snippet,statistics,contentDetails","id":self.channel.channel_id},quota_units=1)
  if not data.get("items"): raise YouTubeProviderError("Channel not found")
  item=data["items"][0]
  return {"channel_id":item["id"],"title":item["snippet"].get("title"),"description":item["snippet"].get("description"),"statistics":item.get("statistics",{}),"content_details":item.get("contentDetails",{})}
 async def recent_videos(self,limit:int=25)->dict[str,Any]:
  if not 1<=limit<=50: raise ValueError("limit must be between 1 and 50")
  return await self.request("search",{"part":"snippet","channelId":self.channel.channel_id,"type":"video","order":"date","maxResults":limit},quota_units=100)
 async def playlist_items(self,playlist_id:str,limit:int=50)->dict[str,Any]:
  if not 1<=limit<=50: raise ValueError("limit must be between 1 and 50")
  return await self.request("playlistItems",{"part":"snippet,contentDetails","playlistId":playlist_id,"maxResults":limit},quota_units=1)
