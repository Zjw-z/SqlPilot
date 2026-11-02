from app.text_to_sql.presentation import build_result_schema


def test_builds_chinese_result_schema_for_yoy_query():
    rows = [{"institution_name": "城北医院", "month": "2026-08-01", "fund_pay_total": 22059.13,
             "settlement_count": 6, "fund_pay_total_yoy": 15534.60, "yoy_rate": 42.0}]
    schema = build_result_schema(rows)
    assert [item["label"] for item in schema] == [
        "医疗机构", "月份", "医保基金支付金额", "结算人次", "上年同期基金支付金额", "同比增长率"
    ]
    assert schema[-1]["type"] == "percent"
    assert schema[2]["unit"] == "元"


def test_infers_common_unseen_aliases():
    schema = build_result_schema([{"previous_amount": 100, "custom_count": 2}])
    assert schema[0]["label"] == "上年同期金额"
    assert schema[0]["type"] == "currency"
    assert schema[1]["type"] == "integer"


def test_labels_deterministic_compiler_comparison_columns():
    schema = build_result_schema([{
        "prev_fund_pay_total": 100,
        "prev_total_fee": 200,
        "prev_settlement_count": 3,
    }])

    assert [item["label"] for item in schema] == [
        "上年同期基金支付金额", "上年同期医疗总费用", "上年同期结算人次",
    ]
