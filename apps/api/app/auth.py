import re,uuid
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User,Workspace,Membership,RefreshSession
import secrets
import httpx
from sqlalchemy.exc import IntegrityError
from app.schemas import RegisterRequest,LoginRequest,AuthResponse,UserView,WorkspaceView,GoogleLoginRequest,UsernameRequest
from app.security import hash_password,verify_password,create_access_token,decode_access_token,new_refresh_token,hash_refresh_token
from app.config import settings
from app.ratelimit import limit
router=APIRouter(prefix="/v1/auth",tags=["auth"]); bearer=HTTPBearer(auto_error=False)
def slugify(value:str)->str:
 base=re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-") or "workspace"
 return f"{base[:90]}-{uuid.uuid4().hex[:8]}"
RESERVED_USERNAMES={"admin","administrator","root","support","help","api","system","billing","security","staff","owner","null","undefined"}
_DUMMY_HASH=hash_password(secrets.token_urlsafe(24))
def _username_base(display_name:str,email:str)->str:
 base=re.sub(r"[^a-z0-9_]+","_",(display_name or "").lower()).strip("_")[:16] or re.sub(r"[^a-z0-9_]+","_",email.split("@")[0].lower()).strip("_")[:16] or "creator"
 if len(base)<3:base=(base+"creator")[:16]
 return base+"_user" if base in RESERVED_USERNAMES else base
async def unique_username(db:AsyncSession,display_name:str,email:str)->str:
 base=_username_base(display_name,email)
 for _ in range(30):
  candidate=f"{base}_{secrets.randbelow(9000)+1000}"
  if not await db.scalar(select(User.id).where(User.username==candidate)):return candidate
 return f"{base}_{secrets.token_hex(4)}"
def _issue_refresh(db:AsyncSession,response:Response,user:User):
 refresh=new_refresh_token(); db.add(RefreshSession(user_id=user.id,token_hash=hash_refresh_token(refresh),expires_at=datetime.now(timezone.utc)+timedelta(days=settings.jwt_refresh_days)))
 response.set_cookie("refresh_token",refresh,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/v1/auth",max_age=settings.jwt_refresh_days*86400)
def make_response(user,workspace,role):
 access,ttl=create_access_token(user.id)
 return AuthResponse(access_token=access,expires_in=ttl,user=UserView.model_validate(user),workspace=WorkspaceView(id=workspace.id,name=workspace.name,slug=workspace.slug,role=role))
async def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:AsyncSession=Depends(get_db)):
 if not credentials: raise HTTPException(401,"Authentication required")
 try: uid=decode_access_token(credentials.credentials)
 except Exception: raise HTTPException(401,"Invalid or expired access token")
 user=await db.get(User,uid)
 if not user or not user.is_active: raise HTTPException(401,"Account unavailable")
 return user
