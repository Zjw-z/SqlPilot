from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conversation.models import (
    ConversationRecord,
    MessageRecord,
    PlanVersionRecord,
    QueryExecutionRecord,
)
from app.core.errors import ConflictError, NotFoundError
from app.planning.models import QueryPlanV1


class ConversationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create(self, tenant_id: str, user_id: str, title: str) -> ConversationRecord:
        async with self.sessions.begin() as session:
            item = ConversationRecord(tenant_id=tenant_id, user_id=user_id, title=title)
            session.add(item)
        return item

    async def list(self, tenant_id: str, user_id: str, limit: int = 50) -> list[ConversationRecord]:
        async with self.sessions() as session:
            statement = (
                select(ConversationRecord)
                .where(ConversationRecord.tenant_id == tenant_id, ConversationRecord.user_id == user_id)
                .order_by(ConversationRecord.updated_at.desc(), ConversationRecord.created_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            return list((await session.execute(statement)).scalars())

    async def get(self, conversation_id: str, tenant_id: str | None = None, user_id: str | None = None) -> ConversationRecord:
        async with self.sessions() as session:
            item = await session.get(ConversationRecord, conversation_id)
            if not item:
                raise NotFoundError("会话")
            if tenant_id is not None and (item.tenant_id != tenant_id or item.user_id != user_id):
                raise NotFoundError("会话")
            return item

    async def add_message(self, conversation_id: str, role: str, content: str, message_type: str = "text") -> None:
        async with self.sessions.begin() as session:
            conversation = await session.get(ConversationRecord, conversation_id)
            if not conversation:
                raise NotFoundError("会话")
            if role == "user" and conversation.title == "新建数据分析":
                conversation.title = " ".join(content.split())[:60]
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(MessageRecord(conversation_id=conversation_id, role=role, content=content, message_type=message_type))

    async def latest_plan(self, conversation_id: str) -> tuple[PlanVersionRecord, QueryPlanV1] | None:
        async with self.sessions() as session:
            statement = (
                select(PlanVersionRecord)
                .where(PlanVersionRecord.conversation_id == conversation_id)
                .order_by(PlanVersionRecord.version.desc())
                .limit(1)
            )
            record = (await session.execute(statement)).scalar_one_or_none()
            return (record, QueryPlanV1.model_validate_json(record.plan_json)) if record else None

    async def save_plan(self, conversation_id: str, plan: QueryPlanV1, status: str) -> PlanVersionRecord:
        async with self.sessions.begin() as session:
            conversation = await session.get(ConversationRecord, conversation_id)
            if not conversation:
                raise NotFoundError("会话")
            version = conversation.current_plan_version + 1
            record = PlanVersionRecord(
                conversation_id=conversation_id,
                version=version,
                plan_json=plan.model_dump_json(),
                plan_hash=plan.stable_hash(),
                status=status,
            )
            conversation.current_plan_version = version
            conversation.status = status
            session.add(record)
        return record

    async def confirm(self, conversation_id: str, version: int, plan_hash: str) -> PlanVersionRecord:
        async with self.sessions.begin() as session:
            conversation = await session.get(ConversationRecord, conversation_id)
            if not conversation:
                raise NotFoundError("会话")
            if conversation.current_plan_version != version:
                raise ConflictError("查询计划已更新，请确认最新版本")
            statement = select(PlanVersionRecord).where(
                PlanVersionRecord.conversation_id == conversation_id,
                PlanVersionRecord.version == version,
            )
            record = (await session.execute(statement)).scalar_one()
            if record.plan_hash != plan_hash:
                raise ConflictError("查询计划内容已发生变化")
            plan = QueryPlanV1.model_validate_json(record.plan_json)
            if plan.intent == "unsupported":
                raise ConflictError("当前问题不是可执行的数据查询，不能确认查询计划")
            if plan.needs_clarification:
                raise ConflictError("仍有问题需要澄清，暂不能确认")
            record.status = "confirmed"
            record.confirmed_at = datetime.now(timezone.utc)
            conversation.status = "confirmed"
        return record

    async def save_execution(self, record: QueryExecutionRecord) -> None:
        async with self.sessions.begin() as session:
            conversation = await session.get(ConversationRecord, record.conversation_id)
            if not conversation:
                raise NotFoundError("会话")
            conversation.status = record.status
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(record)

    async def messages(self, conversation_id: str) -> list[MessageRecord]:
        async with self.sessions() as session:
            statement = select(MessageRecord).where(MessageRecord.conversation_id == conversation_id).order_by(MessageRecord.created_at)
            return list((await session.execute(statement)).scalars())

    async def executions(self, conversation_id: str) -> list[QueryExecutionRecord]:
        async with self.sessions() as session:
            statement = (
                select(QueryExecutionRecord)
                .where(QueryExecutionRecord.conversation_id == conversation_id)
                .order_by(QueryExecutionRecord.created_at)
            )
            return list((await session.execute(statement)).scalars())
