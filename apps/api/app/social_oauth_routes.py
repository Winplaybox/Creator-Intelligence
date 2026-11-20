"""Meta OAuth connection foundation for Facebook Pages and Instagram professional accounts."""
import json, secrets
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router=APIRouter(prefix="/v1/social/oauth",tags=["social-oauth"])
META="https://graph.facebook.com/v21.0"
AUTH="https://www.facebook.com/v21.0/dialog/oauth"
SCOPES="pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish"

def redis_client(): return Redis.from_url(settings.redis_url,decode_responses=True)
def token_cipher():
 key=settings.social_token_encryption_key or settings.youtube_token_encryption_key
 if not key: raise HTTPException(503,"Social token encryption key is not configured")
 try: return Fernet(key.encode())
 except Exception as exc: raise HTTPException(503,"Social token encryption key invalid") from exc
async def access(db,user,wid):
 m=await db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.workspace_id==wid))
 if not m: raise HTTPException(403,"Workspace access required")
 return m

@router.get("/{provider}/connect")
async def connect(provider:str,workspace_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
 provider=provider.lower()
 if provider not in {"facebook","instagram"}: raise HTTPException(422,"Supported providers: facebook, instagram")
 if not settings.meta_client_id or not settings.meta_client_secret or not settings.meta_oauth_redirect_uri: raise HTTPException(503,"Meta OAuth configuration missing")
 await access(db,user,workspace_id)
 state=secrets.token_urlsafe(32); redis=redis_client()
 try: await redis.setex("meta_oauth_state:"+state,600,json.dumps({"user_id":str(user.id),"workspace_id":str(workspace_id),"provider":provider}))
 finally: await redis.aclose()
 return RedirectResponse(AUTH+"?"+urlencode({"client_id":settings.meta_client_id,"redirect_uri":settings.meta_oauth_redirect_uri,"state":state,"scope":SCOPES,"response_type":"code"}))

@router.get("/callback")
async def callback(code:str|None=None,state:str|None=None,error:str|None=None,db:AsyncSession=Depends(get_db)):
 if error: return RedirectResponse(settings.web_base_url+"/settings/connections?meta=denied",status_code=303)
 if not code or not state: raise HTTPException(400,"OAuth code/state missing")
 redis=redis_client()
 try: raw=await redis.getdel("meta_oauth_state:"+state)
 finally: await redis.aclose()
 if not raw: raise HTTPException(400,"OAuth state expired or already used")
 p=json.loads(raw); user=await db.get(User,UUID(p["user_id"])); wid=UUID(p["workspace_id"]); provider=p["provider"]
 if not user or not user.is_active: raise HTTPException(401,"Account unavailable")
 await access(db,user,wid)
 try:
  async with httpx.AsyncClient(timeout=15) as client:
   r=await client.get(META+"/oauth/access_token",params={"client_id":settings.meta_client_id,"client_secret":settings.meta_client_secret,"redirect_uri":settings.meta_oauth_redirect_uri,"code":code});r.raise_for_status(); token=r.json()["access_token"]
   long=await client.get(META+"/oauth/access_token",params={"grant_type":"fb_exchange_token","client_id":settings.meta_client_id,"client_secret":settings.meta_client_secret,"fb_exchange_token":token})
   if long.is_success: token_data=long.json(); token=token_data.get("access_token",token)
   else: token_data={}
   accounts=[]
   if provider=="facebook":
    profile=await client.get(META+"/me",params={"fields":"id,name","access_token":token});profile.raise_for_status(); data=profile.json()
    accounts=[{"id":data["id"],"name":data.get("name","Facebook account"),"profile_url":"https://facebook.com/"+data["id"],"token":token}]
   else:
    pages=await client.get(META+"/me/accounts",params={"fields":"id,name,access_token,instagram_business_account","access_token":token});pages.raise_for_status()
    for page in pages.json().get("data",[]):
     ig=page.get("instagram_business_account")
     if ig: accounts.append({"id":ig["id"],"name":page.get("name","Instagram professional account"),"profile_url":"https://instagram.com/"+ig["id"],"token":page.get("access_token") or token,"page_id":page["id"]})
    if not accounts: raise HTTPException(422,"Link an Instagram professional account to a Facebook Page first")
 except HTTPException: raise
 except Exception as exc: raise HTTPException(502,"Meta OAuth failed; verify app setup and permissions") from exc
 enc=token_cipher()
 for a in accounts:
  record=await db.scalar(select(CreatorRecord).where(CreatorRecord.workspace_id==wid,CreatorRecord.module=="social_account",CreatorRecord.payload["platform"].as_string()==provider,CreatorRecord.payload["account_id"].as_string()==a["id"],CreatorRecord.status.in_(["connected","registered"])))
  payload={"platform":provider,"account_id":a["id"],"account_name":a["name"],"profile_url":a["profile_url"],"connection_type":"oauth","credential_status":"connected","token_encrypted":enc.encrypt(a["token"].encode()).decode(),"connected_at":datetime.now(timezone.utc).isoformat(),"token_expires_in":token_data.get("expires_in"),"page_id":a.get("page_id")}
  if record: record.payload={**record.payload,**payload};record.status="connected";record.title=f"{provider}: {a['name']}"
  else: db.add(CreatorRecord(workspace_id=wid,created_by=user.id,module="social_account",title=f"{provider}: {a['name']}",payload=payload,status="connected"))
 await db.commit()
 return RedirectResponse(settings.web_base_url+"/settings/connections?meta=connected",status_code=303)

@router.delete("/{provider}/{record_id}")
async def disconnect(provider:str,record_id:UUID,workspace_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
 provider=provider.lower()
 if provider not in {"facebook","instagram"}: raise HTTPException(422,"Unsupported provider")
 await access(db,user,workspace_id)
 row=await db.scalar(select(CreatorRecord).where(CreatorRecord.id==record_id,CreatorRecord.workspace_id==workspace_id,CreatorRecord.module=="social_account",CreatorRecord.payload["platform"].as_string()==provider))
 if not row: raise HTTPException(404,"Account not found")
 row.payload={k:v for k,v in row.payload.items() if k!="token_encrypted"}
 row.payload.update({"credential_status":"disconnected","disconnected_at":datetime.now(timezone.utc).isoformat()});row.status="registered"
 await db.commit();return {"status":"disconnected"}
