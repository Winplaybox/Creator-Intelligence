"""Opt-in Meta publishing worker; run python -m app.worker."""
import asyncio,logging
from pathlib import Path
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,asc
from app.config import settings
from app.db import SessionLocal
from app.models import CreatorRecord,YouTubeChannel
from app.services.youtube import get_valid_access_token
from app.services.youtube_upload import resumable_upload
from app.services.social_publishing import MetaPublisher,PublishingError
from cryptography.fernet import Fernet
log=logging.getLogger("creator.worker")
MAX_ATTEMPTS=5
CLAIM_TTL=timedelta(minutes=10)
def decrypt_token(v):
 if not settings.social_token_encryption_key:raise PublishingError("Token key not configured")
 return Fernet(settings.social_token_encryption_key.encode()).decrypt(v.encode()).decode()
def is_stale_claim(payload,now=None):
 now=now or datetime.now(timezone.utc)
 raw=(payload or {}).get("worker_claimed_at")
 if not raw:return True
 try:
  claimed=datetime.fromisoformat(raw.replace("Z","+00:00"))
  if claimed.tzinfo is None:claimed=claimed.replace(tzinfo=timezone.utc)
  return now-claimed>CLAIM_TTL
 except (TypeError,ValueError):return True
async def recover_stale_claims(db):
 """Recover abandoned processing rows after worker crash; commits only changed rows."""
 now=datetime.now(timezone.utc)
 rows=(await db.scalars(select(CreatorRecord).where(CreatorRecord.module=="publishing_queue",CreatorRecord.status=="processing").limit(500))).all()
 recovered=0
 for row in rows:
  p=dict(row.payload or {})
  if not is_stale_claim(p,now):continue
  attempts=int(p.get("attempts",0))
  p["recovered_at"]=now.isoformat();p.pop("worker_claimed_at",None)
  p["last_error"]="Worker claim expired; recovered after process interruption"
  if attempts>=MAX_ATTEMPTS:row.status="failed"
  else:
   row.status="queued";row.due_at=now+timedelta(seconds=min(3600,30*2**max(0,attempts-1)))
  row.payload=p;recovered+=1
 if recovered:await db.commit()
 return recovered
async def claim(db):
 now=datetime.now(timezone.utc)
 row=await db.scalar(select(CreatorRecord).where(CreatorRecord.module=="publishing_queue",CreatorRecord.status=="queued",(CreatorRecord.due_at.is_(None))|(CreatorRecord.due_at<=now)).order_by(asc(CreatorRecord.due_at),asc(CreatorRecord.created_at)).with_for_update(skip_locked=True).limit(1))
 if row is None:return None
 p=dict(row.payload or {});p["attempts"]=int(p.get("attempts",0))+1;p["worker_claimed_at"]=now.isoformat();row.payload=p;row.status="processing";await db.commit();return row.id
async def process_one(db,publisher):
 await recover_stale_claims(db)
 item=await claim(db)
 if item is None:return False
 row=await db.get(CreatorRecord,item);p=dict(row.payload or {});c=p.get("content") or {};m=p.get("metadata") or {};platform=str(p.get("platform","")).lower()
 try:
  if platform=="youtube":
   if not settings.youtube_publishing_worker_enabled:
    row.status="queued";p.pop("worker_claimed_at",None);row.payload=p;row.due_at=datetime.now(timezone.utc)+timedelta(minutes=5);await db.commit();return True
   if not bool(m.get("approved") or c.get("approved")):
    row.status="queued";p.pop("worker_claimed_at",None);row.payload=p;row.due_at=datetime.now(timezone.utc)+timedelta(minutes=5);await db.commit();return True
   channel_id=str(m.get("channel_id") or c.get("channel_id") or "")
   if not channel_id:raise PublishingError("YouTube channel_id is required")
   channel=await db.scalar(select(YouTubeChannel).where(YouTubeChannel.workspace_id==row.workspace_id,YouTubeChannel.channel_id==channel_id))
   if not channel:raise PublishingError("Connected YouTube channel not found")
   raw_path=str(c.get("video_path") or m.get("video_path") or "")
   if not raw_path:raise PublishingError("YouTube video_path is required")
   path=Path(raw_path).resolve()
   root=Path(settings.youtube_upload_root).resolve() if settings.youtube_upload_root else None
   if root is None or root not in path.parents:raise PublishingError("Video path must be inside YOUTUBE_UPLOAD_ROOT")
   token=await get_valid_access_token(db,channel)
   upload_metadata={"title":str(c.get("title") or row.title),"description":str(c.get("description") or m.get("description") or ""),"tags":c.get("tags") or m.get("tags") or [],"privacy_status":str(m.get("privacy_status") or "private"),"category_id":str(m.get("category_id") or "22"),"made_for_kids":bool(m.get("made_for_kids",False))}
   result=await resumable_upload(token,str(path),upload_metadata)
   p["provider_result"]={"platform":"youtube","provider_post_id":result["id"],"video_url":f"https://www.youtube.com/watch?v={result['id']}","privacy_status":upload_metadata["privacy_status"]}
  else:
   aid=str(m.get("account_id") or c.get("account_id") or "")
   acc=await db.scalar(select(CreatorRecord).where(CreatorRecord.workspace_id==row.workspace_id,CreatorRecord.module=="social_account",CreatorRecord.status=="connected",CreatorRecord.payload["platform"].as_string()==platform,CreatorRecord.payload["account_id"].as_string()==aid))
   if not acc:raise PublishingError("Connected social account not found")
   token=decrypt_token((acc.payload or {}).get("token_encrypted",""))
   if platform=="facebook":result=await publisher.publish_facebook_page(aid,token,message=str(c.get("text") or c.get("message") or ""),link=c.get("link"))
   elif platform=="instagram" and c.get("type")=="reel":result=await publisher.publish_instagram_reel(aid,token,video_url=str(c.get("video_url","")),caption=str(c.get("caption","")),share_to_feed=bool(c.get("share_to_feed",True)))
   elif platform=="instagram":result=await publisher.publish_instagram_photo(aid,token,image_url=str(c.get("image_url","")),caption=str(c.get("caption","")))
   else:raise PublishingError("Unsupported platform: "+platform)
   p["provider_result"]={"platform":result.platform,"provider_post_id":result.provider_post_id}
  p["published_at"]=datetime.now(timezone.utc).isoformat();p.pop("worker_claimed_at",None);row.status="published"
 except Exception as e:
  n=int(p.get("attempts",1));p["last_error"]=str(e)[:1000];p["failed_at"]=datetime.now(timezone.utc).isoformat();p.pop("worker_claimed_at",None);row.status="failed" if n>=MAX_ATTEMPTS else "queued"
  if row.status=="queued":row.due_at=datetime.now(timezone.utc)+timedelta(seconds=min(3600,30*2**(n-1)))
 row.payload=p;await db.commit();return True
async def run():
 pub=MetaPublisher(settings.meta_graph_version)
 while True:
  if not settings.publishing_worker_enabled:await asyncio.sleep(5);continue
  try:
   async with SessionLocal() as db:worked=await process_one(db,pub)
   if not worked:await asyncio.sleep(settings.publishing_worker_poll_seconds)
  except Exception:log.exception("worker loop error");await asyncio.sleep(5)
if __name__=="__main__":logging.basicConfig(level=logging.INFO);asyncio.run(run())
