"""Allow-listed platform admin operational endpoints."""
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.models import CreatorRecord,Membership,User
router=APIRouter(prefix="/v1/admin",tags=["admin"])
async def guard(user):
 allowed={e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
 # Email must be verified (e.g. via Google); otherwise anyone could register the admin's address.
 if not user.email_verified or user.email.lower() not in allowed:raise HTTPException(403,"Platform administrator access required")
@router.get("/overview")
async def overview(db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 await guard(user);rows=await db.execute(select(CreatorRecord.module,CreatorRecord.status,func.count()).group_by(CreatorRecord.module,CreatorRecord.status))
 return {"users":await db.scalar(select(func.count()).select_from(User)) or 0,"memberships":await db.scalar(select(func.count()).select_from(Membership)) or 0,"records":[{"module":m,"status":s,"count":n} for m,s,n in rows]}
@router.get("/queue")
async def queue(db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 await guard(user);rows=await db.execute(select(CreatorRecord.status,func.count()).where(CreatorRecord.module=="publishing_queue").group_by(CreatorRecord.status))
 return {"queue":[{"status":s,"count":n} for s,n in rows],"worker_enabled":settings.publishing_worker_enabled}
