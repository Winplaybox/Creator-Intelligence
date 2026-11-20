"""Workspace RBAC management and role-change audit trail (Wave 16)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/workspaces", tags=["workspace-rbac"])
ALLOWED_ROLES = {"admin", "editor", "viewer"}


async def membership(db: AsyncSession, user: User, workspace_id: UUID) -> Membership:
    row = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id))
    if row is None:
        raise HTTPException(403, "Workspace access required")
    return row


@router.get("/{workspace_id}/members")
async def list_members(workspace_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    caller = await membership(db, user, workspace_id)
    if caller.role.lower() not in {"owner", "admin"}:
        raise HTTPException(403, "Workspace owner or admin required")
    rows = await db.scalars(select(Membership).where(Membership.workspace_id == workspace_id))
    result = []
    for row in rows:
        member = await db.get(User, row.user_id)
        if member:
            result.append({"user_id": str(member.id), "email": member.email, "display_name": member.display_name,
                          "role": row.role, "active": member.is_active, "joined_at": None})
    return {"workspace_id": str(workspace_id), "members": result}


class RoleUpdate(BaseModel):
    role: str = Field(min_length=3, max_length=24)


@router.patch("/{workspace_id}/members/{member_user_id}/role")
async def update_member_role(workspace_id: UUID, member_user_id: UUID, body: RoleUpdate,
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    caller = await membership(db, user, workspace_id)
    requested = body.role.strip().lower()
    if requested not in ALLOWED_ROLES:
        raise HTTPException(422, "Role must be admin, editor, or viewer")
    if caller.role.lower() not in {"owner", "admin"}:
        raise HTTPException(403, "Workspace owner or admin required")
    target = await db.scalar(select(Membership).where(
        Membership.user_id == member_user_id, Membership.workspace_id == workspace_id
    ).with_for_update())
    if target is None:
        raise HTTPException(404, "Workspace member not found")
    if target.role.lower() == "owner":
        raise HTTPException(409, "Owner role cannot be changed through this endpoint")
    if caller.role.lower() == "admin" and requested == "admin":
        raise HTTPException(403, "Admins cannot grant admin role")
    previous = target.role
    target.role = requested
    audit = CreatorRecord(workspace_id=workspace_id, created_by=user.id, module="rbac_audit",
        title=f"Role change {member_user_id}", status="audit",
        payload={"actor_user_id": str(user.id), "target_user_id": str(member_user_id),
                 "from_role": previous, "to_role": requested, "occurred_at": datetime.now(timezone.utc).isoformat()})
    db.add(audit)
    await db.commit()
    return {"workspace_id": str(workspace_id), "user_id": str(member_user_id), "from_role": previous, "role": requested}


@router.get("/{workspace_id}/audit/roles")
async def role_audit(workspace_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    caller = await membership(db, user, workspace_id)
    if caller.role.lower() not in {"owner", "admin"}:
        raise HTTPException(403, "Workspace owner or admin required")
    rows = await db.scalars(select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "rbac_audit"
    ).order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {"workspace_id": str(workspace_id), "events": [
        {"id": str(row.id), "payload": row.payload, "created_at": row.created_at.isoformat()} for row in rows
    ], "limit": limit, "offset": offset}
