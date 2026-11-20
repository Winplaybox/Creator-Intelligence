"""Wave 3: competitor snapshots, keyword signals and creator workflow prompts."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import current_user
from app.config import settings
from app.models import User
import httpx

router=APIRouter(prefix="/v1/workflows",tags=["creator-workflows"])

async def yt_get(client,endpoint,params):
    if not settings.youtube_api_key:
        raise HTTPException(503,"YouTube API key is not configured")
    params["key"]=settings.youtube_api_key
    response=await client.get("https://www.googleapis.com/youtube/v3/"+endpoint,params=params)
    if response.status_code>=400:
        raise HTTPException(502,"YouTube provider request failed")
    return response.json()

@router.get("/keyword-research")
async def keyword_research(q:str=Query(min_length=2,max_length=100),region:str=Query("IN",min_length=2,max_length=2),limit:int=Query(15,ge=1,le=25),user:User=Depends(current_user)):
    async with httpx.AsyncClient(timeout=20) as client:
        data=await yt_get(client,"search",{"part":"snippet","q":q,"type":"video","order":"viewCount","regionCode":region.upper(),"maxResults":limit})
        ids=[v.get("id",{}).get("videoId") for v in data.get("items",[]) if v.get("id",{}).get("videoId")]
        stats={}
        if ids:
            details=await yt_get(client,"videos",{"part":"statistics","id":",".join(ids)})
            stats={v["id"]:v.get("statistics",{}) for v in details.get("items",[])}
    results=[]
    for v in data.get("items",[]):
        vid=v.get("id",{}).get("videoId"); sn=v.get("snippet",{}); st=stats.get(vid,{})
        views=int(st.get("viewCount",0)); likes=int(st.get("likeCount",0)); comments=int(st.get("commentCount",0))
        results.append({"video_id":vid,"title":sn.get("title"),"channel":sn.get("channelTitle"),"published_at":sn.get("publishedAt"),"views":views,"likes":likes,"comments":comments,"engagement_pct":round((likes+comments)/views*100,2) if views else 0,"thumbnail":sn.get("thumbnails",{}).get("medium",{}).get("url")})
    return {"query":q,"region":region.upper(),"retrieved_at":datetime.now(timezone.utc).isoformat(),"results":results,"disclaimer":"Search result ordering and public metrics are signals, not guaranteed keyword demand or future performance."}

@router.get("/competitor-channel")
async def competitor_channel(channel_id:str=Query(min_length=5,max_length=40),user:User=Depends(current_user)):
    async with httpx.AsyncClient(timeout=20) as client:
        channels=await yt_get(client,"channels",{"part":"snippet,statistics","id":channel_id})
        if not channels.get("items"): raise HTTPException(404,"Channel not found")
        channel=channels["items"][0]
        videos=await yt_get(client,"search",{"part":"snippet","channelId":channel_id,"type":"video","order":"date","maxResults":10})
    sn=channel.get("snippet",{}); st=channel.get("statistics",{})
    return {"channel_id":channel_id,"snapshot_at":datetime.now(timezone.utc).isoformat(),"channel":{"title":sn.get("title"),"description":sn.get("description"),"thumbnail":sn.get("thumbnails",{}).get("high",{}).get("url"),"subscriber_count":int(st.get("subscriberCount",0)) if not st.get("hiddenSubscriberCount") else None,"views":int(st.get("viewCount",0)),"video_count":int(st.get("videoCount",0))},"recent_videos":[{"video_id":v.get("id",{}).get("videoId"),"title":v.get("snippet",{}).get("title"),"published_at":v.get("snippet",{}).get("publishedAt")} for v in videos.get("items",[])]}

WORKFLOW_MODES={"ideas":"Generate 10 differentiated video ideas with audience, hook, format and source angles.","titles":"Generate 12 accurate, curiosity-driven titles; avoid misleading claims.","short_script":"Create a short-form script with hook, beats, narration, visual cues and CTA.","long_outline":"Create a structured outline with evidence/source needs and retention transitions.","description":"Write a useful video description, chapters if relevant, disclosure reminders and non-spammy CTA.","repurpose":"Repurpose supplied content into a Short, community post and Instagram caption without inventing facts.","localize":"Localize supplied text for the target language and audience; preserve meaning and flag culturally sensitive assumptions.","growth_coach":"Analyze supplied metrics and propose prioritized experiments; distinguish facts from hypotheses."}
class WorkflowRequest(BaseModel):
 mode:str=Field(min_length=2,max_length=40)
 prompt:str=Field(min_length=5,max_length=8000)
 context:dict=Field(default_factory=dict)
@router.post("/ai")
async def workflow_ai(body:WorkflowRequest,user:User=Depends(current_user)):
 if body.mode not in WORKFLOW_MODES: raise HTTPException(400,"Unsupported workflow mode")
 if not settings.ai_api_key or not settings.ai_base_url or not settings.ai_model: raise HTTPException(503,"AI provider is not configured")
 system=WORKFLOW_MODES[body.mode]+" Return concise structured output. Never fabricate analytics, sources, quotes or factual claims; flag verification needs."
 payload={"model":settings.ai_model,"messages":[{"role":"system","content":system},{"role":"user","content":"Context JSON:\n"+str(body.context)+"\n\nTask:\n"+body.prompt}],"temperature":0.65}
 async with httpx.AsyncClient(timeout=60) as client:
  response=await client.post(settings.ai_base_url.rstrip("/")+"/chat/completions",json=payload,headers={"Authorization":"Bearer "+settings.ai_api_key})
 if response.status_code>=400: raise HTTPException(502,"AI provider request failed")
 data=response.json()
 return {"mode":body.mode,"model":data.get("model",settings.ai_model),"content":data.get("choices",[{}])[0].get("message",{}).get("content","")}


# Wave 5: workspace-scoped research persistence and topic gap signals.
from uuid import UUID
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Membership, CreatorRecord

class ContentGapRequest(BaseModel):
    workspace_id: UUID
    topics: list[str] = Field(min_length=1, max_length=10)
    covered_topics: list[str] = Field(default_factory=list, max_length=100)
    region: str = Field(default="IN", min_length=2, max_length=2)

class CompetitorSnapshotRequest(BaseModel):
    workspace_id: UUID
    channel_id: str = Field(min_length=5, max_length=40)

async def require_workspace(db: AsyncSession, user: User, workspace_id: UUID):
    membership = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id))
    if not membership:
        raise HTTPException(403, "Workspace access required")
    return membership


@router.post("/content-gaps")
async def content_gaps(body: ContentGapRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_workspace(db, user, body.workspace_id)
    covered = {x.casefold().strip() for x in body.covered_topics if x.strip()}
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        for topic in body.topics:
            normalized = topic.strip()
            if len(normalized) < 2:
                continue
            data = await yt_get(client, "search", {"part":"snippet", "q":normalized, "type":"video", "order":"viewCount", "regionCode":body.region.upper(), "maxResults":5})
            items = data.get("items", [])
            titles = [i.get("snippet", {}).get("title", "") for i in items]
            overlap = normalized.casefold() in covered
            results.append({"topic":normalized,"covered":overlap,"opportunity":"explore" if not overlap and items else "already_covered" if overlap else "low_data","sample_titles":titles,"result_count":len(items)})
    return {"workspace_id":str(body.workspace_id),"region":body.region.upper(),"topics":results,"note":"Topic coverage is based on user-provided covered topics and public search samples, not a measured market-demand estimate."}

@router.post("/competitor-snapshot", status_code=201)async def save_competitor_snapshot(body: CompetitorSnapshotRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_workspace(db, user, body.workspace_id)
    async with httpx.AsyncClient(timeout=20) as client:
        channels = await yt_get(client, "channels", {"part":"snippet,statistics", "id":body.channel_id})
        if not channels.get("items"):
            raise HTTPException(404, "Channel not found")
        channel = channels["items"][0]
        recent = await yt_get(client, "search", {"part":"snippet", "channelId":body.channel_id, "type":"video", "order":"date", "maxResults":10})
    snippet = channel.get("snippet", {})
    stats = channel.get("statistics", {})
    payload = {"channel_id":body.channel_id,"snapshot_at":datetime.now(timezone.utc).isoformat(),"channel":{"title":snippet.get("title"),"description":snippet.get("description"),"thumbnail":snippet.get("thumbnails",{}).get("high",{}).get("url"),"subscriber_count":int(stats.get("subscriberCount",0)) if not stats.get("hiddenSubscriberCount") else None,"views":int(stats.get("viewCount",0)),"video_count":int(stats.get("videoCount",0))},"recent_videos":[{"video_id":v.get("id",{}).get("videoId"),"title":v.get("snippet",{}).get("title"),"published_at":v.get("snippet",{}).get("publishedAt")} for v in recent.get("items",[])]}
    record = CreatorRecord(workspace_id=body.workspace_id,created_by=user.id,module="competitors",title=snippet.get("title") or body.channel_id,payload=payload,status="snapshot")
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"record_id":str(record.id),"saved":True,"snapshot":payload}
@router.get("/competitor-history")
async def competitor_history(workspace_id: UUID, channel_id: str = Query(min_length=5, max_length=40), limit: int = Query(50, ge=1, le=100), db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_workspace(db, user, workspace_id)
    rows = await db.scalars(select(CreatorRecord).where(CreatorRecord.workspace_id==workspace_id,CreatorRecord.module=="competitors",CreatorRecord.payload["channel_id"].as_string()==channel_id).order_by(desc(CreatorRecord.created_at)).limit(limit))
    return {"channel_id":channel_id,"snapshots":[{"id":str(r.id),"created_at":r.created_at.isoformat(),"payload":r.payload} for r in rows]}


# Wave 6: deterministic content-opportunity prioritization (heuristic, not prediction).
class OpportunityCandidate(BaseModel):
    topic: str = Field(min_length=2, max_length=160)
    trend_score: float = Field(default=0, ge=0, le=100)
    competition: float = Field(default=50, ge=0, le=100, description="User-estimated competition; higher means more crowded")
    audience_fit: float = Field(default=50, ge=0, le=100)
    covered: bool = False
    evidence_count: int = Field(default=0, ge=0, le=10000)

class OpportunityRankRequest(BaseModel):
    workspace_id: UUID
    candidates: list[OpportunityCandidate] = Field(min_length=1, max_length=50)



@router.post("/opportunity-rank")
async def opportunity_rank(body: OpportunityRankRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_workspace(db, user, body.workspace_id)
    ranked = []
    for item in body.candidates:
        # Blend normalized signals; competition is inverse. Coverage is a modest penalty,
        # never an exclusion, so creators can revisit proven subjects.
        coverage_penalty = 12 if item.covered else 0
        score = (item.trend_score * 0.45 + item.audience_fit * 0.35 + (100 - item.competition) * 0.20) - coverage_penalty
        score = round(max(0.0, min(100.0, score)), 2)
        ranked.append({"topic": item.topic.strip(), "score": score,
                     "components": {"trend": item.trend_score, "audience_fit": item.audience_fit,
                                   "competition_opportunity": round(100-item.competition, 2),
                                   "coverage_penalty": coverage_penalty},
                     "evidence_count": item.evidence_count,
                     "recommendation": "prioritize" if score >= 70 else "test" if score >= 45 else "defer"})
    ranked.sort(key=lambda row: row["score"], reverse=True)
    return {"workspace_id": str(body.workspace_id), "ranked_opportunities": ranked,
            "method": {"weights": {"trend": 0.45, "audience_fit": 0.35, "competition_opportunity": 0.20}, "coverage_penalty_points": 12,
                      "note": "Scores are heuristic prioritization aids, not predictions of views or virality. Inputs are user-supplied and evidence_count does not independently validate data."}}
