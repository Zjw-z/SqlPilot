from __future__ import annotations

import re
from typing import Any


_EXACT_FIELDS: dict[str, tuple[str, str, str | None]] = {
    "institution_name": ("医疗机构", "text", None),
    "institution": ("医疗机构", "text", None),
    "fixmedins_name": ("医疗机构", "text", None),
    "institution_level": ("机构等级", "text", None),
    "day": ("日期", "date", None),
    "week": ("周", "date", None),
    "month": ("月份", "month", None),
    "quarter": ("季度", "date", None),
    "year": ("年度", "date", None),
    "fund_pay_total": ("医保基金支付金额", "currency", "元"),
    "fund_pay_total_yoy": ("上年同期基金支付金额", "currency", "元"),
    "previous_fund_pay_total": ("上年同期基金支付金额", "currency", "元"),
    "prev_fund_pay_total": ("上年同期基金支付金额", "currency", "元"),
    "total_fee": ("医疗总费用", "currency", "元"),
    "total_fee_yoy": ("上年同期医疗总费用", "currency", "元"),
    "prev_total_fee": ("上年同期医疗总费用", "currency", "元"),
    "settlement_count": ("结算人次", "integer", "人次"),
    "prev_settlement_count": ("上年同期结算人次", "integer", "人次"),
    "yoy_rate": ("同比增长率", "percent", "%"),
    "mom_rate": ("环比增长率", "percent", "%"),
    "growth_rate": ("增长率", "percent", "%"),
    "rank_no": ("排名", "integer", None),
}


def build_result_schema(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build display metadata without changing SQL aliases or result values."""
    if not rows:
        return []
    schema = []
    for key in rows[0]:
        label, value_type, unit = _field_metadata(key, [row.get(key) for row in rows])
        schema.append({"key": key, "label": label, "type": value_type, "unit": unit})
    return schema


def _field_metadata(key: str, values: list[Any]) -> tuple[str, str, str | None]:
    normalized = key.lower().strip()
    if normalized in _EXACT_FIELDS:
        return _EXACT_FIELDS[normalized]
    if "yoy" in normalized and ("rate" in normalized or "growth" in normalized):
        metric = "医保基金支付" if "fund_pay" in normalized else "医疗总费用" if "total_fee" in normalized else "结算人次" if "settlement" in normalized else ""
        return f"{metric}同比增长率", "percent", "%"
    if "mom" in normalized and ("rate" in normalized or "growth" in normalized):
        return "环比增长率", "percent", "%"
    if normalized.endswith("_rate") or "percent" in normalized:
        return "增长率", "percent", "%"
    if any(token in normalized for token in ("amount", "amt", "fee", "pay", "cost")):
        prefix = "上年同期" if any(token in normalized for token in ("previous", "prior", "yoy")) else ""
        return f"{prefix}金额", "currency", "元"
    if any(token in normalized for token in ("count", "num", "times")):
        return "数量", "integer", None
    if "month" in normalized:
        return "月份", "month", None
    if "date" in normalized or "time" in normalized:
        return "日期", "date", None
    if "name" in normalized:
        return "名称", "text", None
    if "rank" in normalized:
        return "排名", "integer", None
    label = re.sub(r"[_-]+", " ", key).strip() or "结果字段"
    value_type = "number" if any(isinstance(value, (int, float)) for value in values if value is not None) else "text"
    return label, value_type, None
