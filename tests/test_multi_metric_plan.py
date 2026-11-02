from datetime import date

from app.core.config import Settings
from app.planning.bailian import BailianQueryPlanner, PlanningDraft
from app.planning.models import DateRange, PlanProvenance, QueryPlanV1, SemanticBinding
from app.planning.summarizer import summarize_plan
from app.conversation.service import ConversationService


def test_plan_supports_multiple_metrics_and_keeps_legacy_metric():
    plan = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["settlement_count", "total_fee", "fund_pay_total"],
        dimensions=["institution"],
        date_range=DateRange(type="current_year_to_date", start=date(2026, 1, 1), end=date(2026, 8, 25)),
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert plan.metric == "settlement_count"
    assert "结算人次、医疗总费用、医保基金支付总额" in summarize_plan(plan)


def test_unrelated_revision_does_not_retain_previous_query_plan():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    current = QueryPlanV1(
        intent="aggregate_analysis", metrics=["total_fee"], dimensions=["institution"],
        date_range=DateRange(type="current_year_to_date", start=date(2026, 1, 1), end=date(2026, 10, 13)),
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    draft = PlanningDraft(
        intent="unsupported", dimensions=[], date_type="all", changed_fields=["intent"],
    )

    plan = planner._normalize(draft, "今天天气怎么样", current_plan=current)

    assert plan.intent == "unsupported"
    assert plan.metrics == []
    assert plan.dimensions == []
    assert plan.date_range.type == "all"
    assert summarize_plan(plan) == "当前问题不属于可执行的数据查询"


def test_model_selected_metrics_resolve_metric_clarification_without_keyword_override():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    draft = PlanningDraft(
        intent="aggregate_analysis", dimensions=["institution"], date_type="current_year_to_date",
        metrics=["settlement_count", "total_fee", "fund_pay_total"],
        clarifications=[{"id": "metric", "question": "统计哪些指标？", "reason": "未确定", "options": []}],
        changed_fields=["metrics", "clarifications"],
    )

    plan = planner._normalize(draft, "用户补充：这几个指标都统计")

    assert set(plan.metrics) == {"settlement_count", "total_fee", "fund_pay_total"}
    assert not plan.clarifications


def test_period_total_yoy_does_not_require_month_or_ranking():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    draft = PlanningDraft(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=["institution"],
        date_type="current_year_to_date",
        comparison_type="year_over_year",
        comparison_grain="period_total",
        changed_fields=["comparison", "dimensions"],
    )

    plan = planner._normalize(draft, "按年度累计，不按月份拆分")

    assert plan.dimensions == ["institution"]
    assert plan.comparison.grain == "period_total"
    assert plan.ranking.metric == "metric_value"
    assert plan.ranking.scope is None
    assert not plan.clarifications
    assert "按当前期间累计与上年同期进行同比并计算增长率" in summarize_plan(plan)


def test_revision_that_only_adds_yoy_derives_comparison_period():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    current = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total", "total_fee", "settlement_count"],
        dimensions=["institution"],
        date_range=DateRange(
            type="explicit", start=date(2026, 1, 1), end=date(2026, 12, 31)
        ),
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    draft = PlanningDraft(
        intent="aggregate_analysis",
        metrics=current.metrics,
        dimensions=current.dimensions,
        date_type="explicit",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        comparison_type="year_over_year",
        comparison_grain="period_total",
        changed_fields=["comparison"],
    )

    plan = planner._normalize(draft, "和往期同比一下吧", current_plan=current)

    assert plan.date_range.comparison_start == date(2025, 1, 1)
    assert plan.date_range.comparison_end == date(2025, 12, 31)


def test_planner_normalization_handles_february_29_yoy():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    draft = PlanningDraft(
        intent="aggregate_analysis", metrics=["settlement_count"],
        dimensions=["day"], changed_fields=["comparison", "date_range", "dimensions"],
        date_type="explicit", start_date=date(2024, 2, 29), end_date=date(2024, 2, 29),
        comparison_type="year_over_year", comparison_grain="day",
    )

    plan = planner._normalize(draft, "统计2024年2月29日同比")

    assert plan.date_range.comparison_start == date(2023, 2, 28)
    assert plan.date_range.comparison_end == date(2023, 2, 28)


def test_yoy_period_derivation_handles_leap_day():
    plan = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["settlement_count"],
        date_range=DateRange(
            type="explicit", start=date(2024, 2, 29), end=date(2024, 2, 29)
        ),
        comparison={"type": "year_over_year", "grain": "day"},
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert plan.date_range.comparison_start == date(2023, 2, 28)
    assert plan.date_range.comparison_end == date(2023, 2, 28)


def test_growth_rate_phrase_does_not_create_ranking_clarification():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    draft = PlanningDraft(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=["institution"],
        date_type="current_year_to_date",
        comparison_type="year_over_year",
        comparison_grain="period_total",
        changed_fields=["comparison"],
    )

    plan = planner._normalize(draft, "和去年同期比较，计算同比增长率")

    assert plan.ranking.metric == "metric_value"
    assert plan.ranking.scope is None
    assert not plan.clarifications


def test_revision_change_set_preserves_unmentioned_institution_dimension():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    current = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=["month", "institution"],
        date_range=DateRange(type="current_year_to_date", start=date(2026, 1, 1), end=date(2026, 8, 26)),
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    draft = PlanningDraft(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=[],
        date_type="current_year_to_date",
        comparison_type="year_over_year",
        comparison_grain="period_total",
        changed_fields=["dimensions", "comparison"],
    )
    plan = planner._normalize(draft, "按年度累计，不按月份拆分", current_plan=current)

    assert plan.dimensions == ["institution"]
    assert plan.comparison.grain == "period_total"
    assert plan.metrics == ["fund_pay_total"]


def test_revision_cannot_cancel_existing_comparison_without_explicit_request():
    planner = BailianQueryPlanner(Settings(dashscope_api_key="test"))
    current = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=["institution"],
        date_range=DateRange(
            type="current_year_to_date",
            start=date(2026, 1, 1),
            end=date(2026, 8, 26),
            comparison_start=date(2025, 1, 1),
            comparison_end=date(2025, 8, 26),
        ),
        comparison={"type": "year_over_year", "grain": "month"},
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    draft = PlanningDraft(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=[],
        date_type="current_year_to_date",
        comparison_type="none",
        changed_fields=["dimensions", "comparison"],
    )

    plan = planner._normalize(draft, "按年度累计，不按月份拆分", current_plan=current)

    assert plan.dimensions == ["institution"]
    assert plan.comparison.type == "year_over_year"
    assert plan.comparison.grain == "period_total"


def test_plan_accepts_dynamic_metric_with_auditable_schema_binding():
    plan = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["hifp_pay_total"],
        dimensions=["institution"],
        date_range=DateRange(type="all"),
        semantic_bindings=[SemanticBinding(
            role="metric",
            key="hifp_pay_total",
            label="统筹基金支出",
            object_key="nhsa.setl_d.hifp_pay",
            schema_name="nhsa",
            table_name="setl_d",
            column_name="hifp_pay",
            aggregation="sum",
            confidence=0.91,
            certified=True,
        )],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert plan.metrics == ["hifp_pay_total"]
    assert "统筹基金支出" in summarize_plan(plan)
    assert plan.semantic_bindings[0].object_key == "nhsa.setl_d.hifp_pay"


def test_month_dimension_cannot_bind_to_year_only_column():
    plan = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"],
        dimensions=["month"],
        date_range=DateRange(type="current_year_to_date", start=date(2026, 1, 1), end=date(2026, 8, 27)),
        semantic_bindings=[SemanticBinding(
            role="dimension", key="month", label="月份", object_key="nhsa.setl_d.year",
            schema_name="nhsa", table_name="setl_d", column_name="year", aggregation="none",
        )],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert ConversationService._binding_semantically_incompatible(plan, plan.semantic_bindings[0])
    assert "结算时间" in ConversationService._binding_correction_query(plan, plan.semantic_bindings[0])


def test_inpatient_filter_cannot_bind_to_insurance_type():
    plan = QueryPlanV1(
        intent="aggregate_analysis",
        metrics=["fund_pay_total"], dimensions=[], date_range=DateRange(type="all"),
        filters=[{"field": "insutype", "operator": "eq", "value": "21", "display_value": "住院"}],
        semantic_bindings=[SemanticBinding(
            role="filter", key="insutype", label="险种类型", object_key="nhsa.setl_d.insutype",
            schema_name="nhsa", table_name="setl_d", column_name="insutype", aggregation="none",
        )],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert ConversationService._binding_semantically_incompatible(plan, plan.semantic_bindings[0])
    assert "就医类别" in ConversationService._binding_correction_query(plan, plan.semantic_bindings[0])


def test_missing_month_and_time_bindings_are_detected():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=["month"],
        date_range=DateRange(type="current_year_to_date", start=date(2026, 1, 1), end=date(2026, 8, 27)),
        semantic_bindings=[SemanticBinding(
            role="metric", key="fund_pay_total", label="基金支付总额",
            object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa", table_name="setl_d",
            column_name="fund_pay_sumamt", aggregation="sum",
        )],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    missing = ConversationService._missing_semantic_bindings(plan)

    assert "missing:dimension:month" in missing
    assert "missing:time:date_range" in missing


def test_settlement_time_is_ranked_above_birth_date_for_catalog_fallback():
    settlement = {"column_name": "setl_time", "database_comment": "结算时间", "data_type": "varchar"}
    birth = {"column_name": "brdy", "database_comment": "出生日期", "data_type": "varchar"}

    assert ConversationService._time_column_score(settlement) > 0
    assert ConversationService._time_column_score(settlement) > ConversationService._time_column_score(birth)


def test_month_dimension_can_be_derived_from_settlement_time_binding():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=["month"],
        date_range=DateRange(type="current_year_to_date", start=date(2026, 1, 1), end=date(2026, 8, 27)),
        semantic_bindings=[
            SemanticBinding(
                role="metric", key="fund_pay_total", label="基金支付总额",
                object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa", table_name="setl_d",
                column_name="fund_pay_sumamt", aggregation="sum",
            ),
            SemanticBinding(
                role="time", key="stat_time", label="结算时间", object_key="nhsa.setl_d.setl_time",
                schema_name="nhsa", table_name="setl_d", column_name="setl_time", aggregation="none",
            ),
        ],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert ConversationService._missing_semantic_bindings(plan) == []


def test_explicit_date_range_accepts_time_field_bound_as_filter():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=["institution"],
        date_range=DateRange(type="explicit", start=date(2026, 1, 1), end=date(2026, 12, 31)),
        filters=[{"field": "nhsa.setl_d.setl_time", "operator": "between",
                  "value": ["2026-01-01", "2026-12-31"], "display_value": "2026年"}],
        semantic_bindings=[
            SemanticBinding(role="metric", key="fund_pay_total", label="基金支付总额",
                            object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa",
                            table_name="setl_d", column_name="fund_pay_sumamt", aggregation="sum"),
            SemanticBinding(role="dimension", key="institution", label="医疗机构",
                            object_key="nhsa.setl_d.fixmedins_name", schema_name="nhsa",
                            table_name="setl_d", column_name="fixmedins_name"),
            SemanticBinding(role="filter", key="time_range", label="统计时间",
                            object_key="nhsa.setl_d.setl_time", schema_name="nhsa",
                            table_name="setl_d", column_name="setl_time"),
        ],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    assert ConversationService._missing_semantic_bindings(plan) == []


def test_explicit_date_range_normalizes_time_range_binding_and_removes_false_clarification():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=[],
        date_range=DateRange(type="explicit", start=date(2026, 1, 1), end=date(2026, 12, 31)),
        clarifications=[{"id": "filter_value:time_range", "question": "确认时间",
                         "reason": "未落实", "options": []}],
        semantic_bindings=[SemanticBinding(
            role="filter", key="time_range", label="统计时间",
            object_key="nhsa.setl_d.setl_time", schema_name="nhsa", table_name="setl_d",
            column_name="setl_time",
        )],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    ConversationService._normalize_explicit_time_binding(plan)

    assert plan.semantic_bindings[0].role == "time"
    assert plan.clarifications == []
    assert ConversationService._missing_semantic_bindings(plan) == ["missing:metric:fund_pay_total"]


def test_certified_bindings_rebuild_semantic_ir_with_stable_output_aliases():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total", "total_fee", "settlement_count"],
        dimensions=["institution"], date_range=DateRange(type="all"),
        semantic_bindings=[
            SemanticBinding(role="dimension", key="institution", label="医疗机构",
                            object_key="nhsa.setl_d.fixmedins_name", schema_name="nhsa",
                            table_name="setl_d", column_name="fixmedins_name", certified=True),
            SemanticBinding(role="metric", key="fund_pay_total", label="基金支付总额",
                            object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa",
                            table_name="setl_d", column_name="fund_pay_sumamt", aggregation="sum", certified=True),
            SemanticBinding(role="metric", key="total_fee", label="医疗总费用",
                            object_key="nhsa.setl_d.medfee_sumamt", schema_name="nhsa",
                            table_name="setl_d", column_name="medfee_sumamt", aggregation="sum", certified=True),
            SemanticBinding(role="metric", key="settlement_count", label="结算人次",
                            object_key="nhsa.setl_d.setl_id", schema_name="nhsa",
                            table_name="setl_d", column_name="setl_id", aggregation="count_distinct", certified=True),
        ],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    plan.semantics.output_fields = ["fixmedins_name", "fund_pay_sumamt", "medfee_sumamt", "setl_id_count"]

    ConversationService._align_semantics_to_certified_bindings(plan)

    assert plan.semantics.output_fields == ["institution", "fund_pay_total", "total_fee", "settlement_count"]
    assert [item["alias"] for item in plan.semantics.output_expressions] == plan.semantics.output_fields
    assert plan.semantics.aggregations[-1]["function"] == "count_distinct"


def test_certified_yoy_bindings_expand_semantic_output_contract():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total", "settlement_count"],
        dimensions=["institution"], date_range=DateRange(
            type="explicit", start=date(2026, 1, 1), end=date(2026, 12, 31)
        ),
        comparison={"type": "year_over_year", "grain": "period_total"},
        semantic_bindings=[
            SemanticBinding(role="dimension", key="institution", label="医疗机构",
                            object_key="nhsa.setl_d.fixmedins_name", schema_name="nhsa",
                            table_name="setl_d", column_name="fixmedins_name", certified=True),
            SemanticBinding(role="metric", key="fund_pay_total", label="基金支付总额",
                            object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa",
                            table_name="setl_d", column_name="fund_pay_sumamt", aggregation="sum", certified=True),
            SemanticBinding(role="metric", key="settlement_count", label="结算人次",
                            object_key="nhsa.setl_d.setl_id", schema_name="nhsa",
                            table_name="setl_d", column_name="setl_id", aggregation="count_distinct", certified=True),
        ],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )

    ConversationService._align_semantics_to_certified_bindings(plan)

    assert plan.semantics.output_fields == [
        "institution",
        "fund_pay_total", "prev_fund_pay_total", "fund_pay_total_yoy_rate",
        "settlement_count", "prev_settlement_count", "settlement_count_yoy_rate",
    ]
    assert [item["alias"] for item in plan.semantics.output_expressions] == plan.semantics.output_fields


def test_inpatient_label_is_linked_from_catalog_dictionary_and_year_filter_removed():
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["fund_pay_total"], dimensions=["month"],
        date_range=DateRange(type="explicit", start=date(2026, 1, 1), end=date(2026, 8, 27)),
        filters=[
            {"field": "nhsa.setl_d.med_type", "operator": "eq", "value": "住院", "display_value": "住院"},
            {"field": "nhsa.setl_d.year", "operator": "eq", "value": "2026", "display_value": "2026年"},
        ],
        semantic_bindings=[
            SemanticBinding(role="metric", key="fund_pay_total", label="基金支付总额", object_key="nhsa.setl_d.fund_pay_sumamt", schema_name="nhsa", table_name="setl_d", column_name="fund_pay_sumamt", aggregation="sum"),
            SemanticBinding(role="dimension", key="month", label="月份", object_key="nhsa.setl_d.setl_time", schema_name="nhsa", table_name="setl_d", column_name="setl_time", aggregation="none"),
            SemanticBinding(role="filter", key="visit_type", label="医疗类别", object_key="nhsa.setl_d.med_type", schema_name="nhsa", table_name="setl_d", column_name="med_type", aggregation="none"),
            SemanticBinding(role="filter", key="year", label="年度", object_key="nhsa.setl_d.year", schema_name="nhsa", table_name="setl_d", column_name="year", aggregation="none"),
        ],
        provenance=PlanProvenance(model="test", prompt_version="test"),
    )
    context = [{
        "object_key": "nhsa.setl_d.med_type",
        "business_name": "医疗类别",
        "content": "所有住院类型为21、22、23、24、52、92。",
    }]

    ConversationService._link_filter_values(plan, context)
    ConversationService._remove_redundant_year_filter(plan)

    assert plan.filters[0].operator == "in"
    assert plan.filters[0].value == ["21", "22", "23", "24", "52", "92"]
    assert all(item.field.rsplit(".", 1)[-1] != "year" for item in plan.filters)
