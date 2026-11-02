from __future__ import annotations

from app.catalog import DIMENSIONS, METRICS
from app.domain import QueryPlan
from app.planning.models import QueryPlanV1


def to_legacy_plan(plan: QueryPlanV1, question: str = "已确认查询计划") -> QueryPlan:
    metric = next((item for item in METRICS if item.key == plan.metric), None)
    dimensions = [item for item in DIMENSIONS if item.key in plan.dimensions]
    filters = {item.field: item for item in plan.filters}
    comparison = {"none": "none", "month_over_month": "mom", "year_over_year": "yoy"}[plan.comparison.type]
    return QueryPlan(
        question=question,
        metric=metric,
        dimensions=dimensions,
        start_date=plan.date_range.start.isoformat() if plan.date_range.start else None,
        end_date=plan.date_range.end.isoformat() if plan.date_range.end else None,
        institution_level=filters.get("institution_level").display_value if filters.get("institution_level") else None,
        top_n=plan.ranking.limit,
        comparison=comparison,
        medical_type="inpatient" if filters.get("medical_type") else None,
        order_by="growth" if plan.ranking.metric in {"mom_rate", "yoy_rate"} else "metric",
        ranking_scope=plan.ranking.scope,
    )
