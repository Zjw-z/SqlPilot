from __future__ import annotations

import re
from datetime import date

from app.catalog import DIMENSIONS, METRICS, VALUE_DICTIONARY
from app.domain import QueryPlan


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def understand(question: str, today: date | None = None) -> QueryPlan:
    today = today or date.today()
    metric_matches = [metric for metric in METRICS if _contains_any(question, (metric.name, *metric.aliases))]
    if any(term in question for term in ("医保基金", "基金使用", "基金支付", "基金支出")):
        metric = next(item for item in METRICS if item.key == "fund_pay_total")
    else:
        metric = metric_matches[0] if metric_matches else None
    dimensions = [dimension for dimension in DIMENSIONS if _contains_any(question, dimension.aliases)]
    if any(word in question for word in ("医院", "机构")) and not any(d.key == "institution" for d in dimensions):
        dimensions.append(next(d for d in DIMENSIONS if d.key == "institution"))
    if any(word in question for word in ("哪个月", "哪些月", "各月")) and not any(d.key == "month" for d in dimensions):
        dimensions.insert(0, next(d for d in DIMENSIONS if d.key == "month"))

    year_match = re.search(r"(20\d{2})\s*年?", question)
    year = int(year_match.group(1)) if year_match else None
    if "去年" in question:
        year = today.year - 1
    if "今年" in question:
        year = today.year
        start_date, end_date = f"{year}-01-01", today.isoformat()
    else:
        start_date = f"{year}-01-01" if year else None
        end_date = f"{year}-12-31" if year else None

    top_match = re.search(r"(?:前|top\s*)(\d+)", question, re.IGNORECASE)
    top_n = int(top_match.group(1)) if top_match else None
    level = next((name for name in VALUE_DICTIONARY if name in question), None)
    comparison = "yoy" if any(word in question for word in ("同期", "同比")) else "mom" if "环比" in question else "none"
    medical_type = "inpatient" if "住院" in question else None
    order_by = "growth" if any(word in question for word in ("增长较高", "增长最高", "增长较快", "增幅较高", "增幅最高")) else "metric"

    assumptions: list[str] = []
    ambiguities: list[str] = []
    if metric is None:
        ambiguities.append("未识别到经过认证的指标")
    elif metric.key == "total_fee" and "费用" in question and "总费用" not in question:
        ambiguities.append("“费用”暂按总费用理解，也可能指基金支付金额")
    if start_date is None:
        assumptions.append("未指定时间，默认查询全部可用数据")
    if not dimensions:
        assumptions.append("未指定分析维度，返回总体汇总")
    return QueryPlan(
        question=question,
        metric=metric,
        dimensions=dimensions,
        start_date=start_date,
        end_date=end_date,
        institution_level=level,
        top_n=top_n,
        comparison=comparison,
        medical_type=medical_type,
        order_by=order_by,
        assumptions=assumptions,
        ambiguities=ambiguities,
    )
