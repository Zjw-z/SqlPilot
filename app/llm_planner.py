from __future__ import annotations

import json
import os
from datetime import date
from typing import Literal

from openai import OpenAI
from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError

from app.catalog import DIMENSIONS, METRICS
from app.domain import QueryPlan


class PlannerConfigurationError(RuntimeError):
    pass


class PlannerModelError(RuntimeError):
    pass


class ClarificationOption(BaseModel):
    value: str
    label: str
    description: str | None = None


class Clarification(BaseModel):
    id: str
    question: str
    reason: str
    options: list[ClarificationOption] = Field(default_factory=list)


class ModelPlan(BaseModel):
    intent: Literal["aggregate_analysis", "detail_query", "unsupported"]
    metric_key: Literal["fund_pay_total", "total_fee", "settlement_count"] | None
    dimension_keys: list[Literal["month", "institution", "institution_level"]]
    date_preset: Literal["current_year_to_date", "previous_year", "explicit", "all"]
    start_date: str | None = None
    end_date: str | None = None
    medical_type: Literal["inpatient"] | None = None
    institution_level: Literal["三级甲等", "三级乙等"] | None = None
    comparison: Literal["none", "mom", "yoy"] = "none"
    order_by: Literal["metric", "growth"] = "metric"
    ranking_scope: Literal["global", "within_institution", "overall_month"] | None = None
    top_n: int | None = Field(default=None, ge=1, le=1000)
    assumptions: list[str] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)


SYSTEM_PROMPT = """你是医保数据分析系统的需求规划器。请把用户自然语言转换为JSON查询计划，禁止生成SQL。
只能使用提供的认证指标、维度和枚举，不得发明字段。

认证指标：
- fund_pay_total: 医保基金支付总额。别名包括医保基金使用、基金支出、统筹支付。
- total_fee: 医疗总费用。
- settlement_count: 结算人次。

分析维度：month（结算月份）、institution（医疗机构）、institution_level（机构等级）。
medical_type目前只支持 inpatient（住院）。comparison支持 none、mom（环比）、yoy（与上年同期同比）。

要求：
1. 结合整句话判断修饰关系。“住院医保基金……费用增长”仍表示医保基金指标，不要被后面的泛称“费用”覆盖。
2. “同期”通常映射yoy；如果上下文存在其他同样合理解释，则加入clarifications。
3. “今年”映射current_year_to_date，具体日期由程序计算。
4. 需要找“哪个月”时加入month；出现“各医院/各机构”时加入institution。
5. 若增长排名范围不清楚，ranking_scope设null，并追问是每家机构分别排名、机构月份全局排名，还是所有机构汇总后按月排名。
6. 只有不同理解会明显改变查询结果时才追问。clarifications中的options使用稳定英文value和中文label。
7. 必须输出一个JSON对象，不要Markdown，不要解释文字。
"""


class LLMQueryPlanner:
    """Production planner backed by the Bailian model configured by the enterprise platform."""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        file_config = dotenv_values(config_path)
        self.api_key = api_key or file_config.get("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url or file_config.get("SQLPILOT_BAILIAN_BASE_URL") or os.getenv(
            "SQLPILOT_BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model = model or file_config.get("SQLPILOT_BAILIAN_MODEL") or os.getenv(
            "SQLPILOT_BAILIAN_MODEL", "qwen3.6-plus-2026-04-02"
        )
        if not self.api_key:
            raise PlannerConfigurationError(
                f"未配置百炼密钥。请编辑 {config_path} 中的DASHSCOPE_API_KEY，SQLPilot不会降级为规则解析。"
            )
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=120.0, max_retries=2)

    def plan(self, question: str, today: date | None = None) -> QueryPlan:
        today = today or date.today()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"当前日期：{today.isoformat()}\n用户需求：{question}\n请输出JSON查询计划。"},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            content = response.choices[0].message.content or ""
            raw = ModelPlan.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError, IndexError) as exc:
            raise PlannerModelError(f"百炼返回的查询计划不符合结构协议：{exc}") from exc
        except Exception as exc:
            raise PlannerModelError(f"百炼需求分析调用失败：{type(exc).__name__}") from exc
        return self._to_domain(question, raw, today)

    @staticmethod
    def _to_domain(question: str, raw: ModelPlan, today: date) -> QueryPlan:
        metric = next((item for item in METRICS if item.key == raw.metric_key), None)
        dimensions = [item for item in DIMENSIONS if item.key in raw.dimension_keys]
        if raw.date_preset == "current_year_to_date":
            start_date, end_date = f"{today.year}-01-01", today.isoformat()
        elif raw.date_preset == "previous_year":
            start_date, end_date = f"{today.year - 1}-01-01", f"{today.year - 1}-12-31"
        elif raw.date_preset == "explicit":
            start_date, end_date = raw.start_date, raw.end_date
        else:
            start_date = end_date = None

        allowed_values = {
            "metric": {"fund_pay_total", "total_fee", "settlement_count"},
            "ranking_scope": {"global", "within_institution", "overall_month"},
        }
        clarifications = []
        for item in raw.clarifications:
            dumped = item.model_dump()
            allowed = allowed_values.get(item.id, set())
            dumped["options"] = [option for option in dumped["options"] if option["value"] in allowed]
            clarifications.append(dumped)
        ambiguities = [item.question for item in raw.clarifications]
        if raw.metric_key is None and not any(item["id"] == "metric" for item in clarifications):
            question_text = "你希望统计哪个业务指标？"
            clarifications.append({
                "id": "metric",
                "question": question_text,
                "reason": "用户描述中没有唯一确定的统计指标",
                "options": [
                    {"value": "fund_pay_total", "label": "医保基金支付金额", "description": None},
                    {"value": "total_fee", "label": "医疗总费用", "description": None},
                    {"value": "settlement_count", "label": "结算人次", "description": None},
                ],
            })
            ambiguities.append(question_text)
        return QueryPlan(
            question=question,
            metric=metric,
            dimensions=dimensions,
            start_date=start_date,
            end_date=end_date,
            institution_level=raw.institution_level,
            top_n=raw.top_n,
            comparison=raw.comparison,
            medical_type=raw.medical_type,
            order_by=raw.order_by,
            ranking_scope=raw.ranking_scope,
            clarifications=clarifications,
            assumptions=raw.assumptions,
            ambiguities=ambiguities,
        )