@router.post("/register",response_model=AuthResponse,status_code=201)
async def register(body:RegisterRequest,response:Response,request:Request,db:AsyncSession=Depends(get_db)):
 await limit(request,"register",8,3600)
 email=body.email.lower().strip()
 if await db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email already registered")
 if body.username and (body.username in RESERVED_USERNAMES or await db.scalar(select(User.id).where(User.username==body.username))):raise HTTPException(409,"Username is not available")
 username=body.username or await unique_username(db,body.display_name,email)
 user=User(email=email,username=username,password_hash=hash_password(body.password),display_name=body.display_name.strip())
 workspace=Workspace(name=body.workspace_name.strip(),slug=slugify(body.workspace_name))
 db.add_all([user,workspace]); await db.flush()
 db.add(Membership(user_id=user.id,workspace_id=workspace.id,role="owner"))
 refresh=new_refresh_token(); db.add(RefreshSession(user_id=user.id,token_hash=hash_refresh_token(refresh),expires_at=datetime.now(timezone.utc)+timedelta(days=settings.jwt_refresh_days)))
 await db.commit()
 response.set_cookie("refresh_token",refresh,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/v1/auth",max_age=settings.jwt_refresh_days*86400)
 return make_response(user,workspace,"owner")
@router.post("/login",response_model=AuthResponse)
async def login(body:LoginRequest,response:Response,request:Request,db:AsyncSession=Depends(get_db)):
 name=body.login_name
 await limit(request,"login",20,900); await limit(request,"login-account",10,900,name)
 if len(name)<3: raise HTTPException(422,"Email or username is required")
 user=await db.scalar(select(User).where(User.email==name if "@" in name else User.username==name))
 if not user or not user.password_hash:
  verify_password(body.password,_DUMMY_HASH)  # equalise timing; never reveal which accounts exist
  raise HTTPException(401,"Invalid email/username or password")
 if not verify_password(body.password,user.password_hash): raise HTTPException(401,"Invalid email/username or password")
 if not user.is_active: raise HTTPException(403,"Account disabled")
 membership=await db.scalar(select(Membership).where(Membership.user_id==user.id).order_by(Membership.id).limit(1))
 if not membership: raise HTTPException(403,"No workspace membership")
 workspace=await db.get(Workspace,membership.workspace_id)
 refresh=new_refresh_token(); db.add(RefreshSession(user_id=user.id,token_hash=hash_refresh_token(refresh),expires_at=datetime.now(timezone.utc)+timedelta(days=settings.jwt_refresh_days)))
 await db.commit(); response.set_cookie("refresh_token",refresh,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/v1/auth",max_age=settings.jwt_refresh_days*86400)
 return make_response(user,workspace,membership.role)
@router.post("/refresh",response_model=AuthResponse)
async def refresh(response:Response,request:Request,db:AsyncSession=Depends(get_db)):
 token=request.cookies.get("refresh_token")
 if not token: raise HTTPException(401,"Refresh session required")
 now=datetime.now(timezone.utc); session=await db.scalar(select(RefreshSession).where(RefreshSession.token_hash==hash_refresh_token(token),RefreshSession.revoked_at.is_(None)).with_for_update())
 if not session or session.expires_at<=now:
  if session: session.revoked_at=now; await db.commit()
  response.delete_cookie("refresh_token",path="/v1/auth"); raise HTTPException(401,"Refresh session expired or invalid")
 user=await db.get(User,session.user_id)
 if not user or not user.is_active:
  session.revoked_at=now; await db.commit(); response.delete_cookie("refresh_token",path="/v1/auth"); raise HTTPException(401,"Account unavailable")
 session.revoked_at=now; new_token=new_refresh_token()
 db.add(RefreshSession(user_id=user.id,token_hash=hash_refresh_token(new_token),expires_at=now+timedelta(days=settings.jwt_refresh_days)))
 membership=await db.scalar(select(Membership).where(Membership.user_id==user.id).order_by(Membership.id).limit(1))
 if not membership: await db.commit(); raise HTTPException(403,"No workspace membership")
 workspace=await db.get(Workspace,membership.workspace_id); await db.commit()
 response.set_cookie("refresh_token",new_token,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/v1/auth",max_age=settings.jwt_refresh_days*86400)
 return make_response(user,workspace,membership.role)
@router.post("/logout",status_code=204)
async def logout(response:Response,request:Request,db:AsyncSession=Depends(get_db)):
 token=request.cookies.get("refresh_token")
 if token:
  session=await db.scalar(select(RefreshSession).where(RefreshSession.token_hash==hash_refresh_token(token),RefreshSession.revoked_at.is_(None)))
  if session: session.revoked_at=datetime.now(timezone.utc); await db.commit()
 response.delete_cookie("refresh_token",path="/v1/auth")
@router.get("/me",response_model=UserView)
async def me(user:User=Depends(current_user)): return user

async def verify_google_id_token(credential:str)->dict:
 audiences=settings.google_audiences
 if not audiences: raise HTTPException(503,"Google sign-in is not configured")
 try:
  async with httpx.AsyncClient(timeout=10) as client:
   r=await client.get("https://oauth2.googleapis.com/tokeninfo",params={"id_token":credential})
 except httpx.HTTPError: raise HTTPException(503,"Google sign-in is temporarily unavailable")
 if r.status_code!=200: raise HTTPException(401,"Invalid Google credential")
 data=r.json()
 if data.get("aud") not in audiences or data.get("iss") not in ("accounts.google.com","https://accounts.google.com"): raise HTTPException(401,"Invalid Google credential")
 try: expired=int(data.get("exp",0))<datetime.now(timezone.utc).timestamp()
 except (TypeError,ValueError): expired=True
 if expired or str(data.get("email_verified","")).lower()!="true" or not data.get("email") or not data.get("sub"): raise HTTPException(401,"Google account email is not verified")
 return data
@router.post("/google",response_model=AuthResponse)
async def google_login(body:GoogleLoginRequest,response:Response,request:Request,db:AsyncSession=Depends(get_db)):
 """Sign in or sign up with a Google ID token (audience = our client id, verified email only)."""
 await limit(request,"google",30,900)
 data=await verify_google_id_token(body.credential)
 email=data["email"].lower().strip(); sub=str(data["sub"]); name=(data.get("name") or email.split("@")[0])[:120]
 user=await db.scalar(select(User).where(User.google_sub==sub)) or await db.scalar(select(User).where(User.email==email))
 now=datetime.now(timezone.utc)
 if user:
  if not user.is_active: raise HTTPException(403,"Account disabled")
  if not user.email_verified and user.password_hash:
   # Unverified password account on this email: Google proves ownership, so drop the unproven password
   # and revoke its sessions (prevents an attacker pre-registering someone else's email).
   user.password_hash=None
   for session in await db.scalars(select(RefreshSession).where(RefreshSession.user_id==user.id,RefreshSession.revoked_at.is_(None))): session.revoked_at=now
  user.google_sub=sub; user.email_verified=True
  if not user.username: user.username=await unique_username(db,user.display_name,email)
  membership=await db.scalar(select(Membership).where(Membership.user_id==user.id).order_by(Membership.id).limit(1))
  if membership: workspace=await db.get(Workspace,membership.workspace_id); role=membership.role
  else:
   workspace=Workspace(name=(body.workspace_name or f"{name}'s workspace")[:120],slug=slugify(body.workspace_name or name)); db.add(workspace); await db.flush()
   db.add(Membership(user_id=user.id,workspace_id=workspace.id,role="owner")); role="owner"
 else:
  user=User(email=email,username=await unique_username(db,name,email),google_sub=sub,display_name=name,email_verified=True)
  workspace=Workspace(name=(body.workspace_name or f"{name}'s workspace")[:120],slug=slugify(body.workspace_name or name))
  db.add_all([user,workspace]); await db.flush()
  db.add(Membership(user_id=user.id,workspace_id=workspace.id,role="owner")); role="owner"
 _issue_refresh(db,response,user)
 try: await db.commit()
 except IntegrityError:
  await db.rollback(); raise HTTPException(409,"Account conflict, please try again")
 return make_response(user,workspace,role)
@router.post("/username",response_model=UserView)
async def change_username(body:UsernameRequest,db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 if body.username in RESERVED_USERNAMES: raise HTTPException(409,"Username is not available")
 if await db.scalar(select(User.id).where(User.username==body.username,User.id!=user.id)): raise HTTPException(409,"Username is not available")
 user.username=body.username
 try: await db.commit()
 except IntegrityError:
  await db.rollback(); raise HTTPException(409,"Username is not available")
 return user
@router.get("/config")
async def auth_config():
 aud=settings.google_audiences
 return {"google_client_id":aud[0] if aud else None,"password_min_length":10}
