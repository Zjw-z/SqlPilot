import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.llm_planner import LLMQueryPlanner, PlannerConfigurationError


class FakeCompletions:
    def __init__(self, payload):
        self.payload = payload

    def create(self, **kwargs):
        assert kwargs["response_format"] == {"type": "json_object"}
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False)))]
        )


def test_missing_bailian_key_fails_closed(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr("app.llm_planner.dotenv_values", lambda _path: {})
    with pytest.raises(PlannerConfigurationError, match="不会降级"):
        LLMQueryPlanner()


def test_bailian_structured_plan_and_clarification():
    planner = LLMQueryPlanner(api_key="test-key")
    planner.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FakeCompletions(
                {
                    "intent": "aggregate_analysis",
                    "metric_key": "fund_pay_total",
                    "dimension_keys": ["month", "institution"],
                    "date_preset": "current_year_to_date",
                    "medical_type": "inpatient",
                    "comparison": "yoy",
                    "order_by": "growth",
                    "ranking_scope": None,
                    "clarifications": [
                        {
                            "id": "ranking_scope",
                            "question": "增长较高的月份应该在哪个范围内比较？",
                            "reason": "可能是每家机构分别排名，也可能是全局排名",
                            "options": [
                                {"value": "within_institution", "label": "每家机构分别排名"},
                                {"value": "global", "label": "所有机构月份统一排名"},
                                {"value": "unsafe-value'", "label": "非法选项"},
                            ],
                        }
                    ],
                }
            )
        )
    )
    plan = planner.plan(
        "统计下今年各医疗机构的住院医保基金使用情况，和同期进行比较，看哪个月的费用增长较高",
        date(2026, 8, 25),
    )
    assert plan.metric.key == "fund_pay_total"
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-08-25"
    assert plan.comparison == "yoy"
    assert plan.ambiguities
    assert [item["value"] for item in plan.clarifications[0]["options"]] == [
        "within_institution",
        "global",
    ]
