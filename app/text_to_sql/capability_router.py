from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.planning.models import QueryPlanV1, SemanticBinding
from app.text_to_sql.compiler import CompiledQuery, DeterministicQueryCompiler
from app.text_to_sql.schema import SchemaContext


RouteName = Literal["deterministic", "model_fallback", "clarify", "reject", "resync_schema"]


@dataclass(frozen=True)
class RouteDecision:
    route: RouteName
    reason_code: str
    message: str
    compiled: CompiledQuery | None = None
    required_capabilities: list[str] = field(default_factory=list)
    unsupported_capabilities: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def evidence(self) -> dict:
        return {
            "route": self.route,
            "reason_code": self.reason_code,
            "required_capabilities": self.required_capabilities,
            "unsupported_capabilities": self.unsupported_capabilities,
            "missing": self.missing,
            "risks": self.risks,
        }


class CapabilityRouter:
    """Route only semantically complete plans; an LLM is never a substitute for missing facts."""

    SUPPORTED_AGGREGATIONS = {"sum", "count", "count_distinct", "avg", "min", "max"}
    DETERMINISTIC_TIME_GRAINS = {"day", "week", "month", "quarter", "year"}

    def __init__(self, compiler: DeterministicQueryCompiler | None = None) -> None:
        self.compiler = compiler or DeterministicQueryCompiler()

    def decide(self, plan: QueryPlanV1, context: SchemaContext) -> RouteDecision:
        capabilities = self._required_capabilities(plan)
        if plan.needs_clarification:
            return self._decision("clarify", "PLAN_REQUIRES_CLARIFICATION", "查询计划仍有待确认问题", capabilities)
        if plan.intent == "unsupported":
            return self._decision("reject", "UNSUPPORTED_INTENT", "当前请求不属于可执行的数据查询", capabilities)

        missing = self._missing_bindings(plan)
        if missing:
            return self._decision(
                "clarify", "MISSING_SEMANTIC_BINDING", "查询计划缺少明确的字段或统计口径绑定",
                capabilities, missing=missing,
            )

        invalid_objects = self._invalid_schema_objects(plan, context)
        if invalid_objects:
            return self._decision(
                "resync_schema", "SCHEMA_OBJECT_NOT_FOUND", "计划引用的表或字段不在当前Schema版本中",
                capabilities, missing=invalid_objects,
            )

        metric_bindings = self._bindings(plan, "metric")
        invalid_aggregations = [
            f"{item.key}:{item.aggregation}" for item in metric_bindings
            if item.aggregation not in self.SUPPORTED_AGGREGATIONS
        ]
        if invalid_aggregations:
            return self._decision(
                "clarify", "MISSING_METRIC_AGGREGATION", "指标缺少受支持的聚合口径",
                capabilities, missing=invalid_aggregations,
            )

        if plan.comparison.type == "month_over_month":
            grain = plan.comparison.grain or ("month" if "month" in plan.dimensions else None)
            if grain == "period_total" or grain not in self.DETERMINISTIC_TIME_GRAINS:
                return self._decision(
                    "clarify", "PERIOD_COMPARISON_GRAIN_REQUIRED",
                    "环比必须明确为自然日、ISO自然周、自然月、自然季度或自然年",
                    capabilities, missing=["comparison.grain"],
                )
            if grain not in plan.dimensions:
                return self._decision(
                    "clarify", "PERIOD_COMPARISON_REQUIRES_TIME_DIMENSION",
                    f"{grain}环比需要对应的时间分析维度",
                    capabilities, missing=[f"dimension:{grain}"],
                )
        if plan.comparison.type == "year_over_year" and (
            not plan.date_range.comparison_start or not plan.date_range.comparison_end
        ):
            return self._decision(
                "clarify", "YOY_REQUIRES_COMPARISON_PERIOD", "同比需要完整的上年同期范围",
                capabilities, missing=["date_range.comparison_start", "date_range.comparison_end"],
            )
        if plan.comparison.type == "year_over_year":
            grain = plan.comparison.grain
            if grain not in self.DETERMINISTIC_TIME_GRAINS | {"period_total"}:
                return self._decision(
                    "clarify", "YOY_GRAIN_REQUIRED", "同比必须明确自然时间粒度或期间累计口径",
                    capabilities, missing=["comparison.grain"],
                )
            if grain != "period_total" and grain not in plan.dimensions:
                return self._decision(
                    "clarify", "YOY_REQUIRES_TIME_DIMENSION", f"{grain}同比需要对应的时间分析维度",
                    capabilities, missing=[f"dimension:{grain}"],
                )

        tables = {(item.schema_name, item.table_name) for item in plan.semantic_bindings}
        if len(tables) > 1 and not self._has_connected_join_path(tables, context):
            return self._decision(
                "clarify", "UNVERIFIED_JOIN_PATH", "多表查询缺少经过验证的完整JOIN路径",
                capabilities, missing=["verified_join_path"], risks=["多表连接可能造成错误匹配或重复聚合"],
            )

        forced_fallback = self._unsupported_capabilities(plan, tables, include_generic=False)
        if forced_fallback:
            return self._decision(
                "model_fallback", "SEMANTICS_COMPLETE_BUT_EXPRESSION_UNSUPPORTED",
                "业务语义和Schema绑定完整，但SQL表达超出确定性编译器范围",
                capabilities, unsupported=forced_fallback,
            )

        compiled = self.compiler.compile(plan, context)
        if compiled:
            return self._decision(
                "deterministic", "SUPPORTED_BY_DETERMINISTIC_COMPILER", "全部操作符均由确定性编译器支持",
                capabilities, compiled=compiled,
            )

        unsupported = self._unsupported_capabilities(plan, tables)
        return self._decision(
            "model_fallback", "SEMANTICS_COMPLETE_BUT_EXPRESSION_UNSUPPORTED",
            "业务语义和Schema绑定完整，但SQL表达超出确定性编译器范围",
            capabilities, unsupported=unsupported,
        )

    @staticmethod
    def _decision(route, code, message, capabilities=None, *, compiled=None, unsupported=None, missing=None, risks=None):
        return RouteDecision(route, code, message, compiled, capabilities or [], unsupported or [], missing or [], risks or [])

    @staticmethod
    def _bindings(plan: QueryPlanV1, role: str) -> list[SemanticBinding]:
        return [item for item in plan.semantic_bindings if item.role == role]

    def _missing_bindings(self, plan: QueryPlanV1) -> list[str]:
        missing: list[str] = []
        for role, keys in (("metric", plan.metrics), ("dimension", plan.dimensions)):
            available = {item.key for item in self._bindings(plan, role)}
            if role == "dimension" and self._bindings(plan, "time"):
                available.update(set(keys) & self.DETERMINISTIC_TIME_GRAINS)
            missing.extend(f"{role}:{key}" for key in keys if key not in available)
        filter_bindings = self._bindings(plan, "filter")
        for item in plan.filters:
            if not any(item.field in {binding.key, binding.column_name, binding.object_key} for binding in filter_bindings):
                missing.append(f"filter:{item.field}")
        if plan.date_range.start and plan.date_range.end:
            has_time = bool(self._bindings(plan, "time")) or any(
                item.key in self.DETERMINISTIC_TIME_GRAINS for item in self._bindings(plan, "dimension")
            )
            if not has_time:
                missing.append("time:date_range")
        return missing

    @staticmethod
    def _invalid_schema_objects(plan: QueryPlanV1, context: SchemaContext) -> list[str]:
        columns = context.columns_by_table
        invalid = []
        for item in plan.semantic_bindings:
            table = (item.schema_name, item.table_name)
            if table not in columns or item.column_name not in columns[table]:
                invalid.append(item.object_key)
        return list(dict.fromkeys(invalid))

    @staticmethod
    def _has_connected_join_path(tables: set[tuple[str, str]], context: SchemaContext) -> bool:
        required = {name for _, name in tables}
        if len(required) <= 1:
            return True
        graph: dict[str, set[str]] = {name: set() for name in required}
        for relation in context.relationships:
            if relation.certified:
                graph.setdefault(relation.source_table, set()).add(relation.target_table)
                graph.setdefault(relation.target_table, set()).add(relation.source_table)
        visited, pending = set(), [next(iter(required))]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(graph.get(current, set()) - visited)
        return required <= visited

    @staticmethod
    def _required_capabilities(plan: QueryPlanV1) -> list[str]:
        result = [plan.intent]
        if plan.filters:
            result.append("filter")
        if plan.dimensions:
            result.append("group_by")
        if plan.comparison.type != "none":
            result.append(plan.comparison.type)
        if plan.ranking.limit:
            result.append("top_n")
        if plan.ranking.scope in {"within_institution", "within_dimension"}:
            result.append("partitioned_ranking")
        if plan.semantics.having:
            result.append("having")
        if plan.semantics.output_expressions:
            result.append("derived_expression")
        return list(dict.fromkeys(result))

    @staticmethod
    def _unsupported_capabilities(
        plan: QueryPlanV1, tables: set[tuple[str, str]], *, include_generic: bool = True
    ) -> list[str]:
        result = []
        if len(tables) > 1:
            result.append("multi_table")
        if plan.intent != "aggregate_analysis":
            result.append(plan.intent)
        if plan.ranking.scope in {"within_institution", "within_dimension"}:
            result.append("partitioned_ranking")
        if plan.semantics.having:
            result.append("having")
        if plan.semantics.output_expressions:
            result.append("derived_expression")
        if plan.semantics.ordering:
            result.append("semantic_ordering")
        if plan.semantics.predicate_scopes:
            result.append("predicate_scope")
        if plan.semantics.distinct_keys:
            result.append("explicit_distinct_keys")
        if plan.semantics.logical_operator != "and":
            result.append(f"logical_operator:{plan.semantics.logical_operator}")
        result = list(dict.fromkeys(result))
        return result or (["unsupported_expression_combination"] if include_generic else [])
