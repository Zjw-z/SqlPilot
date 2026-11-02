from datetime import date

import pytest

from app.planning.models import Comparison, DateRange, PlanProvenance, QueryPlanV1, Ranking, SemanticBinding
from app.text_to_sql.capability_router import CapabilityRouter
from app.text_to_sql.schema import ColumnInfo, Relationship, SchemaContext, TableInfo
from app.text_to_sql.validator import PostgresSqlValidator


def plan() -> QueryPlanV1:
    return QueryPlanV1(
        intent="aggregate_analysis", metrics=["total_fee"], dimensions=["institution"],
        date_range=DateRange(type="all"),
        semantic_bindings=[
            SemanticBinding(role="metric", key="total_fee", label="医疗总费用",
                object_key="nhsa.setl_d.medfee_sumamt", schema_name="nhsa", table_name="setl_d",
                column_name="medfee_sumamt", aggregation="sum"),
            SemanticBinding(role="dimension", key="institution", label="医疗机构",
                object_key="nhsa.setl_d.fixmedins_name", schema_name="nhsa", table_name="setl_d",
                column_name="fixmedins_name"),
        ], provenance=PlanProvenance(model="test", prompt_version="test"),
    )


def context(with_relation: bool = False) -> SchemaContext:
    relationships = [Relationship("setl_d", "setl_id", "fee_list_d", "setl_id")] if with_relation else []
    return SchemaContext([
        TableInfo("nhsa", "setl_d", columns=[
            ColumnInfo("medfee_sumamt", "numeric", True),
            ColumnInfo("fixmedins_name", "varchar", True), ColumnInfo("setl_id", "varchar", False),
        ]),
        TableInfo("nhsa", "fee_list_d", columns=[
            ColumnInfo("setl_id", "varchar", False), ColumnInfo("drug_name", "varchar", True),
        ]),
    ], relationships)


def test_routes_supported_single_table_plan_to_deterministic_compiler():
    decision = CapabilityRouter().decide(plan(), context())
    assert decision.route == "deterministic"
    assert decision.compiled is not None


def test_missing_binding_is_clarified_instead_of_sent_to_model():
    value = plan()
    value.semantic_bindings = [item for item in value.semantic_bindings if item.role != "metric"]
    decision = CapabilityRouter().decide(value, context())
    assert decision.route == "clarify"
    assert decision.reason_code == "MISSING_SEMANTIC_BINDING"
    assert "metric:total_fee" in decision.missing


def test_stale_schema_binding_requires_resync_instead_of_model_guess():
    value = plan()
    value.semantic_bindings[0].column_name = "removed_column"
    value.semantic_bindings[0].object_key = "nhsa.setl_d.removed_column"
    decision = CapabilityRouter().decide(value, context())
    assert decision.route == "resync_schema"
    assert decision.reason_code == "SCHEMA_OBJECT_NOT_FOUND"


def test_mom_without_month_dimension_never_silently_degrades():
    value = plan()
    value.comparison = Comparison(type="month_over_month", grain="month")
    decision = CapabilityRouter().decide(value, context())
    assert decision.route == "clarify"
    assert decision.reason_code == "PERIOD_COMPARISON_REQUIRES_TIME_DIMENSION"


def test_multitable_requires_verified_join_before_model_fallback():
    value = plan()
    value.dimensions.append("drug")
    value.semantic_bindings.append(SemanticBinding(
        role="dimension", key="drug", label="药品", object_key="nhsa.fee_list_d.drug_name",
        schema_name="nhsa", table_name="fee_list_d", column_name="drug_name",
    ))
    blocked = CapabilityRouter().decide(value, context(with_relation=False))
    allowed = CapabilityRouter().decide(value, context(with_relation=True))
    assert blocked.route == "clarify" and blocked.reason_code == "UNVERIFIED_JOIN_PATH"
    assert allowed.route == "model_fallback"
    assert "multi_table" in allowed.unsupported_capabilities


def test_metric_without_aggregation_is_clarified():
    value = plan()
    value.semantic_bindings[0].aggregation = "none"
    decision = CapabilityRouter().decide(value, context())
    assert decision.route == "clarify"
    assert decision.reason_code == "MISSING_METRIC_AGGREGATION"


def test_partitioned_top_n_uses_model_instead_of_incorrect_global_limit():
    value = plan()
    value.dimensions.append("month")
    value.semantic_bindings.append(SemanticBinding(
        role="time", key="settlement_time", label="结算时间",
        object_key="nhsa.setl_d.setl_time", schema_name="nhsa", table_name="setl_d",
        column_name="setl_time",
    ))
    value.ranking = Ranking(metric="metric_value", direction="desc", scope="within_institution", limit=3)
    ctx = context()
    ctx.tables[0].columns.append(ColumnInfo("setl_time", "timestamp", True))

    decision = CapabilityRouter().decide(value, ctx)

    assert decision.route == "model_fallback"
    assert "partitioned_ranking" in decision.unsupported_capabilities


