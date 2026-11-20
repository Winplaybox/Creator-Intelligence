"""Usernames + Google identity on users; Dodo billing tables and the workspace credit ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0004_usernames_billing";down_revision="0003_creator_records";branch_labels=None;depends_on=None
def upgrade():
 op.add_column("users",sa.Column("username",sa.String(32),nullable=True))
 op.add_column("users",sa.Column("google_sub",sa.String(64),nullable=True))
 # Backfill a unique username for existing accounts: local part of the email + short id suffix.
 op.execute("""UPDATE users SET username = left(regexp_replace(lower(split_part(email,'@',1)),'[^a-z0-9_]+','_','g'),20) || '_' || substr(replace(id::text,'-',''),1,6) WHERE username IS NULL""")
 op.create_index("ix_users_username","users",["username"],unique=True)
 op.create_unique_constraint("uq_users_google_sub","users",["google_sub"])
 op.create_table("workspace_subscriptions",
  sa.Column("workspace_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("workspaces.id",ondelete="CASCADE"),primary_key=True),
  sa.Column("plan",sa.String(32),nullable=False,server_default="free"),
  sa.Column("status",sa.String(24),nullable=False,server_default="active"),
  sa.Column("provider_subscription_id",sa.String(64),unique=True),
  sa.Column("provider_customer_id",sa.String(64)),
  sa.Column("current_period_end",sa.DateTime(timezone=True)),
  sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
 op.create_table("billing_payments",
  sa.Column("payment_id",sa.String(64),primary_key=True),
  sa.Column("workspace_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False),
  sa.Column("plan",sa.String(32),nullable=False),
  sa.Column("credits",sa.Integer(),nullable=False,server_default="0"),
  sa.Column("amount_minor",sa.BigInteger()),
  sa.Column("currency",sa.String(3)),
  sa.Column("provider_subscription_id",sa.String(64)),
  sa.Column("status",sa.String(24),nullable=False,server_default="granted"),
  sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
 op.create_index("ix_billing_payments_workspace_id","billing_payments",["workspace_id"])
 op.create_index("ix_billing_payments_provider_subscription_id","billing_payments",["provider_subscription_id"])
 op.create_table("billing_webhook_events",
  sa.Column("webhook_id",sa.String(128),primary_key=True),
  sa.Column("event_type",sa.String(64),nullable=False),
  sa.Column("received_at",sa.DateTime(timezone=True),nullable=False),
  sa.Column("result",sa.String(500)))
 op.create_table("credit_ledger",
  sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
  sa.Column("workspace_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("workspaces.id",ondelete="CASCADE"),nullable=False),
  sa.Column("amount",sa.Integer(),nullable=False),
  sa.Column("kind",sa.String(40),nullable=False),
  sa.Column("reference",sa.String(160),nullable=False),
  sa.Column("description",sa.String(240),nullable=False,server_default=""),
  sa.Column("actor_user_id",postgresql.UUID(as_uuid=True)),
  sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
  sa.UniqueConstraint("workspace_id","kind","reference",name="uq_credit_ledger_once"))
 op.create_index("ix_credit_ledger_ws_created","credit_ledger",["workspace_id","created_at"])
def downgrade():
 op.drop_index("ix_credit_ledger_ws_created",table_name="credit_ledger");op.drop_table("credit_ledger")
 op.drop_table("billing_webhook_events")
 op.drop_index("ix_billing_payments_provider_subscription_id",table_name="billing_payments")
 op.drop_index("ix_billing_payments_workspace_id",table_name="billing_payments");op.drop_table("billing_payments")
 op.drop_table("workspace_subscriptions")
 op.drop_constraint("uq_users_google_sub","users",type_="unique")
 op.drop_index("ix_users_username",table_name="users")
 op.drop_column("users","google_sub");op.drop_column("users","username")
