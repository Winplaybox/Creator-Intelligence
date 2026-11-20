import uuid
from datetime import datetime,timezone
from sqlalchemy import String,DateTime,Boolean,ForeignKey,UniqueConstraint,Index,Text
from sqlalchemy.dialects.postgresql import UUID,JSONB
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.db import Base
def now_utc():
 return datetime.now(timezone.utc)
class User(Base):
 __tablename__="users"
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
 email:Mapped[str]=mapped_column(String(320),unique=True,index=True,nullable=False)
 password_hash:Mapped[str|None]=mapped_column(String(255))
 display_name:Mapped[str]=mapped_column(String(120),default="")
 email_verified:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
 is_active:Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)
 memberships:Mapped[list["Membership"]]=relationship(back_populates="user",cascade="all,delete-orphan")
class Workspace(Base):
 __tablename__="workspaces"
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
 name:Mapped[str]=mapped_column(String(120),nullable=False)
 slug:Mapped[str]=mapped_column(String(120),unique=True,index=True,nullable=False)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)
 memberships:Mapped[list["Membership"]]=relationship(back_populates="workspace",cascade="all,delete-orphan")
class Membership(Base):
 __tablename__="workspace_memberships"
 __table_args__=(UniqueConstraint("user_id","workspace_id",name="uq_membership_user_workspace"),)
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
 user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),nullable=False,index=True)
 workspace_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False,index=True)
 role:Mapped[str]=mapped_column(String(24),default="owner",nullable=False)
 user:Mapped[User]=relationship(back_populates="memberships")
 workspace:Mapped[Workspace]=relationship(back_populates="memberships")
class RefreshSession(Base):
 __tablename__="refresh_sessions"
 __table_args__=(Index("ix_refresh_user_active","user_id","revoked_at"),)
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
 user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),nullable=False,index=True)
 token_hash:Mapped[str]=mapped_column(String(64),unique=True,nullable=False)
 expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
 revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)
class YouTubeChannel(Base):
 __tablename__="youtube_channels"
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
 workspace_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False,index=True)
 connected_by:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),nullable=False)
 channel_id:Mapped[str]=mapped_column(String(64),unique=True,nullable=False)
 title:Mapped[str]=mapped_column(String(255),nullable=False)
 description:Mapped[str]=mapped_column(Text,default="",nullable=False)
 thumbnail_url:Mapped[str|None]=mapped_column(Text)
 access_token_encrypted:Mapped[str]=mapped_column(Text,nullable=False)
 refresh_token_encrypted:Mapped[str|None]=mapped_column(Text)
 token_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 scopes:Mapped[list]=mapped_column(JSONB,default=list,nullable=False)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)
 updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)

class CreatorRecord(Base):
 __tablename__="creator_records"
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
 workspace_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False,index=True)
 created_by:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),nullable=False)
 module:Mapped[str]=mapped_column(String(40),nullable=False,index=True)
 title:Mapped[str]=mapped_column(String(240),nullable=False)
 payload:Mapped[dict]=mapped_column(JSONB,default=dict,nullable=False)
 status:Mapped[str]=mapped_column(String(40),default="draft",nullable=False)
 due_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)
 updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,nullable=False)
