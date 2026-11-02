from datetime import date

import pytest

from app.planning.models import (
    Comparison,
    DateRange,
    PlanProvenance,
    QueryFilter,
    QueryPlanV1,
    SemanticBinding,
)
from app.text_to_sql.compiler import DeterministicQueryCompiler
from app.text_to_sql.schema import ColumnInfo, SchemaContext, TableInfo
from app.text_to_sql.validator import PostgresSqlValidator


def context() -> SchemaContext:
    return SchemaContext([
        TableInfo("nhsa", "setl_d", columns=[
            ColumnInfo("setl_time", "character varying", False, "结算时间 yyyy-MM-dd HH:mm:ss"),
            ColumnInfo("fund_pay_sumamt", "numeric", True),
            ColumnInfo("medfee_sumamt", "numeric", True),
            ColumnInfo("setl_id", "character varying", False),
            ColumnInfo("med_type", "character varying", True),
            ColumnInfo("vali_flag", "character varying", True),
            ColumnInfo("refd_setl_flag", "character varying", True),
        ])
    ], [])


def multi_metric_yoy_plan() -> QueryPlanV1:
    return QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total", "total_fee", "settlement_count"],
        dimensions=["month"],
        date_range=DateRange(
            type="explicit", start=date(2026, 1, 1), end=date(2026, 8, 27),
            comparison_start=date(2025, 1, 1), comparison_end=date(2025, 8, 27),
        ),
        filters=[QueryFilter(
            field="nhsa.setl_d.med_type", operator="in",
            value=["21", "22", "23", "24", "52", "92"], display_value="住院（所有类型）",
        )],
        comparison=Comparison(type="year_over_year", grain="month"),
        default_policies=["valid_settlement_only", "exclude_cancelled"],
        semantic_bindings=[
            SemanticBinding(role="metric", key="fund_pay_total", label="基金支付总额", object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa", table_name="setl_d", column_name="fund_pay_sumamt", aggregation="sum"),
            SemanticBinding(role="metric", key="total_fee", label="医疗总费用", object_key="nhsa.setl_d.medfee_sumamt", schema_name="nhsa", table_name="setl_d", column_name="medfee_sumamt", aggregation="sum"),
            SemanticBinding(role="metric", key="settlement_count", label="结算人次", object_key="nhsa.setl_d.setl_id", schema_name="nhsa", table_name="setl_d", column_name="setl_id", aggregation="count_distinct"),
            SemanticBinding(role="dimension", key="month", label="月份", object_key="nhsa.setl_d.setl_time", schema_name="nhsa", table_name="setl_d", column_name="setl_time", aggregation="none"),
            SemanticBinding(role="filter", key="med_type", label="医疗类别", object_key="nhsa.setl_d.med_type", schema_name="nhsa", table_name="setl_d", column_name="med_type", aggregation="none"),
        ],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )


def test_compiles_multi_metric_monthly_yoy_without_llm():
    plan = multi_metric_yoy_plan()

    compiled = DeterministicQueryCompiler().compile(plan, context())

    assert compiled is not None
    assert compiled.strategy == "deterministic_ir_v1"
    assert 'SUM(t."fund_pay_sumamt") AS "fund_pay_total"' in compiled.sql
    assert 'COUNT(DISTINCT t."setl_id") AS "settlement_count"' in compiled.sql
    assert 'INTERVAL \'1 year\'' in compiled.sql
    assert '"fund_pay_total_yoy_rate"' in compiled.sql
    assert all(code in compiled.sql for code in ("'21'", "'22'", "'23'", "'24'", "'52'", "'92'"))
    assert "2026-08-28" in compiled.sql and "2025-08-28" in compiled.sql
    assert 't."vali_flag" = \'1\'' in compiled.sql


def test_compiled_query_passes_existing_security_and_plan_validator():
    plan = multi_metric_yoy_plan()
    compiled = DeterministicQueryCompiler().compile(plan, context())

    validation = PostgresSqlValidator().validate(compiled.sql, context(), plan)

    assert validation.valid, validation.errors


def test_compiler_escapes_filter_literals():
    plan = multi_metric_yoy_plan()
    plan.comparison = Comparison(type="none")
    plan.filters[0].operator = "eq"
    plan.filters[0].value = "O'Reilly"

    compiled = DeterministicQueryCompiler().compile(plan, context())

    assert "O''Reilly" in compiled.sql


def test_multi_table_plan_uses_controlled_fallback():
    plan = multi_metric_yoy_plan()
    plan.semantic_bindings[1].table_name = "other_table"
    plan.semantic_bindings[1].object_key = "nhsa.other_table.medfee_sumamt"

    assert DeterministicQueryCompiler().compile(plan, context()) is None


@pytest.mark.parametrize("grain", ["day", "week", "month", "quarter", "year"])
def test_compiles_natural_grain_yoy_deterministically(grain):
    plan = multi_metric_yoy_plan()
    plan.dimensions = [grain]
    plan.comparison = Comparison(type="year_over_year", grain=grain)
    dimension = next(item for item in plan.semantic_bindings if item.role == "dimension")
    dimension.key = grain
    dimension.label = grain

    compiled = DeterministicQueryCompiler().compile(plan, context())

    assert compiled is not None
    assert f"DATE_TRUNC('{grain}'" in compiled.sql
    assert 'AS "fund_pay_total_yoy_rate"' in compiled.sql
    if grain == "week":
        assert "EXTRACT(ISOYEAR" in compiled.sql
        assert "EXTRACT(WEEK" in compiled.sql
    else:
        assert "INTERVAL '1 year'" in compiled.sql


@pytest.mark.parametrize("grain", ["day", "week", "month", "quarter", "year"])
def test_compiles_natural_period_over_period_with_leading_period(grain):
    plan = multi_metric_yoy_plan()
    plan.dimensions = [grain]
    plan.comparison = Comparison(type="month_over_month", grain=grain)
    dimension = next(item for item in plan.semantic_bindings if item.role == "dimension")
    dimension.key = grain
    dimension.label = grain

    compiled = DeterministicQueryCompiler().compile(plan, context())

    assert compiled is not None
    assert f"DATE_TRUNC('{grain}'" in compiled.sql
    expected_interval = "3 months" if grain == "quarter" else f"1 {grain}"
    assert f"INTERVAL '{expected_interval}'" in compiled.sql
    assert f'ORDER BY "{grain}"' in compiled.sql
    assert "LAG(" not in compiled.sql
    assert "LEFT JOIN period_data AS p" in compiled.sql
    assert f'p."{grain}" = c."{grain}" - INTERVAL \'{expected_interval}\'' in compiled.sql
    assert 'AS "fund_pay_total_mom_rate"' in compiled.sql
    # A missing immediately previous period stays NULL; it cannot jump to an older row.
    assert f'WHERE c."{grain}" >= DATE_TRUNC' in compiled.sql
