from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conversation.models import (
    BusinessMemoryRecord,
    ConversationMemoryRecord,
    DataSourceRecord,
    UserPreferenceRecord,
)
from app.core.errors import NotFoundError
from app.planning.models import QueryPlanV1


class MemoryService:
    """Keeps working, preference and governed business memory isolated."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def save_conversation_summary(self, conversation_id: str, version: int, plan: QueryPlanV1) -> None:
        summary = {
            "intent": plan.intent,
            "metrics": plan.metrics,
            "dimensions": plan.dimensions,
            "date_range": plan.date_range.model_dump(mode="json"),
            "filters": [item.model_dump(mode="json") for item in plan.filters],
            "comparison": plan.comparison.model_dump(mode="json"),
            "data_source_id": plan.data_source_id,
            "open_questions": [item.question for item in plan.clarifications],
        }
        async with self.sessions.begin() as session:
            row = await session.get(ConversationMemoryRecord, conversation_id)
            if row:
                row.summary_json = json.dumps(summary, ensure_ascii=False)
                row.plan_version = version
            else:
                session.add(ConversationMemoryRecord(
                    conversation_id=conversation_id,
                    summary_json=json.dumps(summary, ensure_ascii=False),
                    plan_version=version,
                ))

    async def context(self, tenant_id: str, user_id: str, source_id: str | None) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            source = await session.get(DataSourceRecord, source_id) if source_id else None
            preferences = (await session.execute(select(UserPreferenceRecord).where(
                UserPreferenceRecord.tenant_id == tenant_id,
                UserPreferenceRecord.user_id == user_id,
                UserPreferenceRecord.enabled == 1,
            ))).scalars()
            memory_filter = [
                BusinessMemoryRecord.tenant_id == tenant_id,
                BusinessMemoryRecord.status == "certified",
                or_(BusinessMemoryRecord.expires_at.is_(None), BusinessMemoryRecord.expires_at > now),
            ]
            if source_id:
                memory_filter.append(BusinessMemoryRecord.source_id.in_(["", source_id]))
                memory_filter.append(or_(
                    BusinessMemoryRecord.schema_fingerprint == "",
                    BusinessMemoryRecord.schema_fingerprint == (source.schema_fingerprint if source else "__missing__"),
                ))
            else:
                memory_filter.append(BusinessMemoryRecord.source_id == "")
            memories = list((await session.execute(
                select(BusinessMemoryRecord).where(*memory_filter).order_by(BusinessMemoryRecord.updated_at.desc()).limit(30)
            )).scalars())
        return {
            "user_preferences": {item.preference_key: json.loads(item.value_json) for item in preferences},
            "certified_business_memory": [self._business_dict(item) for item in memories],
        }

    async def list_preferences(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = list((await session.execute(select(UserPreferenceRecord).where(
                UserPreferenceRecord.tenant_id == tenant_id,
                UserPreferenceRecord.user_id == user_id,
            ).order_by(UserPreferenceRecord.preference_key))).scalars())
        return [self._preference_dict(item) for item in rows]

    async def put_preference(self, tenant_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            row = (await session.execute(select(UserPreferenceRecord).where(
                UserPreferenceRecord.tenant_id == tenant_id,
                UserPreferenceRecord.user_id == user_id,
                UserPreferenceRecord.preference_key == payload["key"],
            ))).scalar_one_or_none()
            if not row:
                row = UserPreferenceRecord(tenant_id=tenant_id, user_id=user_id, preference_key=payload["key"])
                session.add(row)
            row.value_json = json.dumps(payload["value"], ensure_ascii=False)
            row.enabled = int(payload.get("enabled", True))
        return self._preference_dict(row)

    async def list_business(self, tenant_id: str, source_id: str | None = None) -> list[dict[str, Any]]:
        conditions = [BusinessMemoryRecord.tenant_id == tenant_id]
        if source_id is not None:
            conditions.append(BusinessMemoryRecord.source_id == source_id)
        async with self.sessions() as session:
            rows = list((await session.execute(select(BusinessMemoryRecord).where(*conditions).order_by(
                BusinessMemoryRecord.updated_at.desc()
            ))).scalars())
        return [self._business_dict(item) for item in rows]

    async def put_business(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = payload.get("source_id") or ""
        async with self.sessions.begin() as session:
            if source_id and not await session.get(DataSourceRecord, source_id):
                raise NotFoundError("数据源")
            row = (await session.execute(select(BusinessMemoryRecord).where(
                BusinessMemoryRecord.tenant_id == tenant_id,
                BusinessMemoryRecord.source_id == source_id,
                BusinessMemoryRecord.memory_key == payload["key"],
            ))).scalar_one_or_none()
            if not row:
                row = BusinessMemoryRecord(tenant_id=tenant_id, source_id=source_id, memory_key=payload["key"], title=payload["title"], content=payload["content"])
                session.add(row)
            else:
                row.version += 1
            for field in ("title", "content", "category", "evidence", "status", "schema_fingerprint", "expires_at"):
                if field in payload:
                    setattr(row, field, payload[field])
        return self._business_dict(row)

    async def delete_business(self, tenant_id: str, memory_id: str) -> None:
        async with self.sessions.begin() as session:
            result = await session.execute(delete(BusinessMemoryRecord).where(
                BusinessMemoryRecord.id == memory_id, BusinessMemoryRecord.tenant_id == tenant_id
            ))
            if not result.rowcount:
                raise NotFoundError("业务记忆")

    @staticmethod
    def _preference_dict(item: UserPreferenceRecord) -> dict[str, Any]:
        return {"id": item.id, "key": item.preference_key, "value": json.loads(item.value_json), "enabled": bool(item.enabled), "updated_at": item.updated_at.isoformat()}

    @staticmethod
    def _business_dict(item: BusinessMemoryRecord) -> dict[str, Any]:
        return {"id": item.id, "source_id": item.source_id or None, "category": item.category, "key": item.memory_key, "title": item.title, "content": item.content, "evidence": item.evidence, "status": item.status, "schema_fingerprint": item.schema_fingerprint, "version": item.version, "expires_at": item.expires_at.isoformat() if item.expires_at else None, "updated_at": item.updated_at.isoformat()}
