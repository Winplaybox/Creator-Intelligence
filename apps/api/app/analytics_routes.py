"""Workspace-scoped analytics API routes."""
from datetime import date,timedelta
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import current_user
from app.db import get_db
from app.models import User,Membership,YouTubeChannel
from app.services.youtube_analytics import YouTubeAnalytics,YouTubeAnalyticsError
router=APIRouter(prefix="/v1/analytics/youtube",tags=["youtube-analytics"])
async def channel_for(db:AsyncSession,user:User,workspace_id:UUID,channel_id:str):
 member=await db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.workspace_id==workspace_id))
 if not member: raise HTTPException(403,"Workspace membership required")
 channel=await db.scalar(select(YouTubeChannel).where(YouTubeChannel.workspace_id==workspace_id,YouTubeChannel.channel_id==channel_id))
 if not channel: raise HTTPException(404,"Channel not found")
 return channel
def validate_dates(start:date|None,end:date|None):
 end=end or date.today()-timedelta(days=1); start=start or end-timedelta(days=27)
 if end>=date.today(): raise HTTPException(422,"End date must be before today; analytics are not realtime")
 if start>end: raise HTTPException(422,"Start date must not be after end date")
 if (end-start).days>365: raise HTTPException(422,"Date range must be 366 days or less")
 return start,end
async def run_report(method:str,workspace_id:UUID,channel_id:str,start_date:date|None,end_date:date|None,user:User,db:AsyncSession,limit:int=10):
 start,end=validate_dates(start_date,end_date); channel=await channel_for(db,user,workspace_id,channel_id); svc=YouTubeAnalytics(channel,db)
 try:
  if method=="summary": return await svc.summary(start,end)
  if method=="daily": return await svc.daily(start,end)
  if method=="top": return await svc.top_videos(start,end,limit)
  return await svc.traffic_sources(start,end)
 except YouTubeAnalyticsError as exc: raise HTTPException(502,str(exc))
 finally: await svc.close()
@router.get("/summary")
async def summary(workspace_id:UUID,channel_id:str,start_date:date|None=None,end_date:date|None=None,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
 return await run_report("summary",workspace_id,channel_id,start_date,end_date,user,db)
@router.get("/daily")
async def daily(workspace_id:UUID,channel_id:str,start_date:date|None=None,end_date:date|None=None,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
 return await run_report("daily",workspace_id,channel_id,start_date,end_date,user,db)
@router.get("/top-videos")
async def top_videos(workspace_id:UUID,channel_id:str,start_date:date|None=None,end_date:date|None=None,limit:int=Query(10,ge=1,le=50),user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
 return await run_report("top",workspace_id,channel_id,start_date,end_date,user,db,limit)
@router.get("/traffic-sources")
async def traffic_sources(workspace_id:UUID,channel_id:str,start_date:date|None=None,end_date:date|None=None,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
 return await run_report("traffic",workspace_id,channel_id,start_date,end_date,user,db)
