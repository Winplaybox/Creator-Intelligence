"""Initial identity, workspace and refresh-session tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0001_identity_workspace"
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("users",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("email",sa.String(320),nullable=False),sa.Column("password_hash",sa.String(255)),sa.Column("display_name",sa.String(120),nullable=False),sa.Column("email_verified",sa.Boolean(),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
 op.create_index("ix_users_email","users",["email"],unique=True)
 op.create_table("workspaces",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("name",sa.String(120),nullable=False),sa.Column("slug",sa.String(120),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
 op.create_index("ix_workspaces_slug","workspaces",["slug"],unique=True)
 op.create_table("workspace_memberships",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("user_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("workspace_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False),sa.Column("role",sa.String(24),nullable=False))
 op.create_index("ix_workspace_memberships_user_id","workspace_memberships",["user_id"])
 op.create_index("ix_workspace_memberships_workspace_id","workspace_memberships",["workspace_id"])
 op.create_unique_constraint("uq_membership_user_workspace","workspace_memberships",["user_id","workspace_id"])
 op.create_table("refresh_sessions",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("user_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("revoked_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
 op.create_index("ix_refresh_sessions_user_id","refresh_sessions",["user_id"])
 op.create_index("ix_refresh_user_active","refresh_sessions",["user_id","revoked_at"])
 op.create_index("ix_refresh_sessions_token_hash","refresh_sessions",["token_hash"],unique=True)
def downgrade():
 op.drop_table("refresh_sessions")
 op.drop_constraint("uq_membership_user_workspace","workspace_memberships",type_="unique")
 op.drop_table("workspace_memberships")
 op.drop_table("workspaces")
 op.drop_table("users")
