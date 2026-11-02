import asyncio
import json
from datetime import date
from pathlib import Path

from app.conversation.models import DataSourceRecord
from app.core.config import Settings
from app.infrastructure.database import Database
from app.planning.models import DateRange, PlanProvenance, QueryPlanV1, SemanticBinding
from app.semantic_layer import SemanticLayerService


def test_initial_nhsa_catalog_definitions_are_valid_and_unsafe_defaults_stay_draft():
    catalog = json.loads((Path(__file__).parents[1] / "data" / "semantic" / "nhsa_initial_catalog.json").read_text(encoding="utf-8"))
    for payload in catalog:
        SemanticLayerService._validate_definition(payload)
    draft_keys = {item["semantic_key"] for item in catalog if item["status"] == "draft"}
    assert {"default_statistics_time", "valid_settlement_scope", "exclude_refund_scope",
            "mid_settlement_scope"}.issubset(draft_keys)
    certified = {item["semantic_key"] for item in catalog if item["status"] == "certified"}
    assert {"fund_pay_total", "hifp_pay_total", "total_fee", "settlement_count"}.issubset(certified)
    assert next(item for item in catalog if item["semantic_key"] == "total_medical_fee")["status"] == "disabled"


def test_certified_definition_overrides_model_binding_and_confirmation_is_observed(tmp_path):
    async def scenario():
        database = Database(Settings(
            system_database_url=f"sqlite+aiosqlite:///{(tmp_path / 'semantic.db').as_posix()}"
        ))
        await database.initialize()
        async with database.sessions.begin() as session:
            source = DataSourceRecord(
                tenant_id="default", name="测试源", host="127.0.0.1", port=5432,
                database_name="test", username="test", status="ready",
            )
            session.add(source)
        service = SemanticLayerService(database.sessions)
        binding = {
            "role": "metric", "key": "fund_pay_total", "label": "医保基金支付总额",
            "object_key": "nhsa.setl_d.fund_pay_sumamt", "schema_name": "nhsa",
            "table_name": "setl_d", "column_name": "fund_pay_sumamt", "aggregation": "sum",
        }
        saved = await service.upsert_definition("default", source.id, {
            "kind": "metric", "semantic_key": "fund_pay_total", "label": "医保基金支付总额",
            "definition": {"binding": binding}, "status": "certified",
        })
        documents = await service.retrieval_documents("default", source.id)
        plan = QueryPlanV1(
            intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=[],
            date_range=DateRange(type="explicit", start=date(2026, 1, 1), end=date(2026, 1, 31)),
            data_source_id=source.id,
            semantic_bindings=[SemanticBinding(
                role="metric", key="fund_pay_total", label="错误字段", object_key="nhsa.setl_d.hifp_pay",
                schema_name="nhsa", table_name="setl_d", column_name="hifp_pay", aggregation="sum",
            )],
            provenance=PlanProvenance(model="test", prompt_version="test"),
        )

        applied = await service.apply_certified("default", plan)
        await service.observe_confirmation("default", plan)
        observations = await service.observations("default", source.id)
        capabilities = service.compiler_capabilities()
        await database.close()

        assert saved["status"] == "certified"
        assert documents[0]["object_key"] == "nhsa.setl_d.fund_pay_sumamt"
        assert documents[0]["metadata"]["certified"] is True
        assert applied == ["metric:fund_pay_total"]
        assert plan.semantic_bindings[0].column_name == "fund_pay_sumamt"
        assert plan.semantic_bindings[0].certified is True
        assert observations[0]["confirmation_count"] == 1
        assert capabilities["fallback"]["requires_validation"] is True

    asyncio.run(scenario())


def test_value_set_definition_maps_business_label_to_codes(tmp_path):
    async def scenario():
        database = Database(Settings(
            system_database_url=f"sqlite+aiosqlite:///{(tmp_path / 'values.db').as_posix()}"
        ))
        await database.initialize()
        async with database.sessions.begin() as session:
            source = DataSourceRecord(
                tenant_id="default", name="码值测试源", host="127.0.0.1", port=5432,
                database_name="test", username="test", status="ready",
            )
            session.add(source)
        service = SemanticLayerService(database.sessions)
        await service.upsert_definition("default", source.id, {
            "kind": "value_set", "semantic_key": "med_type", "label": "医疗类别",
            "definition": {"values": {"住院": ["21", "22", "23", "24", "52", "92"]}},
            "status": "certified",
        })
        plan = QueryPlanV1(
            intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=[],
            date_range=DateRange(type="all"), data_source_id=source.id,
            filters=[{"field": "nhsa.setl_d.med_type", "value": "住院", "display_value": "住院"}],
            provenance=PlanProvenance(model="test", prompt_version="test"),
        )

        await service.apply_certified("default", plan)
        await database.close()

        assert plan.filters[0].operator == "in"
        assert plan.filters[0].value == ["21", "22", "23", "24", "52", "92"]

    asyncio.run(scenario())


def test_business_rules_and_golden_queries_can_be_managed(tmp_path):
    async def scenario():
        database = Database(Settings(
            system_database_url=f"sqlite+aiosqlite:///{(tmp_path / 'governance.db').as_posix()}"
        ))
        await database.initialize()
        async with database.sessions.begin() as session:
            source = DataSourceRecord(
                tenant_id="default", name="治理测试源", host="127.0.0.1", port=5432,
                database_name="test", username="test", status="ready",
            )
            session.add(source)
        service = SemanticLayerService(database.sessions)
        rule = await service.upsert_definition("default", source.id, {
            "kind": "business_rule", "semantic_key": "default_time", "label": "默认统计时间",
            "definition": {"rule_type": "time_semantics", "field": "nhsa.setl_d.setl_time",
                           "operator": "use_as_default", "value": "settlement_time"},
            "status": "certified",
        })
        case = await service.upsert_definition("default", source.id, {
            "kind": "golden_query", "semantic_key": "case_monthly_fund", "label": "月度基金对账",
            "definition": {"question": "统计月度基金支付总额", "expected": {"row_count": 12},
                           "notes": "与财务月报核对"}, "status": "draft",
        })
        rows = await service.list_definitions("default", source.id)
        await database.close()
        assert rule["definition"]["rule_type"] == "time_semantics"
        assert case["definition"]["expected"]["row_count"] == 12
        assert {item["kind"] for item in rows} == {"business_rule", "golden_query"}

    asyncio.run(scenario())
