import re,uuid
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User,Workspace,Membership,RefreshSession
from app.schemas import RegisterRequest,LoginRequest,AuthResponse,UserView,WorkspaceView
from app.security import hash_password,verify_password,create_access_token,decode_access_token,new_refresh_token,hash_refresh_token
from app.config import settings
router=APIRouter(prefix="/v1/auth",tags=["auth"]); bearer=HTTPBearer(auto_error=False)
def slugify(value:str)->str:
 base=re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-") or "workspace"
 return f"{base[:90]}-{uuid.uuid4().hex[:8]}"
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
async def register(body:RegisterRequest,response:Response,db:AsyncSession=Depends(get_db)):
 email=body.email.lower().strip()
 if await db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email already registered")
 user=User(email=email,password_hash=hash_password(body.password),display_name=body.display_name.strip())
 workspace=Workspace(name=body.workspace_name.strip(),slug=slugify(body.workspace_name))
 db.add_all([user,workspace]); await db.flush()
 db.add(Membership(user_id=user.id,workspace_id=workspace.id,role="owner"))
 refresh=new_refresh_token(); db.add(RefreshSession(user_id=user.id,token_hash=hash_refresh_token(refresh),expires_at=datetime.now(timezone.utc)+timedelta(days=settings.jwt_refresh_days)))
 await db.commit()
 response.set_cookie("refresh_token",refresh,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/v1/auth",max_age=settings.jwt_refresh_days*86400)
 return make_response(user,workspace,"owner")
@router.post("/login",response_model=AuthResponse)
async def login(body:LoginRequest,response:Response,db:AsyncSession=Depends(get_db)):
 user=await db.scalar(select(User).where(User.email==body.email.lower().strip()))
 if not user or not user.password_hash or not verify_password(body.password,user.password_hash): raise HTTPException(401,"Invalid email or password")
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
