from __future__ import annotations

from app.planning.models import QueryPlanV1


METRICS = {
    "fund_pay_total": "医保基金支付总额",
    "total_fee": "医疗总费用",
    "settlement_count": "结算人次",
}
DIMENSIONS = {
    "day": "日期", "week": "周", "month": "月份", "quarter": "季度", "year": "年度",
    "institution": "医疗机构", "institution_level": "机构等级",
}


def summarize_plan(plan: QueryPlanV1) -> str:
    if plan.intent == "unsupported":
        return "当前问题不属于可执行的数据查询"
    binding_labels = {item.key: item.label for item in plan.semantic_bindings}
    metric = "、".join(METRICS.get(item, binding_labels.get(item, item)) for item in plan.metrics) or "尚未确定的统计指标"
    dimensions = "、".join(DIMENSIONS.get(item, binding_labels.get(item, item)) for item in plan.dimensions) or "总体"
    period = "全部可用时间"
    if plan.date_range.start and plan.date_range.end:
        start, end = plan.date_range.start, plan.date_range.end
        period = f"{start.year}年度" if start.month == start.day == 1 and end.month == 12 and end.day == 31 else f"{start.year}年{start.month}月{start.day}日至{end.month}月{end.day}日"
    sentences = [f"统计{period}各{dimensions}的{metric}"]
    for item in plan.filters:
        if item.field == "medical_type":
            sentences.append(f"就医类型仅统计{item.display_value}")
        elif item.field == "institution_level":
            sentences.append(f"机构范围仅限{item.display_value}")
    if plan.comparison.type == "year_over_year":
        grain = {"day": "按日", "week": "按周", "month": "按月", "quarter": "按季度", "year": "按年度", "period_total": "按当前期间累计"}.get(plan.comparison.grain, "")
        sentences.append(f"{grain}与上年同期进行同比并计算增长率")
    elif plan.comparison.type == "month_over_month":
        previous = {"day": "上一日", "week": "上一周", "month": "上月", "quarter": "上季度", "year": "上一年"}.get(plan.comparison.grain, "上一周期")
        sentences.append(f"计算与{previous}相比的环比")
    if plan.ranking.metric == "yoy_rate" and (plan.ranking.scope or plan.ranking.limit):
        scope = {
            "within_institution": "分别在每家医疗机构内",
            "within_dimension": "分别在每个" + "、".join(
                DIMENSIONS.get(key, binding_labels.get(key, key)) for key in plan.ranking.partition_by
            ) + "内",
            "global": "在所有机构和月份中",
            "overall_month": "汇总全部机构后",
        }.get(plan.ranking.scope, "按待确认范围")
        limit = f"前{plan.ranking.limit}项" if plan.ranking.limit else "增长较高的月份"
        sentences.append(f"{scope}按同比增长率从高到低查找{limit}")
    policy_labels = {
        "valid_settlement_only": "仅包含有效结算",
        "exclude_cancelled": "排除已撤销记录",
    }
    policies = [policy_labels[item] for item in plan.default_policies if item in policy_labels]
    suffix = f"。已应用数据源认证口径：{'，'.join(policies)}。" if policies else "。未应用额外的默认业务口径。"
    return "。".join(sentences) + suffix


def conversation_reply(plan: QueryPlanV1, *, is_revision: bool) -> str:
    """Render a stage-aware chat reply; the structured plan remains the execution source."""
    if plan.needs_clarification:
        question = plan.clarifications[0].question
        if is_revision:
            return f"已记录你的补充。还需要确认一个问题：{question}"
        return f"我已经初步理解了你的需求。为了准确查询，还需要确认：{question}"

    prefix = "已按你的补充更新查询计划。当前最终需求是：" if is_revision else "我理解你的需求是："
    return prefix + summarize_plan(plan) + "请确认右侧最终查询计划，确认后我再生成并执行 SQL。"
