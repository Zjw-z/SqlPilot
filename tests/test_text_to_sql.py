from datetime import date

from app.planning.models import Comparison, DateRange, PlanProvenance, QueryFilter, QueryPlanV1, QuerySemantics, Ranking, SchemaEvidence
from app.text_to_sql.schema import ColumnInfo, SchemaContext, TableInfo
from app.text_to_sql.validator import PostgresSqlValidator
from app.text_to_sql.engine import PostgresTextToSqlEngine
from app.text_to_sql.generator import BailianSqlGenerator


def yoy_plan() -> QueryPlanV1:
    return QueryPlanV1(
        intent="aggregate_analysis",
        metric="fund_pay_total",
        dimensions=["month", "institution"],
        date_range=DateRange(
            type="explicit",
            start=date(2026, 1, 1),
            end=date(2026, 8, 25),
            comparison_start=date(2025, 1, 1),
            comparison_end=date(2025, 8, 25),
        ),
        comparison=Comparison(type="year_over_year", grain="month"),
        ranking=Ranking(metric="yoy_rate", scope="within_institution"),
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )


def context() -> SchemaContext:
    return SchemaContext(
        [TableInfo("nhsa", "setl_d", columns=[
            ColumnInfo("setl_time", "varchar", False),
            ColumnInfo("fund_pay_sumamt", "numeric", False),
            ColumnInfo("fixmedins_name", "varchar", False),
        ])],
        [],
    )


def test_rejects_yoy_without_comparison_period():
    sql = """SELECT fixmedins_name, fund_pay_sumamt AS yoy_rate
    FROM nhsa.setl_d WHERE setl_time >= '2026-01-01' AND setl_time <= '2026-08-25'
    ORDER BY yoy_rate DESC"""
    validation = PostgresSqlValidator().validate(sql, context(), yoy_plan())
    assert not validation.valid
    assert any("同期开始日期" in error for error in validation.errors)


def test_rejects_reversed_yoy_join_and_non_percentage():
    sql = """WITH c AS (SELECT setl_time, fund_pay_sumamt, fixmedins_name FROM nhsa.setl_d
    WHERE setl_time BETWEEN '2026-01-01' AND '2026-08-25'),
    y AS (SELECT setl_time, fund_pay_sumamt, fixmedins_name FROM nhsa.setl_d
    WHERE setl_time BETWEEN '2025-01-01' AND '2025-08-25')
    SELECT c.fixmedins_name, c.fund_pay_sumamt AS yoy_rate FROM c JOIN y
    ON c.setl_time = y.setl_time - INTERVAL '1 year' ORDER BY yoy_rate DESC"""
    validation = PostgresSqlValidator().validate(sql, context(), yoy_plan())
    assert not validation.valid
    assert any("方向错误" in error for error in validation.errors)
    assert any("百分比" in error for error in validation.errors)


def test_rejects_unrequested_yoy_and_missing_plan_period():
    plan = yoy_plan().model_copy(deep=True)
    plan.comparison.type = "none"
    plan.ranking.metric = "metric_value"
    plan.metrics = ["fund_pay_total"]
    sql = """SELECT fixmedins_name, fund_pay_sumamt AS fund_pay_total,
    fund_pay_sumamt AS fund_pay_total_yoy_rate FROM nhsa.setl_d"""

    validation = PostgresSqlValidator().validate(sql, context(), plan)

    assert any("不得擅自增加同比" in error for error in validation.errors)
    assert any("开始日期" in error for error in validation.errors)
    assert any("结束日期" in error for error in validation.errors)


def test_trust_score_reflects_rag_ambiguity_instead_of_being_constant():
    plan = yoy_plan()
    plan.schema_evidence = [
        SchemaEvidence(object_key="nhsa.setl_d.fund_pay_sumamt", score=0.49, requires_confirmation=True),
        SchemaEvidence(object_key="nhsa.setl_d.hifp_pay", score=0.48, requires_confirmation=True),
    ]
    validation = type("Validation", (), {"passed": ["只读校验通过"]})()

    trust = PostgresTextToSqlEngine._trust_result(plan, context(), validation, 1)

    assert trust["score"] < 0.9
    assert trust["level"] in {"B", "C", "D"}
    assert "Schema语义召回置信度偏低" in trust["risks"]
    assert "存在未由语义绑定消解的相近字段" in trust["risks"]


