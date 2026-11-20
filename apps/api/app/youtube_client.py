"""Quota-aware YouTube Data API v3 client."""
from __future__ import annotations
from typing import Any
import httpx
from app.services.youtube import decrypt_token
from app.services.youtube_quota import YouTubeQuota,YouTubeQuotaExceeded
from app.models import YouTubeChannel
class YouTubeProviderError(RuntimeError): pass
class YouTubeClient:
 def __init__(self,channel:YouTubeChannel,quota:YouTubeQuota|None=None):
  self.channel=channel
  self.quota=quota or YouTubeQuota()
 async def request(self,endpoint:str,params:dict[str,Any],quota_units:int=1)->dict[str,Any]:
  await self.quota.reserve(quota_units)
  token=decrypt_token(self.channel.access_token_encrypted)
  async with httpx.AsyncClient(timeout=20) as client:
   response=await client.get(f"https://www.googleapis.com/youtube/v3/{endpoint}",params=params,headers={"Authorization":f"Bearer {token}"})
  if response.status_code==401: raise YouTubeProviderError("YouTube access token expired; refresh required")
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