@pytest.mark.parametrize("group_key,column_name", [("district", "district_name"), ("institution", "fixmedins_name")])
def test_each_group_top_n_requires_explicit_partition_and_model_route(group_key, column_name):
    value = plan()
    if group_key != "institution":
        value.dimensions.append(group_key)
        value.semantic_bindings.append(SemanticBinding(
            role="dimension", key=group_key, label="区县", object_key=f"nhsa.setl_d.{column_name}",
            schema_name="nhsa", table_name="setl_d", column_name=column_name,
        ))
    value.ranking = Ranking(scope="within_dimension", partition_by=[group_key], limit=3)
    ctx = context()
    if group_key == "district":
        ctx.tables[0].columns.append(ColumnInfo(column_name, "varchar", True))

    decision = CapabilityRouter().decide(value, ctx)

    assert decision.route == "model_fallback"
    assert "partitioned_ranking" in decision.unsupported_capabilities
    assert decision.compiled is None


def test_district_top_n_sql_rejects_global_limit_and_accepts_partitioned_rank():
    value = plan()
    value.dimensions.append("district")
    value.semantic_bindings.append(SemanticBinding(
        role="dimension", key="district", label="区县", object_key="nhsa.setl_d.district_name",
        schema_name="nhsa", table_name="setl_d", column_name="district_name",
    ))
    value.ranking = Ranking(scope="within_dimension", partition_by=["district"], limit=3)
    ctx = context()
    ctx.tables[0].columns.append(ColumnInfo("district_name", "varchar", True))
    bad_sql = (
        'SELECT district_name AS district, SUM(medfee_sumamt) AS total_fee '
        'FROM nhsa.setl_d GROUP BY district_name ORDER BY total_fee DESC LIMIT 3'
    )
    good_sql = (
        'WITH totals AS (SELECT district_name AS district, fixmedins_name AS institution, '
        'SUM(medfee_sumamt) AS total_fee FROM nhsa.setl_d '
        'GROUP BY district_name, fixmedins_name), '
        'ranked AS (SELECT district, institution, total_fee, '
        'ROW_NUMBER() OVER (PARTITION BY district ORDER BY total_fee DESC) AS rank_no FROM totals) '
        'SELECT district, institution, total_fee FROM ranked WHERE rank_no <= 3'
    )

    assert any("PARTITION BY" in error for error in PostgresSqlValidator().validate(bad_sql, ctx, value).errors)
    assert PostgresSqlValidator().validate(good_sql, ctx, value).valid


@pytest.mark.parametrize("grain", ["day", "week", "month", "quarter", "year"])
@pytest.mark.parametrize("comparison_type", ["year_over_year", "month_over_month"])
def test_natural_time_comparisons_use_deterministic_route(grain, comparison_type):
    value = plan()
    value.date_range = DateRange(
        type="explicit", start=date(2026, 1, 1), end=date(2026, 8, 31),
        comparison_start=date(2025, 1, 1), comparison_end=date(2025, 8, 31),
    )
    value.dimensions.append(grain)
    value.comparison = Comparison(type=comparison_type, grain=grain)
    value.semantic_bindings.append(SemanticBinding(
        role="time", key="settlement_time", label="结算时间",
        object_key="nhsa.setl_d.setl_time", schema_name="nhsa", table_name="setl_d",
        column_name="setl_time",
    ))
    ctx = context()
    ctx.tables[0].columns.append(ColumnInfo("setl_time", "timestamp", True))

    decision = CapabilityRouter().decide(value, ctx)

    assert decision.route == "deterministic", decision.evidence()


def test_period_total_is_supported_for_yoy_but_rejected_for_period_over_period():
    yoy = plan()
    yoy.date_range = DateRange(
        type="explicit", start=date(2026, 1, 1), end=date(2026, 8, 31),
        comparison_start=date(2025, 1, 1), comparison_end=date(2025, 8, 31),
    )
    yoy.comparison = Comparison(type="year_over_year", grain="period_total")
    yoy.semantic_bindings.append(SemanticBinding(
        role="time", key="settlement_time", label="结算时间",
        object_key="nhsa.setl_d.setl_time", schema_name="nhsa", table_name="setl_d",
        column_name="setl_time",
    ))
    yoy_context = context()
    yoy_context.tables[0].columns.append(ColumnInfo("setl_time", "timestamp", True))
    assert CapabilityRouter().decide(yoy, yoy_context).route == "deterministic"

    period_over_period = plan()
    period_over_period.comparison = Comparison(type="month_over_month", grain="period_total")
    decision = CapabilityRouter().decide(period_over_period, context())
    assert decision.route == "clarify"
    assert decision.reason_code == "PERIOD_COMPARISON_GRAIN_REQUIRED"
