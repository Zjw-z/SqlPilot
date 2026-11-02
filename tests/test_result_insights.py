from app.text_to_sql.insights import ResultInterpreter, build_chart_spec
from app.text_to_sql.presentation import build_result_schema


def test_builds_bar_chart_for_institution_metric():
    rows = [
        {"institution_name": "甲医院", "fund_pay_total": 120.5},
        {"institution_name": "乙医院", "fund_pay_total": 98.0},
    ]

    chart = build_chart_spec(rows, build_result_schema(rows))

    assert chart is not None
    assert chart["type"] == "bar"
    assert chart["categories"] == ["甲医院", "乙医院"]
    assert chart["series"][0]["label"] == "医保基金支付金额"


def test_bar_chart_is_sorted_by_primary_measure():
    rows = [
        {"institution_name": "甲医院", "fund_pay_total": 10},
        {"institution_name": "乙医院", "fund_pay_total": 30},
    ]

    chart = build_chart_spec(rows, build_result_schema(rows))

    assert chart["categories"] == ["乙医院", "甲医院"]
    assert chart["series"][0]["values"] == [30.0, 10.0]


def test_builds_line_chart_for_monthly_series():
    rows = [
        {"month": "2026-01", "yoy_rate": 3.2},
        {"month": "2026-02", "yoy_rate": 5.1},
    ]

    chart = build_chart_spec(rows, build_result_schema(rows))

    assert chart is not None
    assert chart["type"] == "line"
    assert chart["categories"] == ["2026-01", "2026-02"]
    assert chart["series"][0]["unit"] == "%"


def test_chart_limits_large_category_sets_and_marks_truncation():
    rows = [{"institution_name": f"医院{i}", "fund_pay_total": i} for i in range(25)]

    chart = build_chart_spec(rows, build_result_schema(rows))

    assert chart is not None
    assert chart["displayed_points"] == 20
    assert chart["total_points"] == 25
    assert chart["truncated"] is True
    assert chart["categories"][0] == "医院24"


def test_fallback_interpretation_uses_only_result_values():
    rows = [
        {"institution_name": "甲医院", "fund_pay_total": 12},
        {"institution_name": "乙医院", "fund_pay_total": 20},
    ]
    chart = build_chart_spec(rows, build_result_schema(rows))

    insight = ResultInterpreter._fallback(rows, chart, truncated=False)

    assert insight["source"] == "system"
    assert insight["summary"] == "本次查询返回2条结果。"
    assert insight["findings"] == ["乙医院的医保基金支付金额最高，为20元。"]


def test_model_object_findings_are_normalized_for_display():
    items = [{"label": "最高机构", "detail": "甲医院为100元"}, "没有同期数据"]

    assert ResultInterpreter._text_items(items, 4) == ["最高机构：甲医院为100元", "没有同期数据"]


def test_multi_metric_results_are_split_by_business_measure_and_unit():
    rows = [{
        "month": "2026-01-01", "fund_pay_total": 100, "prev_fund_pay_total": 90,
        "total_fee": 150, "prev_total_fee": 140,
        "settlement_count": 10, "prev_settlement_count": 9,
        "fund_pay_total_yoy_rate": 11.11, "total_fee_yoy_rate": 7.14,
        "settlement_count_yoy_rate": 11.11,
    }]

    chart = build_chart_spec(rows, build_result_schema(rows))

    assert chart["type"] == "dashboard"
    assert len(chart["charts"]) == 4
    assert [item["key"] for item in chart["charts"][0]["series"]] == [
        "fund_pay_total", "prev_fund_pay_total",
    ]
    assert [item["key"] for item in chart["charts"][2]["series"]] == [
        "settlement_count", "prev_settlement_count",
    ]
    assert chart["charts"][3]["zero_baseline"] is True
    assert all(item["unit"] == "%" for item in chart["charts"][3]["series"])
