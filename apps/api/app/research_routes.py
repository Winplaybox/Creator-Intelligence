"""Research endpoints using public YouTube Data API and configured AI provider."""
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import current_user
from app.db import get_db
from app.models import User
from app.config import settings
import httpx
router=APIRouter(prefix="/v1/research",tags=["research"])
class AIRequest(BaseModel):
 prompt:str=Field(min_length=8,max_length=8000)
 context:dict=Field(default_factory=dict)
 mode:str=Field(default="ideas",max_length=40)
@router.get("/youtube-search")
async def youtube_search(q:str=Query(min_length=2,max_length=120),limit:int=Query(10,ge=1,le=25),user:User=Depends(current_user)):
 if not settings.google_client_id: raise HTTPException(503,"YouTube search API key is not configured")
 async with httpx.AsyncClient(timeout=20) as client:
  r=await client.get("https://www.googleapis.com/youtube/v3/search",params={"part":"snippet","q":q,"type":"video","maxResults":limit,"key":settings.google_client_id})
 if r.status_code>=400: raise HTTPException(502,"YouTube research provider error")
 return {"query":q,"items":[{"video_id":i.get("id",{}).get("videoId"),"title":i.get("snippet",{}).get("title"),"channel":i.get("snippet",{}).get("channelTitle"),"published_at":i.get("snippet",{}).get("publishedAt"),"description":i.get("snippet",{}).get("description"),"thumbnail":i.get("snippet",{}).get("thumbnails",{}).get("medium",{}).get("url")} for i in r.json().get("items",[])]}
@router.post("/ai")
async def ai_assist(body:AIRequest,user:User=Depends(current_user)):
 if not settings.ai_api_key or not settings.ai_base_url or not settings.ai_model: raise HTTPException(503,"AI provider is not configured")
 payload={"model":settings.ai_model,"messages":[{"role":"system","content":"You are a YouTube creator strategist. Produce useful, specific, non-spammy content advice. Be honest about uncertainty. Return structured headings and actionable bullets where useful."},{"role":"user","content":f"Task mode: {body.mode}\nContext JSON: {body.context}\n\n{body.prompt}"}],"temperature":0.7}
 async with httpx.AsyncClient(timeout=60) as client:
  r=await client.post(settings.ai_base_url.rstrip("/")+"/chat/completions",json=payload,headers={"Authorization":f"Bearer {settings.ai_api_key}"})
 if r.status_code>=400: raise HTTPException(502,"AI provider request failed")
 data=r.json()
 return {"model":data.get("model",settings.ai_model),"content":data.get("choices",[{}])[0].get("message",{}).get("content","")}
