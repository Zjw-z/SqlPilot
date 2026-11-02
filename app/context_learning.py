from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.conversation.models import (
    ConversationRecord, DataSourceRecord, MessageRecord, PlanVersionRecord,
    QueryExecutionRecord, QueryFeedbackRecord, SemanticDefinitionRecord,
    VerifiedQueryPathRecord,
)
from app.core.errors import ConflictError, NotFoundError, PlannerError
from app.planning.models import QueryPlanV1
from app.planning.summarizer import summarize_plan


class ContextLearningService:
    """将真实查询反馈转为可审核、可失效、可追溯的查询路径。"""

    def __init__(self, sessions: async_sessionmaker) -> None:
        self.sessions = sessions

    async def submit_feedback(self, tenant_id: str, user_id: str, execution_id: str,
                              payload: dict[str, Any]) -> dict[str, Any]:
        verdict = payload["verdict"]
        if verdict not in {"correct", "incorrect"}:
            raise PlannerError("FEEDBACK_INVALID", "反馈类型无效", False)
        async with self.sessions.begin() as session:
            execution = await session.get(QueryExecutionRecord, execution_id)
            if not execution:
                raise NotFoundError("查询执行")
            conversation = await session.get(ConversationRecord, execution.conversation_id)
            if not conversation or conversation.tenant_id != tenant_id or conversation.user_id != user_id:
                raise NotFoundError("查询执行")
            feedback = await session.scalar(select(QueryFeedbackRecord).where(
                QueryFeedbackRecord.execution_id == execution_id
            ))
            previous_review_status = feedback.review_status if feedback else None
            if feedback is None:
                feedback = QueryFeedbackRecord(
                    tenant_id=tenant_id, user_id=user_id, execution_id=execution_id,
                    verdict=verdict,
                )
                session.add(feedback)
            feedback.verdict = verdict
            feedback.issue_type = payload.get("issue_type", "")
            feedback.comment = payload.get("comment", "")
            feedback.review_status = "pending"
            feedback.reviewed_by = ""
            feedback.reviewed_at = None
            if verdict == "correct":
                if execution.status != "completed":
                    raise ConflictError("只有成功执行的查询才能沉淀为路径")
                plan_record = await session.scalar(select(PlanVersionRecord).where(
                    PlanVersionRecord.conversation_id == execution.conversation_id,
                    PlanVersionRecord.version == execution.plan_version,
                ))
                if not plan_record:
                    raise NotFoundError("查询计划")
                plan = QueryPlanV1.model_validate_json(plan_record.plan_json)
                if not plan.data_source_id:
                    raise ConflictError("查询计划缺少数据源")
                source = await session.get(DataSourceRecord, plan.data_source_id)
                messages = (await session.scalars(select(MessageRecord).where(
                    MessageRecord.conversation_id == execution.conversation_id,
                    MessageRecord.role == "user",
                ).order_by(MessageRecord.created_at))).all()
                question = "；".join(item.content.strip() for item in messages if item.content.strip())
                normalized = self.normalize_question(question)
                path = await session.scalar(select(VerifiedQueryPathRecord).where(
                    VerifiedQueryPathRecord.tenant_id == tenant_id,
                    VerifiedQueryPathRecord.source_id == plan.data_source_id,
                    VerifiedQueryPathRecord.normalized_question == normalized,
                ))
                if path is None:
                    path = VerifiedQueryPathRecord(
                        tenant_id=tenant_id, source_id=plan.data_source_id,
                        source_execution_id=execution.id, title=summarize_plan(plan)[:255],
                        question=question, normalized_question=normalized,
                        plan_json=plan.model_dump_json(),
                        dependencies_json=json.dumps(self.plan_dependencies(plan), ensure_ascii=False),
                        schema_fingerprint=source.schema_fingerprint if source else "",
                        status="draft",
                    )
                    session.add(path)
                    await session.flush()
                else:
                    path.confirmation_count += 1
                    path.success_count += 1
                    path.source_execution_id = execution.id
                    path.plan_json = plan.model_dump_json()
                    path.dependencies_json = json.dumps(self.plan_dependencies(plan), ensure_ascii=False)
                    path.schema_fingerprint = source.schema_fingerprint if source else ""
                    if path.status == "stale" or previous_review_status == "approved":
                        path.status = "draft"
                feedback.query_path_id = path.id
            elif feedback.query_path_id:
                path = await session.get(VerifiedQueryPathRecord, feedback.query_path_id)
                if path and path.status == "certified":
                    path.status = "draft"
        return self._feedback_dict(feedback)

    async def list_feedback(self, tenant_id: str, status: str | None = None) -> list[dict[str, Any]]:
        conditions = [QueryFeedbackRecord.tenant_id == tenant_id]
        if status:
            conditions.append(QueryFeedbackRecord.review_status == status)
        async with self.sessions() as session:
            rows = (await session.scalars(select(QueryFeedbackRecord).where(*conditions).order_by(
                QueryFeedbackRecord.created_at.desc()
            ))).all()
        return [self._feedback_dict(item) for item in rows]

    async def review_feedback(self, tenant_id: str, feedback_id: str, reviewer: str,
                              payload: dict[str, Any]) -> dict[str, Any]:
        decision = payload["decision"]
        if decision not in {"approve", "reject"}:
            raise PlannerError("REVIEW_INVALID", "审核结果无效", False)
        async with self.sessions.begin() as session:
            feedback = await session.get(QueryFeedbackRecord, feedback_id)
            if not feedback or feedback.tenant_id != tenant_id:
                raise NotFoundError("查询反馈")
            feedback.review_status = "approved" if decision == "approve" else "rejected"
            feedback.reviewed_by = reviewer
            feedback.reviewed_at = datetime.now(timezone.utc)
            if feedback.query_path_id:
                path = await session.get(VerifiedQueryPathRecord, feedback.query_path_id)
                if path:
                    if decision == "approve" and feedback.verdict == "correct":
                        path.status = "certified"
                        path.reviewer = reviewer
                        path.review_note = payload.get("note", "")
                    elif decision == "reject":
                        path.status = "disabled"
                        path.reviewer = reviewer
                        path.review_note = payload.get("note", "") or "审核未通过"
        return self._feedback_dict(feedback)

    async def list_paths(self, tenant_id: str, source_id: str | None = None) -> list[dict[str, Any]]:
        conditions = [VerifiedQueryPathRecord.tenant_id == tenant_id]
        if source_id:
            conditions.append(VerifiedQueryPathRecord.source_id == source_id)
        async with self.sessions() as session:
            rows = (await session.scalars(select(VerifiedQueryPathRecord).where(*conditions).order_by(
                VerifiedQueryPathRecord.updated_at.desc()
            ))).all()
        return [self._path_dict(item) for item in rows]

    async def context(self, tenant_id: str, source_id: str, question: str,
                      schema_fingerprint: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(VerifiedQueryPathRecord).where(
                VerifiedQueryPathRecord.tenant_id == tenant_id,
                VerifiedQueryPathRecord.source_id == source_id,
                VerifiedQueryPathRecord.status == "certified",
                VerifiedQueryPathRecord.schema_fingerprint == schema_fingerprint,
            ))).all()
        query_tokens = self._tokens(question)
        ranked = []
        for item in rows:
            path_tokens = self._tokens(item.question)
            overlap = len(query_tokens & path_tokens) / max(1, len(query_tokens | path_tokens))
            exact = self.normalize_question(question) == item.normalized_question
            score = 1.0 if exact else overlap
            if score >= 0.18:
                ranked.append((score, item))
        ranked.sort(key=lambda value: (value[0], value[1].confirmation_count), reverse=True)
        return [{**self._path_dict(item), "match_score": round(score, 4)} for score, item in ranked[:5]]

    async def find_exact_plan(self, tenant_id: str, source_id: str, question: str,
                              schema_fingerprint: str) -> tuple[QueryPlanV1, str] | None:
        normalized = self.normalize_question(question)
        async with self.sessions() as session:
            row = await session.scalar(select(VerifiedQueryPathRecord).where(
                VerifiedQueryPathRecord.tenant_id == tenant_id,
                VerifiedQueryPathRecord.source_id == source_id,
                VerifiedQueryPathRecord.status == "certified",
                VerifiedQueryPathRecord.schema_fingerprint == schema_fingerprint,
                VerifiedQueryPathRecord.normalized_question == normalized,
            ).order_by(VerifiedQueryPathRecord.confirmation_count.desc()))
        if not row:
            return None
        plan = QueryPlanV1.model_validate_json(row.plan_json)
        today = date.today()
        if plan.date_range.type == "current_year_to_date":
            plan.date_range.start, plan.date_range.end = date(today.year, 1, 1), today
            plan.date_range.comparison_start = plan.date_range.comparison_end = None
            if plan.comparison.type == "year_over_year":
                plan.date_range.comparison_start = plan._previous_year_date(plan.date_range.start)
                plan.date_range.comparison_end = plan._previous_year_date(plan.date_range.end)
        plan.assumptions.append(f"已复用认证查询路径：{row.id}")
        return plan, row.id

    async def invalidate_for_schema_change(self, tenant_id: str, source_id: str,
                                           old_fingerprint: str, new_fingerprint: str) -> int:
        if not old_fingerprint or old_fingerprint == new_fingerprint:
            return 0
        async with self.sessions.begin() as session:
            rows = (await session.scalars(select(VerifiedQueryPathRecord).where(
                VerifiedQueryPathRecord.tenant_id == tenant_id,
                VerifiedQueryPathRecord.source_id == source_id,
                VerifiedQueryPathRecord.status.in_(["certified", "draft"]),
                VerifiedQueryPathRecord.schema_fingerprint != new_fingerprint,
            ))).all()
            for row in rows:
                row.status = "stale"
                row.review_note = "Schema指纹变化，需重新验证"
        return len(rows)

    async def dependency_graph(self, tenant_id: str, source_id: str) -> dict[str, Any]:
        async with self.sessions() as session:
            definitions = (await session.scalars(select(SemanticDefinitionRecord).where(
                SemanticDefinitionRecord.tenant_id == tenant_id,
                SemanticDefinitionRecord.source_id == source_id,
            ))).all()
            paths = (await session.scalars(select(VerifiedQueryPathRecord).where(
                VerifiedQueryPathRecord.tenant_id == tenant_id,
                VerifiedQueryPathRecord.source_id == source_id,
            ))).all()
        nodes, edges = {}, []
        for row in definitions:
            definition = json.loads(row.definition_json or "{}")
            node_id = f"semantic:{row.kind}:{row.semantic_key}"
            nodes[node_id] = {"id": node_id, "type": row.kind, "label": row.label, "status": row.status}
            binding = definition.get("binding", {})
            object_key = binding.get("object_key") or definition.get("field")
            if object_key:
                nodes.setdefault(object_key, {"id": object_key, "type": "schema", "label": object_key})
                edges.append({"source": node_id, "target": object_key, "type": "binds_to"})
        for row in paths:
            node_id = f"path:{row.id}"
            nodes[node_id] = {"id": node_id, "type": "query_path", "label": row.title, "status": row.status}
            dependencies = json.loads(row.dependencies_json or "{}")
            for object_key in dependencies.get("objects", []):
                nodes.setdefault(object_key, {"id": object_key, "type": "schema", "label": object_key})
                edges.append({"source": node_id, "target": object_key, "type": "depends_on"})
        return {"nodes": list(nodes.values()), "edges": edges}

    @staticmethod
    def normalize_question(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.lower())

    @staticmethod
    def _tokens(value: str) -> set[str]:
        normalized = ContextLearningService.normalize_question(value)
        latin = set(re.findall(r"[a-z0-9_]+", value.lower()))
        chinese = {normalized[index:index + 2] for index in range(max(0, len(normalized) - 1))}
        return latin | chinese

    @staticmethod
    def plan_dependencies(plan: QueryPlanV1) -> dict[str, Any]:
        return {
            "semantic_keys": sorted({f"{item.role}:{item.key}" for item in plan.semantic_bindings}),
            "objects": sorted({item.object_key for item in plan.semantic_bindings}),
            "tables": sorted({f"{item.schema_name}.{item.table_name}" for item in plan.semantic_bindings}),
        }

    @staticmethod
    def _path_dict(item: VerifiedQueryPathRecord) -> dict[str, Any]:
        return {
            "id": item.id, "source_id": item.source_id, "title": item.title,
            "question": item.question, "dependencies": json.loads(item.dependencies_json or "{}"),
            "schema_fingerprint": item.schema_fingerprint, "status": item.status,
            "confirmation_count": item.confirmation_count, "success_count": item.success_count,
            "reviewer": item.reviewer, "review_note": item.review_note,
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    def _feedback_dict(item: QueryFeedbackRecord) -> dict[str, Any]:
        return {
            "id": item.id, "execution_id": item.execution_id, "verdict": item.verdict,
            "issue_type": item.issue_type, "comment": item.comment,
            "review_status": item.review_status, "query_path_id": item.query_path_id or None,
            "reviewed_by": item.reviewed_by or None,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
            "created_at": item.created_at.isoformat(),
        }
