from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ConversationStatus(str, enum.Enum):
    NEW = "new"
    UNSUPPORTED = "unsupported"
    CLARIFYING = "clarifying"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), default="analyst")
    status: Mapped[str] = mapped_column(String(32), default="active")
    must_change_password: Mapped[int] = mapped_column(Integer, default=0)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="local-user", index=True)
    title: Mapped[str] = mapped_column(String(255), default="新建数据分析")
    status: Mapped[str] = mapped_column(String(32), default=ConversationStatus.NEW.value)
    current_plan_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list[MessageRecord]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    plans: Mapped[list[PlanVersionRecord]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class MessageRecord(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[ConversationRecord] = relationship(back_populates="messages")


class PlanVersionRecord(Base):
    __tablename__ = "query_plan_versions"
    __table_args__ = (UniqueConstraint("conversation_id", "version", name="uq_conversation_plan_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    plan_json: Mapped[str] = mapped_column(Text)
    plan_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[ConversationRecord] = relationship(back_populates="plans")


class QueryExecutionRecord(Base):
    __tablename__ = "query_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    plan_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SchemaCatalogOverrideRecord(Base):
    __tablename__ = "schema_catalog_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "schema_name", "table_name", "column_name", name="uq_schema_catalog_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    schema_name: Mapped[str] = mapped_column(String(128))
    table_name: Mapped[str] = mapped_column(String(128))
    column_name: Mapped[str] = mapped_column(String(128), default="")
    display_name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DataSourceRecord(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tenant_data_source_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    name: Mapped[str] = mapped_column(String(255))
    database_type: Mapped[str] = mapped_column(String(32), default="postgresql")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=5432)
    database_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(255))
    password_cipher: Mapped[str] = mapped_column(Text, default="")
    schemas_json: Mapped[str] = mapped_column(Text, default='["public"]')
    status: Mapped[str] = mapped_column(String(32), default="draft")
    schema_version: Mapped[str] = mapped_column(String(64), default="")
    schema_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    tools_json: Mapped[str] = mapped_column(Text, default="[]")
    business_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SchemaKnowledgeDocumentRecord(Base):
    __tablename__ = "schema_knowledge_documents"
    __table_args__ = (UniqueConstraint("source_id", "object_key", "schema_version", name="uq_schema_document_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    object_type: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(512))
    table_name: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    embedding_json: Mapped[str] = mapped_column(Text, default="[]")
    schema_version: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SchemaSyncJobRecord(Base):
    __tablename__ = "schema_sync_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="scanning")
    stage: Mapped[str] = mapped_column(String(32), default="connecting")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SemanticDefinitionRecord(Base):
    __tablename__ = "semantic_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", "kind", "semantic_key", name="uq_semantic_definition"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    semantic_key: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(String(255))
    definition_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SemanticBindingObservationRecord(Base):
    __tablename__ = "semantic_binding_observations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", "role", "semantic_key", "object_key", name="uq_binding_observation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    semantic_key: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(512))
    confirmation_count: Mapped[int] = mapped_column(Integer, default=1)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationMemoryRecord(Base):
    """Compact working memory for one conversation; never used across users."""
    __tablename__ = "conversation_memories"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserPreferenceRecord(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "preference_key", name="uq_user_preference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="local-user", index=True)
    preference_key: Mapped[str] = mapped_column(String(128))
    value_json: Mapped[str] = mapped_column(Text, default="null")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BusinessMemoryRecord(Base):
    """Governed reusable memory. Only certified rows are injected into planning."""
    __tablename__ = "business_memories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", "memory_key", name="uq_business_memory"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    source_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    category: Mapped[str] = mapped_column(String(32), default="business_rule")
    memory_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    schema_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class VerifiedQueryPathRecord(Base):
    """经人工审核的可复用查询路径；不保存为绕过计划校验的裸 SQL。"""
    __tablename__ = "verified_query_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    source_execution_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    title: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text)
    normalized_question: Mapped[str] = mapped_column(String(2048), index=True)
    plan_json: Mapped[str] = mapped_column(Text)
    dependencies_json: Mapped[str] = mapped_column(Text, default="{}")
    schema_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    confirmation_count: Mapped[int] = mapped_column(Integer, default=1)
    success_count: Mapped[int] = mapped_column(Integer, default=1)
    reviewer: Mapped[str] = mapped_column(String(64), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QueryFeedbackRecord(Base):
    """用户对一次真实执行的反馈；正确反馈仅生成待审核路径。"""
    __tablename__ = "query_feedback"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_query_feedback_execution"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="local-user", index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("query_executions.id", ondelete="CASCADE"), index=True)
    verdict: Mapped[str] = mapped_column(String(32))
    issue_type: Mapped[str] = mapped_column(String(64), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    query_path_id: Mapped[str] = mapped_column(String(36), default="")
    reviewed_by: Mapped[str] = mapped_column(String(64), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
