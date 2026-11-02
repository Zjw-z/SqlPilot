from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MetricKey = str
DimensionKey = str


class SemanticBinding(BaseModel):
    role: Literal["metric", "dimension", "filter", "time"]
    key: str
    label: str
    object_key: str
    schema_name: str
    table_name: str
    column_name: str
    aggregation: Literal["sum", "count", "count_distinct", "avg", "min", "max", "none"] = "none"
    confidence: float = Field(default=0.0, ge=0, le=1)
    certified: bool = False


class SchemaEvidence(BaseModel):
    object_key: str
    business_name: str = ""
    score: float = Field(default=0.0, ge=-1, le=1)
    requires_confirmation: bool = False


class FieldCandidate(BaseModel):
    mention: str
    object_key: str
    schema_name: str = ""
    table_name: str
    column_name: str
    business_name: str = ""
    score: float = Field(default=0.0, ge=-1, le=1)
    value_match: bool = False
    matched_value: Any | None = None
    selected: bool = False


class QuerySemantics(BaseModel):
    entity_grain: str | None = None
    output_fields: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    distinct_keys: list[str] = Field(default_factory=list)
    logical_operator: Literal["and", "or", "union", "intersect", "except", "not_exists"] = "and"
    output_expressions: list[dict[str, Any]] = Field(default_factory=list)
    aggregations: list[dict[str, Any]] = Field(default_factory=list)
    having: list[dict[str, Any]] = Field(default_factory=list)
    ordering: list[dict[str, Any]] = Field(default_factory=list)
    predicate_scopes: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class ClarificationOption(BaseModel):
    value: str
    label: str
    description: str | None = None


class Clarification(BaseModel):
    id: str
    question: str
    reason: str
    options: list[ClarificationOption] = Field(default_factory=list)
    required: bool = True


class DateRange(BaseModel):
    type: Literal["current_year_to_date", "previous_year", "explicit", "all"]
    start: date | None = None
    end: date | None = None
    comparison_start: date | None = None
    comparison_end: date | None = None


class QueryFilter(BaseModel):
    field: str
    operator: Literal["eq", "ne", "in", "gte", "lte", "between", "contains"] = "eq"
    value: Any
    display_value: str


class Comparison(BaseModel):
    type: Literal["none", "month_over_month", "year_over_year"] = "none"
    # month_over_month is kept as the backwards-compatible protocol name for
    # period-over-period comparison; grain decides whether the previous
    # natural day/week/month/quarter/year is used.
    grain: Literal["day", "week", "month", "quarter", "year", "period_total"] | None = None


class Ranking(BaseModel):
    metric: Literal["metric_value", "mom_rate", "yoy_rate"] = "metric_value"
    direction: Literal["asc", "desc"] = "desc"
    scope: Literal["global", "within_institution", "within_dimension", "overall_month"] | None = None
    partition_by: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=1000)


class PlanProvenance(BaseModel):
    planner: Literal["bailian", "test"] = "bailian"
    model: str
    prompt_version: str
    catalog_version: int = 1


class QueryPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    data_source_id: str | None = None
    intent: Literal["aggregate_analysis", "detail_query", "unsupported"]
    metric: MetricKey | None = None
    metrics: list[MetricKey] = Field(default_factory=list, max_length=3)
    dimensions: list[DimensionKey] = Field(default_factory=list)
    date_range: DateRange
    filters: list[QueryFilter] = Field(default_factory=list)
    comparison: Comparison = Field(default_factory=Comparison)
    ranking: Ranking = Field(default_factory=Ranking)
    default_policies: list[Literal["valid_settlement_only", "exclude_cancelled"]] = Field(
        default_factory=list
    )
    assumptions: list[str] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)
    semantic_bindings: list[SemanticBinding] = Field(default_factory=list)
    schema_evidence: list[SchemaEvidence] = Field(default_factory=list)
    field_candidates: list[FieldCandidate] = Field(default_factory=list)
    semantics: QuerySemantics = Field(default_factory=QuerySemantics)
    provenance: PlanProvenance

    @model_validator(mode="after")
    def validate_dependencies(self):
        if self.metric and self.metric not in self.metrics:
            self.metrics.insert(0, self.metric)
        self.metrics = list(dict.fromkeys(self.metrics))
        self.metric = self.metrics[0] if self.metrics else None
        if (
            self.comparison.type == "year_over_year"
            and self.date_range.start
            and self.date_range.end
        ):
            if self.date_range.comparison_start is None:
                self.date_range.comparison_start = self._previous_year_date(self.date_range.start)
            if self.date_range.comparison_end is None:
                self.date_range.comparison_end = self._previous_year_date(self.date_range.end)
        if self.ranking.metric == "yoy_rate" and self.comparison.type != "year_over_year":
            raise ValueError("yoy_rate排序必须配合year_over_year")
        if self.ranking.scope == "within_institution" and "institution" not in self.dimensions:
            raise ValueError("机构内排名必须包含institution维度")
        if self.ranking.scope == "within_dimension":
            if not self.ranking.partition_by:
                raise ValueError("分组排名必须指定partition_by维度")
            if any(key not in self.dimensions for key in self.ranking.partition_by):
                raise ValueError("分组排名维度必须包含在查询维度中")
        elif self.ranking.partition_by:
            raise ValueError("partition_by仅适用于within_dimension排名")
        return self

    @staticmethod
    def _previous_year_date(value: date) -> date:
        """按日历年派生同期日期；2月29日在非闰年落到2月28日。"""
        try:
            return value.replace(year=value.year - 1)
        except ValueError:
            return value.replace(year=value.year - 1, day=28)

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"provenance": {"model"}})
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def needs_clarification(self) -> bool:
        return any(item.required for item in self.clarifications)
