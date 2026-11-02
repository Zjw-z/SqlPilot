from __future__ import annotations

from app.domain import Dimension, JoinEdge, Metric


METRICS = (
    Metric(
        key="fund_pay_total",
        name="基金支付总额",
        aliases=("基金支付", "基金支出", "医保支付金额", "统筹支付"),
        expression="SUM(s.fund_pay_amt)",
        description="有效、未撤销结算记录的医保基金支付金额之和",
        source_table="settlement",
        required_filters=("s.valid_flag = 1", "s.cancelled_flag = 0"),
    ),
    Metric(
        key="total_fee",
        name="总费用",
        aliases=("费用", "医疗费用", "费用总额"),
        expression="SUM(s.total_fee)",
        description="有效、未撤销结算记录的医疗总费用之和",
        source_table="settlement",
        required_filters=("s.valid_flag = 1", "s.cancelled_flag = 0"),
    ),
    Metric(
        key="settlement_count",
        name="结算人次",
        aliases=("人次", "结算次数", "就诊人次"),
        expression="COUNT(DISTINCT s.settlement_id)",
        description="有效且未撤销的唯一结算记录数",
        source_table="settlement",
        required_filters=("s.valid_flag = 1", "s.cancelled_flag = 0"),
    ),
)

DIMENSIONS = (
    Dimension("month", "结算月份", ("按月", "每月", "月份", "月度"), "strftime('%Y-%m', s.settle_date)", "settlement"),
    Dimension("institution", "医疗机构", ("医院", "机构", "定点医疗机构"), "o.org_name", "medical_org"),
    Dimension("institution_level", "机构等级", ("医院等级", "机构等级", "等级"), "o.org_level_name", "medical_org"),
)

SCHEMA = {
    "settlement": {
        "alias": "s",
        "description": "医保结算事实表，一次结算一行",
        "grain": "settlement_id",
        "columns": {
            "settlement_id", "org_code", "settle_date", "total_fee", "fund_pay_amt",
            "medical_type", "valid_flag", "cancelled_flag",
        },
    },
    "medical_org": {
        "alias": "o",
        "description": "定点医疗机构维表，一个机构一行",
        "grain": "org_code",
        "columns": {"org_code", "org_name", "org_level_code", "org_level_name", "region_code"},
    },
}

JOINS = (
    JoinEdge("settlement", "medical_org", "s.org_code = o.org_code", "N:1"),
)

VALUE_DICTIONARY = {
    "三级甲等": ("o.org_level_code", "3A"),
    "三甲": ("o.org_level_code", "3A"),
    "三级乙等": ("o.org_level_code", "3B"),
}

