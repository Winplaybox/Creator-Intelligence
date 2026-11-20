"""YouTube Analytics reports with Redis cache."""
from __future__ import annotations
import json,hashlib
from datetime import date
from typing import Any
import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.youtube_client import YouTubeClient
from app.models import YouTubeChannel

BASE="https://youtubeanalytics.googleapis.com/v2/reports"
class YouTubeAnalyticsError(RuntimeError): pass
class YouTubeAnalytics:
 def __init__(self,channel:YouTubeChannel,db:AsyncSession,redis:Redis|None=None):
  self.channel=channel; self.client=YouTubeClient(channel,db); self.redis=redis or Redis.from_url(settings.redis_url,decode_responses=True)
 async def report(self,params:dict[str,str|int],cache_seconds:int=300)->dict[str,Any]:
  key="ytanalytics:"+hashlib.sha256((self.channel.channel_id+json.dumps(params,sort_keys=True)).encode()).hexdigest()
  cached=await self.redis.get(key)
  if cached: return json.loads(cached)
  token=await self.client.access_token()
  async with httpx.AsyncClient(timeout=30) as client:
   response=await client.get(BASE,params={"ids":"channel==MINE",**params},headers={"Authorization":f"Bearer {token}"})
  if response.status_code==401: raise YouTubeAnalyticsError("Analytics authorization rejected. Reconnect channel.")
  if response.status_code==403: raise YouTubeAnalyticsError("Analytics permission or provider quota denied.")
  if response.status_code>=400: raise YouTubeAnalyticsError(f"YouTube Analytics returned HTTP {response.status_code}")
  data=response.json(); await self.redis.set(key,json.dumps(data),ex=cache_seconds); return data
 async def daily(self,start:date,end:date)->dict[str,Any]:
  return await self.report({"startDate":start.isoformat(),"endDate":end.isoformat(),"metrics":"views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost,likes,comments,shares","dimensions":"day","sort":"day"})
 async def top_videos(self,start:date,end:date,limit:int=10)->dict[str,Any]:
  return await self.report({"startDate":start.isoformat(),"endDate":end.isoformat(),"metrics":"views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares","dimensions":"video","sort":"-views","maxResults":limit})
 async def traffic_sources(self,start:date,end:date)->dict[str,Any]:
  return await self.report({"startDate":start.isoformat(),"endDate":end.isoformat(),"metrics":"views,estimatedMinutesWatched","dimensions":"insightTrafficSourceType","sort":"-views"})
 async def summary(self,start:date,end:date)->dict[str,Any]:
  daily=await self.daily(start,end); videos=await self.top_videos(start,end); traffic=await self.traffic_sources(start,end)
  rows=daily.get("rows",[]); indexes={h["name"]:i for i,h in enumerate(daily.get("columnHeaders",[]))}
  def sum_col(name):
   idx=indexes.get(name); return sum(row[idx] or 0 for row in rows) if idx is not None else 0
  return {"channel_id":self.channel.channel_id,"date_range":{"start":start.isoformat(),"end":end.isoformat()},"totals":{"views":sum_col("views"),"estimated_minutes_watched":sum_col("estimatedMinutesWatched"),"average_view_duration_seconds":sum_col("averageViewDuration"),"subscribers_gained":sum_col("subscribersGained"),"subscribers_lost":sum_col("subscribersLost"),"likes":sum_col("likes"),"comments":sum_col("comments"),"shares":sum_col("shares")},"daily":daily,"top_videos":videos,"traffic_sources":traffic}
 async def close(self): await self.redis.aclose()