def test_rejects_wrong_schema_and_column_owned_by_another_table():
    other = TableInfo("nhsa", "other_d", columns=[ColumnInfo("secret_value", "text", True)])
    ctx = SchemaContext(context().tables + [other], [])

    wrong_schema = PostgresSqlValidator().validate(
        "SELECT fund_pay_sumamt FROM public.setl_d", ctx
    )
    wrong_owner = PostgresSqlValidator().validate(
        "SELECT s.secret_value FROM nhsa.setl_d s", ctx
    )

    assert any("未授权" in item for item in wrong_schema.errors)
    assert any("不属于指定表" in item for item in wrong_owner.errors)


def test_rejects_unplanned_order_and_missing_filter_value():
    plan = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=["institution"],
        date_range=DateRange(type="explicit", start=date(2026, 1, 1), end=date(2026, 8, 25)),
        filters=[QueryFilter(field="nhsa.setl_d.setl_time", operator="eq", value="required-value", display_value="测试值")],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    sql = """SELECT fixmedins_name, SUM(fund_pay_sumamt) AS fund_pay_total
    FROM nhsa.setl_d WHERE setl_time >= '2026-01-01' AND setl_time <= '2026-08-25'
    GROUP BY fixmedins_name ORDER BY fund_pay_total DESC"""

    validation = PostgresSqlValidator().validate(sql, context(), plan)

    assert any("不得擅自增加顶层排序" in item for item in validation.errors)
    assert any("缺少计划过滤值" in item for item in validation.errors)


def test_allows_dimension_order_and_month_number_yoy_alignment():
    plan = yoy_plan().model_copy(deep=True)
    plan.dimensions = ["month"]
    plan.ranking = Ranking()
    sql = """WITH current_data AS (
      SELECT EXTRACT(MONTH FROM setl_time) AS month, SUM(fund_pay_sumamt) AS current_value
      FROM nhsa.setl_d WHERE setl_time >= '2026-01-01' AND setl_time <= '2026-08-25'
      GROUP BY EXTRACT(MONTH FROM setl_time)
    ), year_ago_data AS (
      SELECT EXTRACT(MONTH FROM setl_time) AS month, SUM(fund_pay_sumamt) AS previous_value
      FROM nhsa.setl_d WHERE setl_time >= '2025-01-01' AND setl_time <= '2025-08-25'
      GROUP BY EXTRACT(MONTH FROM setl_time)
    )
    SELECT c.month, c.current_value AS fund_pay_total,
      ROUND((c.current_value-y.previous_value)*100.0/NULLIF(y.previous_value,0),2) AS yoy_rate
    FROM current_data c JOIN year_ago_data y ON c.month = y.month
    ORDER BY c.month"""

    validation = PostgresSqlValidator().validate(sql, context(), plan)

    assert validation.valid, validation.errors


def test_engine_always_wraps_query_with_hard_row_limit():
    engine = object.__new__(PostgresTextToSqlEngine)
    engine.settings = type("Settings", (), {"query_max_rows": 500})()

    bounded = engine._bounded_sql("SELECT * FROM nhsa.setl_d;")

    assert bounded.endswith("LIMIT 501")
    assert "AS sqlpilot_bounded" in bounded


def test_typed_semantics_rejects_wrong_projection_and_missing_grouping():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=["institution"],
        date_range=DateRange(type="all"), provenance=PlanProvenance(model="test", prompt_version="test"),
        semantics=QuerySemantics(entity_grain="institution", output_fields=["institution", "fund_pay_total"],
                                 group_by=["institution"], confidence=.9),
    )
    validation = PostgresSqlValidator().validate(
        "SELECT SUM(fund_pay_sumamt) AS fund_pay_total FROM nhsa.setl_d", context(), plan
    )
    assert any("输出列数量" in item for item in validation.errors)
    assert any("缺少GROUP BY" in item for item in validation.errors)


def test_sql_candidates_are_deduplicated_and_keep_stable_model_rank():
    candidates = BailianSqlGenerator._normalize_candidates([
        " SELECT name FROM main.singer; ",
        "SELECT  name  FROM main.singer",
        "SELECT age FROM main.singer;",
        None,
    ], 3)
    assert candidates == ["SELECT name FROM main.singer", "SELECT age FROM main.singer"]
