"""Wave 2 creator research intelligence: trend signals and metadata scoring."""
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import current_user
from app.config import settings
from app.models import User
import httpx

router = APIRouter(prefix="/v1/intelligence", tags=["intelligence"])

class SEOAuditInput(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    is_short: bool = True

def score_metadata(data: SEOAuditInput) -> dict[str, Any]:
    title = data.title.strip()
    desc = data.description.strip()
    tags = [t.strip() for t in data.tags if t.strip()]
    checks = []
    checks.append({"key":"title_length","label":"Title length","score":20 if 35 <= len(title) <= 70 else (12 if 20 <= len(title) <= 90 else 4),"max":20,"detail":f"{len(title)} characters; aim for 35–70 characters."})
    checks.append({"key":"keyword_in_title","label":"Clear topic in title","score":15 if title and any(w.lower() in title.lower() for w in desc.split()[:8] if len(w)>3) else 8,"max":15,"detail":"Use the main topic naturally in both title and description."})
    checks.append({"key":"description","label":"Description depth","score":20 if len(desc)>=250 else (12 if len(desc)>=100 else 5),"max":20,"detail":f"{len(desc)} characters; add context, value and a clear next step."})
    checks.append({"key":"tags","label":"Tag coverage","score":15 if len(tags)>=8 else (10 if len(tags)>=4 else 4),"max":15,"detail":f"{len(tags)} tags provided; use relevant variations, not unrelated tags."})
    checks.append({"key":"readability","label":"Readability","score":15 if title and desc and not title.isupper() else 8,"max":15,"detail":"Avoid all-caps and keyword stuffing."})
    checks.append({"key":"short_format","label":"Short-form packaging","score":15 if data.is_short and ("#shorts" in desc.lower() or len(title)<=70) else 10,"max":15,"detail":"Make the opening promise specific and easy to understand quickly."})
    total=sum(c["score"] for c in checks)
    return {"score":total,"max_score":100,"grade":"strong" if total>=80 else "improve" if total>=60 else "needs_work","checks":checks,"disclaimer":"Heuristic audit only. Scores do not predict ranking or views."}

@router.post("/seo-audit")
async def seo_audit(body: SEOAuditInput, user: User = Depends(current_user)):
    return score_metadata(body)

@router.get("/trending")
async def trending(region: str = Query("IN", min_length=2, max_length=2), category_id: str | None = Query(None, max_length=20), limit: int = Query(20, ge=1, le=50), user: User = Depends(current_user)):
    if not settings.youtube_api_key:
        raise HTTPException(503, "YouTube search API key is not configured")
    params={"part":"snippet,statistics","chart":"mostPopular","regionCode":region.upper(),"maxResults":limit,"key":settings.youtube_api_key}
    if category_id: params["videoCategoryId"]=category_id
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.get("https://www.googleapis.com/youtube/v3/videos",params=params)
    if r.status_code>=400: raise HTTPException(502,"YouTube trending provider error")
    items=[]
    for item in r.json().get("items",[]):
        sn=item.get("snippet",{}); stats=item.get("statistics",{})
        views=int(stats.get("viewCount",0))
        likes=int(stats.get("likeCount",0))
        comments=int(stats.get("commentCount",0))
        items.append({"video_id":item.get("id"),"title":sn.get("title"),"channel":sn.get("channelTitle"),"published_at":sn.get("publishedAt"),"views":views,"likes":likes,"comments":comments,"engagement_rate":round((likes+comments)/views*100,3) if views else 0,"thumbnail":sn.get("thumbnails",{}).get("high",{}).get("url")})
    return {"region":region.upper(),"category_id":category_id,"fetched_at":datetime.now(timezone.utc).isoformat(),"items":items,"note":"Trending list is a provider snapshot; it is not personalized and may change."}
