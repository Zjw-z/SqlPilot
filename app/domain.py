from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    aliases: tuple[str, ...]
    expression: str
    description: str
    source_table: str
    required_filters: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dimension:
    key: str
    name: str
    aliases: tuple[str, ...]
    expression: str
    source_table: str


@dataclass
class QueryPlan:
    question: str
    metric: Metric | None
    dimensions: list[Dimension]
    start_date: str | None
    end_date: str | None
    institution_level: str | None = None
    top_n: int | None = None
    comparison: Literal["mom", "yoy", "none"] = "none"
    medical_type: Literal["inpatient"] | None = None
    order_by: Literal["metric", "growth"] = "metric"
    ranking_scope: Literal["global", "within_institution", "overall_month"] | None = None
    clarifications: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["metric"] = asdict(self.metric) if self.metric else None
        result["dimensions"] = [asdict(item) for item in self.dimensions]
        return result


@dataclass(frozen=True)
class JoinEdge:
    left_table: str
    right_table: str
    condition: str
    cardinality: str
    verified: bool = True
    confidence: float = 1.0


@dataclass
class ValidationReport:
    passed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class TrustReport:
    score: float
    level: Literal["A", "B", "C", "D"]
    action: Literal["auto_execute", "confirm", "review", "reject"]
    passed: list[str]
    risks: list[str]
