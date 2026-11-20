from datetime import datetime,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select,desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.auth import current_user
from app.models import User,Membership,CreatorRecord
router=APIRouter(prefix="/v1/studio",tags=["creator-studio"])
MODULES={"ideas","research","competitors","scripts","seo_audits","thumbnail_tests","calendar","operations","growth_coach","localization","notifications","monetization","product_events"}
class RecordInput(BaseModel):
 title:str=Field(min_length=1,max_length=240)
 payload:dict=Field(default_factory=dict)
 status:str=Field(default="draft",max_length=40)
 due_at:datetime|None=None
class RecordPatch(BaseModel):
 title:str|None=Field(default=None,min_length=1,max_length=240)
 payload:dict|None=None
 status:str|None=Field(default=None,max_length=40)
 due_at:datetime|None=None
async def access(db,user,wid):
 m=await db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.workspace_id==wid))
 if not m: raise HTTPException(403,"Workspace access required")
@router.get("/modules")
async def modules(): return sorted(MODULES)
@router.get("/{module}")
async def list_records(module:str,workspace_id:UUID,limit:int=Query(100,ge=1,le=200),db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 if module not in MODULES: raise HTTPException(404,"Unknown module")
 await access(db,user,workspace_id)
 rows=await db.scalars(select(CreatorRecord).where(CreatorRecord.workspace_id==workspace_id,CreatorRecord.module==module).order_by(desc(CreatorRecord.updated_at)).limit(limit))
 return [serialize(r) for r in rows]
@router.post("/{module}",status_code=201)
async def create(module:str,workspace_id:UUID,body:RecordInput,db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 if module not in MODULES: raise HTTPException(404,"Unknown module")
 await access(db,user,workspace_id)
 r=CreatorRecord(workspace_id=workspace_id,created_by=user.id,module=module,title=body.title,payload=body.payload,status=body.status,due_at=body.due_at)
 db.add(r);await db.commit();await db.refresh(r);return serialize(r)
@router.patch("/{module}/{rid}")
async def patch(module:str,rid:UUID,workspace_id:UUID,body:RecordPatch,db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 if module not in MODULES: raise HTTPException(404,"Unknown module")
 await access(db,user,workspace_id)
 r=await db.scalar(select(CreatorRecord).where(CreatorRecord.id==rid,CreatorRecord.workspace_id==workspace_id,CreatorRecord.module==module))
 if not r: raise HTTPException(404,"Record not found")
 for k,v in body.model_dump(exclude_unset=True).items(): setattr(r,k,v)
 r.updated_at=datetime.now(timezone.utc);await db.commit();await db.refresh(r);return serialize(r)
@router.delete("/{module}/{rid}",status_code=204)
async def delete(module:str,rid:UUID,workspace_id:UUID,db:AsyncSession=Depends(get_db),user:User=Depends(current_user)):
 if module not in MODULES: raise HTTPException(404,"Unknown module")
 await access(db,user,workspace_id)
 r=await db.scalar(select(CreatorRecord).where(CreatorRecord.id==rid,CreatorRecord.workspace_id==workspace_id,CreatorRecord.module==module))
 if not r: raise HTTPException(404,"Record not found")
 await db.delete(r);await db.commit()
def serialize(r):
 return {"id":str(r.id),"module":r.module,"title":r.title,"payload":r.payload,"status":r.status,"due_at":r.due_at.isoformat() if r.due_at else None,"created_at":r.created_at.isoformat(),"updated_at":r.updated_at.isoformat()}
