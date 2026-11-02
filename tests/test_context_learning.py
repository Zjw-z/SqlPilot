import asyncio
from datetime import date

from app.context_learning import ContextLearningService
from app.conversation.models import (
    ConversationRecord, DataSourceRecord, MessageRecord, PlanVersionRecord,
    QueryExecutionRecord,
)
from app.core.config import Settings
from app.data_sources import DataSourceService
from app.infrastructure.database import Database
from app.planning.models import DateRange, PlanProvenance, QueryPlanV1, SemanticBinding


def test_feedback_requires_review_then_reuses_and_schema_drift_invalidates(tmp_path):
    async def scenario():
        database = Database(Settings(
            system_database_url=f"sqlite+aiosqlite:///{(tmp_path / 'learning.db').as_posix()}"
        ))
        await database.initialize()
        plan = QueryPlanV1(
            intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=["institution"],
            date_range=DateRange(type="explicit", start=date(2026, 1, 1), end=date(2026, 12, 31)),
            semantic_bindings=[
                SemanticBinding(
                    role="metric", key="fund_pay_total", label="基金支付总额",
                    object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa",
                    table_name="setl_d", column_name="fund_pay_sumamt", aggregation="sum",
                    certified=True,
                ),
                SemanticBinding(
                    role="dimension", key="institution", label="医疗机构",
                    object_key="nhsa.setl_d.fixmedins_name", schema_name="nhsa",
                    table_name="setl_d", column_name="fixmedins_name", certified=True,
                ),
            ],
            provenance=PlanProvenance(model="test", prompt_version="test"),
        )
        async with database.sessions.begin() as session:
            source = DataSourceRecord(
                tenant_id="default", name="学习测试源", host="127.0.0.1", port=5432,
                database_name="test", username="test", status="ready",
                schema_fingerprint="fingerprint-v1",
            )
            session.add(source)
            await session.flush()
            plan.data_source_id = source.id
            conversation = ConversationRecord(
                tenant_id="default", user_id="local-user", title="基金查询", status="completed",
                current_plan_version=1,
            )
            session.add(conversation)
            await session.flush()
            session.add(MessageRecord(
                conversation_id=conversation.id, role="user",
                content="统计2026年各医疗机构基金支付总额",
            ))
            session.add(PlanVersionRecord(
                conversation_id=conversation.id, version=1, plan_json=plan.model_dump_json(),
                plan_hash=plan.stable_hash(), status="confirmed",
            ))
            execution = QueryExecutionRecord(
                conversation_id=conversation.id, plan_version=1, status="completed",
                sql_text='SELECT 1', result_json='{"rows": []}',
            )
            session.add(execution)
            await session.flush()
            assert DataSourceService._public(source)["schema_fingerprint"] == "fingerprint-v1"

        service = ContextLearningService(database.sessions)
        feedback = await service.submit_feedback(
            "default", "local-user", execution.id,
            {"verdict": "correct", "issue_type": "", "comment": "已与报表核对"},
        )
        assert feedback["review_status"] == "pending"
        assert await service.context(
            "default", source.id, "统计2026年各医疗机构基金支付总额", "fingerprint-v1"
        ) == []

        await service.review_feedback(
            "default", feedback["id"], "reviewer", {"decision": "approve", "note": "口径已确认"}
        )
        paths = await service.context(
            "default", source.id, "统计2026年各医疗机构基金支付总额", "fingerprint-v1"
        )
        exact = await service.find_exact_plan(
            "default", source.id, "统计2026年各医疗机构基金支付总额", "fingerprint-v1"
        )
        graph = await service.dependency_graph("default", source.id)
        assert paths[0]["status"] == "certified"
        assert exact and exact[0].metrics == ["fund_pay_total"]
        assert any(edge["type"] == "depends_on" for edge in graph["edges"])

        reopened = await service.submit_feedback(
            "default", "local-user", execution.id,
            {"verdict": "correct", "issue_type": "", "comment": "重新送审"},
        )
        assert reopened["review_status"] == "pending"
        assert reopened["reviewed_by"] is None
        assert (await service.list_paths("default", source.id))[0]["status"] == "draft"
        await service.review_feedback(
            "default", feedback["id"], "reviewer", {"decision": "approve", "note": "再次确认"}
        )

        invalidated = await service.invalidate_for_schema_change(
            "default", source.id, "fingerprint-v1", "fingerprint-v2"
        )
        assert invalidated == 1
        assert (await service.list_paths("default", source.id))[0]["status"] == "stale"
        assert await service.find_exact_plan(
            "default", source.id, "统计2026年各医疗机构基金支付总额", "fingerprint-v2"
        ) is None
        await database.close()

    asyncio.run(scenario())
