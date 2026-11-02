from __future__ import annotations

import json
import re
from datetime import date
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.config import Settings
from app.core.errors import ConfigurationError, PlannerError
from app.planning.models import (
    Clarification,
    Comparison,
    DateRange,
    PlanProvenance,
    QueryFilter,
    QueryPlanV1,
    Ranking,
    SemanticBinding,
    QuerySemantics,
)
from app.planning.prompt import PROMPT_VERSION, SYSTEM_PROMPT


class PlanningDraft(BaseModel):
    intent: Literal["aggregate_analysis", "detail_query", "unsupported"]
    metrics: list[str] = Field(default_factory=list)
    metric: str | None = None
    dimensions: list[str]
    date_type: Literal["current_year_to_date", "previous_year", "explicit", "all"]
    start_date: date | None = None
    end_date: date | None = None
    filters: list[QueryFilter] = Field(default_factory=list)
    comparison_type: Literal["none", "month_over_month", "year_over_year"] = "none"
    comparison_grain: Literal["day", "week", "month", "quarter", "year", "period_total"] | None = None
    ranking: Ranking = Field(default_factory=Ranking)
    assumptions: list[str] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)
    semantic_bindings: list[SemanticBinding] = Field(default_factory=list)
    semantics: QuerySemantics = Field(default_factory=QuerySemantics)
    changed_fields: list[Literal[
        "intent", "metrics", "dimensions", "date_range", "filters",
        "comparison", "ranking", "assumptions", "clarifications", "semantic_bindings", "semantics",
    ]] = Field(min_length=1)

    @field_validator("ranking", mode="before")
    @classmethod
    def normalize_empty_ranking(cls, value):
        # Models commonly use null to mean that no ranking was requested.
        # It is semantically equivalent to the protocol's empty Ranking object.
        return {} if value is None else value

    @model_validator(mode="after")
    def normalize_metrics(self):
        if self.metric and self.metric not in self.metrics:
            self.metrics.insert(0, self.metric)
        self.metrics = list(dict.fromkeys(self.metrics))
        return self


