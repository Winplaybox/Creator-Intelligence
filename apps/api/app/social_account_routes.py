"""Social account registry foundation (Wave 14); credentials are deliberately not accepted."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import CreatorRecord, Membership, User

router = APIRouter(prefix="/v1/social/accounts", tags=["social-integrations"])
ALLOWED_PLATFORMS = {"instagram", "facebook", "tiktok", "pinterest", "linkedin"}


class AccountLinkRequest(BaseModel):
    workspace_id: UUID
    platform: str = Field(min_length=2, max_length=32)
    account_id: str = Field(min_length=1, max_length=128)
    account_name: str = Field(default="", max_length=240)
    profile_url: str | None = Field(default=None, max_length=2048)
    metadata: dict = Field(default_factory=dict)


async def require_membership(db: AsyncSession, user: User, workspace_id: UUID):
    membership = await db.scalar(select(Membership).where(
        Membership.user_id == user.id, Membership.workspace_id == workspace_id
    ))
    if membership is None:
        raise HTTPException(403, "Workspace access required")
    return membership


@router.post("", status_code=201)
async def register_account(body: AccountLinkRequest, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_membership(db, user, body.workspace_id)
    platform = body.platform.strip().lower()
    account_id = body.account_id.strip()
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(422, "Unsupported social platform")
    if not account_id:
        raise HTTPException(422, "account_id cannot be blank")
    existing = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.workspace_id == body.workspace_id,
        CreatorRecord.module == "social_account",
        CreatorRecord.payload["platform"].as_string() == platform,
        CreatorRecord.payload["account_id"].as_string() == account_id,
        CreatorRecord.status == "connected",
    ))
    if existing:
        raise HTTPException(409, "Account already registered in this workspace")
    record = CreatorRecord(
        workspace_id=body.workspace_id, created_by=user.id, module="social_account",
        title=f"{platform}: {body.account_name.strip() or account_id}",
        payload={"platform": platform, "account_id": account_id, "account_name": body.account_name.strip(),
                 "profile_url": body.profile_url, "metadata": body.metadata, "connection_type": "manual_registry",
                 "credential_status": "not_connected"},
        status="registered",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": str(record.id), "status": record.status, "account": record.payload,
            "note": "Registry entry created. OAuth/token connection and publishing are not implemented by this endpoint."}


@router.get("")
async def list_accounts(workspace_id: UUID, platform: str | None = Query(default=None, max_length=32),
    limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await require_membership(db, user, workspace_id)
    query = select(CreatorRecord).where(
        CreatorRecord.workspace_id == workspace_id, CreatorRecord.module == "social_account"
    )
    if platform:
        platform = platform.lower()
        if platform not in ALLOWED_PLATFORMS:
            raise HTTPException(422, "Unsupported social platform")
        query = query.where(CreatorRecord.payload["platform"].as_string() == platform)
    rows = await db.scalars(query.order_by(desc(CreatorRecord.created_at)).offset(offset).limit(limit))
    return {"workspace_id": str(workspace_id), "accounts": [
        {"id": str(row.id), "status": row.status, "account": row.payload, "created_at": row.created_at.isoformat()}
        for row in rows
    ], "limit": limit, "offset": offset}


@router.delete("/{account_record_id}", status_code=204)
async def remove_account(account_record_id: UUID, workspace_id: UUID, db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user)):
    await require_membership(db, user, workspace_id)
    record = await db.scalar(select(CreatorRecord).where(
        CreatorRecord.id == account_record_id, CreatorRecord.workspace_id == workspace_id,
        CreatorRecord.module == "social_account",
    ))
    if record is None:
        raise HTTPException(404, "Social account registry entry not found")
    record.status = "removed"
    await db.commit()
