"""Workspace YouTube channel credential and profile storage."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0002_youtube_channels"
down_revision="0001_identity_workspace"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("youtube_channels",
  sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
  sa.Column("workspace_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False),
  sa.Column("connected_by",postgresql.UUID(as_uuid=True),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
  sa.Column("channel_id",sa.String(64),nullable=False,unique=True),
  sa.Column("title",sa.String(255),nullable=False),
  sa.Column("description",sa.Text(),nullable=False,server_default=""),
  sa.Column("thumbnail_url",sa.Text()),
  sa.Column("access_token_encrypted",sa.Text(),nullable=False),
  sa.Column("refresh_token_encrypted",sa.Text()),
  sa.Column("token_expires_at",sa.DateTime(timezone=True)),
  sa.Column("scopes",postgresql.JSONB(),nullable=False,server_default="[]"),
  sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
  sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
 )
 op.create_index("ix_youtube_channels_workspace_id","youtube_channels",["workspace_id"])
def downgrade():
 op.drop_table("youtube_channels")