class BailianQueryPlanner:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        if not settings.dashscope_api_key:
            raise ConfigurationError("请在项目根目录.env中配置DASHSCOPE_API_KEY")
        self.settings = settings
        self.client = client or AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.sqlpilot_bailian_base_url,
            timeout=settings.planner_timeout_seconds,
            max_retries=settings.planner_max_retries,
        )

    async def create_plan(self, question: str, schema_context: list[dict] | None = None, memory_context: dict | None = None) -> QueryPlanV1:
        return await self._call(
            f"当前日期：{date.today().isoformat()}\n用户的新需求：{question}\n"
            f"Schema RAG候选：{json.dumps(schema_context or [], ensure_ascii=False)}\n请生成JSON查询计划。",
            memory_context=memory_context,
            latest_user_message=question,
        )

    async def revise_plan(
        self,
        current_plan: QueryPlanV1,
        user_message: str,
        schema_context: list[dict] | None = None,
        memory_context: dict | None = None,
    ) -> QueryPlanV1:
        return await self._call(
            "这是当前查询计划：\n"
            + current_plan.model_dump_json(exclude={"provenance"})
            + f"\n用户补充或回答：{user_message}\n"
            + f"\n本轮Schema RAG候选：{json.dumps(schema_context or [], ensure_ascii=False)}\n"
            "请结合当前待澄清问题理解这条回答。只更新用户本轮明确修改或回答涉及的字段；"
            "changed_fields必须准确列出本轮允许变化的顶层字段，未列出的字段会由系统保留上一版值。"
            "例如用户只说‘按年度累计，不按月份’，应修改dimensions、comparison，保留institution等其他维度。",
            latest_user_message=user_message,
            current_plan=current_plan,
            memory_context=memory_context,
        )

    async def _call(
        self,
        user_content: str,
        *,
        latest_user_message: str,
        current_plan: QueryPlanV1 | None = None,
        memory_context: dict | None = None,
    ) -> QueryPlanV1:
        schema = json.dumps(PlanningDraft.model_json_schema(), ensure_ascii=False)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    user_content
                    + "\n可复用记忆（仅可作为偏好或已认证口径，不得覆盖本轮明确需求）：\n"
                    + json.dumps(memory_context or {}, ensure_ascii=False)
                    + "\n必须严格使用下面 JSON Schema 的字段名、枚举值和数据类型，不得新增或改名：\n"
                    + schema
                ),
            },
        ]
        try:
            last_error: Exception | None = None
            for attempt in range(2):
                response = await self.client.chat.completions.create(
                    model=self.settings.sqlpilot_bailian_model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                    extra_body={"enable_thinking": False},
                )
                content = response.choices[0].message.content or ""
                try:
                    draft = PlanningDraft.model_validate(json.loads(content))
                    return self._normalize(draft, latest_user_message, current_plan=current_plan)
                except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                    last_error = exc
                    if attempt == 0:
                        messages.extend(
                            [
                                {"role": "assistant", "content": content},
                                {
                                    "role": "user",
                                    "content": (
                                        "上面的 JSON 未通过协议校验。请纠正后只输出完整 JSON；"
                                        "不要解释、不要使用其他字段名。校验错误："
                                        + str(exc)
                                    ),
                                },
                            ]
                        )
            raise PlannerError(
                "PLANNER_INVALID_OUTPUT",
                "百炼返回的查询计划不符合协议",
                details={"validation_error": str(last_error)[:4000]},
            ) from last_error
        except PlannerError:
            raise
        except Exception as exc:
            name = type(exc).__name__
            retryable = name in {"APITimeoutError", "RateLimitError", "APIConnectionError"}
            raise PlannerError("PLANNER_UNAVAILABLE", f"百炼需求分析失败：{name}", retryable) from exc

    def _normalize(
        self,
        draft: PlanningDraft,
        latest_user_message: str = "",
        *,
        current_plan: QueryPlanV1 | None = None,
    ) -> QueryPlanV1:
        today = date.today()
        if draft.date_type == "current_year_to_date":
            date_range = DateRange(type=draft.date_type, start=date(today.year, 1, 1), end=today)
        elif draft.date_type == "previous_year":
            date_range = DateRange(
                type=draft.date_type,
                start=date(today.year - 1, 1, 1),
                end=date(today.year - 1, 12, 31),
            )
        elif draft.date_type == "explicit":
            date_range = DateRange(type=draft.date_type, start=draft.start_date, end=draft.end_date)
        else:
            date_range = DateRange(type="all")
        if draft.comparison_type == "year_over_year" and date_range.start and date_range.end:
            date_range.comparison_start = QueryPlanV1._previous_year_date(date_range.start)
            date_range.comparison_end = QueryPlanV1._previous_year_date(date_range.end)
        filters = list(draft.filters)
        metrics = list(draft.metrics)
        clarifications = self._sanitize_clarifications(draft.clarifications)
        filter_fields = {
            field_name
            for item in filters
            for field_name in (item.field, item.field.rsplit(".", 1)[-1])
        }
        missing_filter_bindings = [
            item for item in draft.semantic_bindings
            if item.role == "filter"
            and item.key not in filter_fields
            and item.column_name not in filter_fields
            and item.object_key not in filter_fields
        ]
        for binding in missing_filter_bindings:
            clarifications.append(
                Clarification(
                    id=f"filter_value:{binding.key}",
                    question=f"“{binding.label}”还没有落实为可执行的数据条件，请确认对应字段和值。",
                    reason="系统识别到了过滤意图，但模型没有给出数据库中的实际过滤值；为避免扩大统计范围，本次查询不会直接执行。",
                    options=[],
                )
            )
        if metrics:
            clarifications = [item for item in clarifications if item.id != "metric"]
        ranking = draft.ranking.model_copy(deep=True)

        candidate = QueryPlanV1(
            intent=draft.intent,
            metrics=metrics,
            dimensions=list(dict.fromkeys(draft.dimensions)),
            date_range=date_range,
            filters=filters,
            comparison=Comparison(
                type=draft.comparison_type,
                grain=draft.comparison_grain if draft.comparison_type != "none" else None,
            ),
            ranking=ranking,
            assumptions=draft.assumptions,
            clarifications=clarifications,
            semantic_bindings=draft.semantic_bindings,
            semantics=draft.semantics,
            provenance=PlanProvenance(
                model=self.settings.sqlpilot_bailian_model,
                prompt_version=PROMPT_VERSION,
            ),
        )
        if current_plan is None:
            return candidate
        # A topic switch is not a revision of the previous data query.
        if candidate.intent == "unsupported":
            return candidate

        changed = set(draft.changed_fields)
        previous = current_plan.model_dump(exclude={"provenance"})
        proposed = candidate.model_dump(exclude={"provenance"})
        field_map = {
            "intent": "intent",
            "metrics": "metrics",
            "dimensions": "dimensions",
            "date_range": "date_range",
            "filters": "filters",
            "comparison": "comparison",
            "ranking": "ranking",
            "assumptions": "assumptions",
            "clarifications": "clarifications",
            "semantic_bindings": "semantic_bindings",
            "semantics": "semantics",
        }
        for change_name, plan_field in field_map.items():
            if change_name not in changed:
                proposed[plan_field] = previous[plan_field]
        proposed = self._protect_unmentioned_requirements(previous, proposed, latest_user_message, changed)
        proposed["metric"] = proposed["metrics"][0] if proposed["metrics"] else None
        proposed["provenance"] = candidate.provenance.model_dump()
        return QueryPlanV1.model_validate(proposed)

    @staticmethod
    def _protect_unmentioned_requirements(
        previous: dict,
        proposed: dict,
        latest_user_message: str,
        changed: set[str],
    ) -> dict:
        """Prevent a revision from deleting requirements the user did not revoke.

        This guard is intentionally conservative: it never adds a new business
        requirement. It only accepts destructive changes when the latest message
        explicitly names the requirement being removed.
        """
        text = re.sub(r"\s+", "", latest_user_message)
        removable_dimension = {
            "month": any(phrase in text for phrase in ("不按月", "不分月", "不要月份", "去掉月份", "取消月份")),
            "institution": any(phrase in text for phrase in ("不按机构", "不分机构", "全部机构汇总", "汇总所有机构")),
            "institution_level": any(phrase in text for phrase in ("不按机构等级", "不分机构等级", "取消机构等级")),
        }
        if "dimensions" in changed:
            proposed_dimensions = list(proposed["dimensions"])
            for dimension in previous["dimensions"]:
                if dimension not in proposed_dimensions and not removable_dimension.get(dimension, False):
                    proposed_dimensions.append(dimension)
            proposed["dimensions"] = proposed_dimensions

        cancels_comparison = any(
            phrase in text
            for phrase in ("不比较", "不对比", "取消对比", "取消同比", "不要同比", "取消环比", "不要环比")
        )
        if (
            "comparison" in changed
            and previous["comparison"]["type"] != "none"
            and proposed["comparison"]["type"] == "none"
            and not cancels_comparison
        ):
            proposed["comparison"] = previous["comparison"].copy()

        period_total = any(phrase in text for phrase in ("按年度累计", "年度累计", "按年累计", "期间累计", "不按月份"))
        if period_total and proposed["comparison"]["type"] != "none":
            proposed["comparison"]["grain"] = "period_total"
            proposed["dimensions"] = [item for item in proposed["dimensions"] if item != "month"]
        return proposed

    @staticmethod
    def _sanitize_clarifications(items: list[Clarification]) -> list[Clarification]:
        allowed = {
            "metric": {"fund_pay_total", "total_fee", "settlement_count"},
            "ranking_scope": {"global", "within_institution", "within_dimension", "overall_month"},
        }
        result = []
        for item in items:
            values = allowed.get(item.id)
            if values is not None:
                item.options = [option for option in item.options if option.value in values]
            else:
                item.options = [
                    option for option in item.options
                    if re.fullmatch(r"[\w.:-]{1,512}", option.value, flags=re.UNICODE)
                ]
            result.append(item)
        return result

    @staticmethod
    def _ranking_scope_clarification() -> Clarification:
        from app.planning.models import ClarificationOption

        return Clarification(
            id="ranking_scope",
            question="增长较高的月份应该在哪个范围内比较？",
            reason="不同排名范围会得到不同结果，需要由你确认。",
            options=[
                ClarificationOption(value="within_institution", label="每家机构分别比较"),
                ClarificationOption(value="global", label="所有机构和月份统一比较"),
                ClarificationOption(value="overall_month", label="全部机构汇总后按月比较"),
            ],
        )
