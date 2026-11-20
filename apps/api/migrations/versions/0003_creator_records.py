"""Creator studio workspace records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0003_creator_records";down_revision="0002_youtube_channels";branch_labels=None;depends_on=None
def upgrade():
 op.create_table("creator_records",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("workspace_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False),sa.Column("created_by",postgresql.UUID(as_uuid=True),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("module",sa.String(40),nullable=False),sa.Column("title",sa.String(240),nullable=False),sa.Column("payload",postgresql.JSONB(),nullable=False,server_default="{}"),sa.Column("status",sa.String(40),nullable=False,server_default="draft"),sa.Column("due_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
 op.create_index("ix_creator_records_ws_module_updated","creator_records",["workspace_id","module","updated_at"])
def downgrade():
 op.drop_index("ix_creator_records_ws_module_updated",table_name="creator_records");op.drop_table("creator_records")
