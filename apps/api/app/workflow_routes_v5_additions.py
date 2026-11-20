

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
