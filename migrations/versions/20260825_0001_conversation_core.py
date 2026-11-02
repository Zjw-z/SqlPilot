"""conversation core tables"""
from alembic import op
import sqlalchemy as sa

revision = "20260825_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("conversations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("user_id", sa.String(64), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("current_plan_version", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_table("conversation_messages", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(16), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("message_type", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])
    op.create_table("query_plan_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("plan_json", sa.Text(), nullable=False), sa.Column("plan_hash", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("confirmed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("conversation_id", "version", name="uq_conversation_plan_version"))
    op.create_index("ix_query_plan_versions_conversation_id", "query_plan_versions", ["conversation_id"])
    op.create_table("query_executions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False), sa.Column("plan_version", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("sql_text", sa.Text()), sa.Column("result_json", sa.Text()), sa.Column("error_code", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_query_executions_conversation_id", "query_executions", ["conversation_id"])

def downgrade():
    op.drop_table("query_executions")
    op.drop_table("query_plan_versions")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
