from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.planning.models import QueryFilter, QueryPlanV1, SemanticBinding
from app.text_to_sql.schema import SchemaContext, TableInfo


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    strategy: str = "deterministic_ir_v1"


class DeterministicQueryCompiler:
    """Compile the supported analytics subset without asking an LLM to write SQL."""

    TIME_GRAINS = {"day", "week", "month", "quarter", "year"}

    def compile(self, plan: QueryPlanV1, context: SchemaContext) -> CompiledQuery | None:
        if plan.intent != "aggregate_analysis" or not plan.metrics:
            return None
        if plan.ranking.scope in {"within_institution", "within_dimension"}:
            return None
        metric_bindings = self._bindings(plan, "metric", plan.metrics)
        dimension_bindings = self._bindings(plan, "dimension", plan.dimensions, allow_time_grain_from_time=True)
        filter_bindings = self._filter_bindings(plan)
        if metric_bindings is None or dimension_bindings is None or filter_bindings is None:
            return None
        if any(item.aggregation not in {"sum", "count", "count_distinct", "avg", "min", "max"}
               for item in metric_bindings.values()):
            return None
        all_bindings = list(metric_bindings.values()) + list(dimension_bindings.values()) + list(filter_bindings.values())
        table_keys = {(item.schema_name, item.table_name) for item in all_bindings}
        if len(table_keys) != 1:
            return None
        schema_name, table_name = next(iter(table_keys))
        table = next((item for item in context.tables if (item.schema, item.name) == (schema_name, table_name)), None)
        if table is None:
            return None
        time_binding = self._time_binding(plan, dimension_bindings)
        if plan.date_range.start and plan.date_range.end and time_binding is None:
            return None
        if time_binding and (time_binding.schema_name, time_binding.table_name) != (schema_name, table_name):
            return None

        if plan.comparison.type == "year_over_year":
            if not plan.date_range.comparison_start or not plan.date_range.comparison_end:
                return None
            sql = self._compile_yoy(plan, table, metric_bindings, dimension_bindings, filter_bindings, time_binding)
        elif plan.comparison.type == "month_over_month":
            grain = plan.comparison.grain or ("month" if "month" in plan.dimensions else None)
            if grain not in self.TIME_GRAINS or grain not in plan.dimensions:
                return None
            sql = self._compile_period_over_period(
                plan, table, metric_bindings, dimension_bindings, filter_bindings, time_binding, grain
            )
        else:
            sql = self._compile_plain(plan, table, metric_bindings, dimension_bindings, filter_bindings, time_binding)
        return CompiledQuery(sql)

    def _compile_plain(self, plan, table, metrics, dimensions, filters, time_binding) -> str:
        select_items, group_items = self._dimension_selects(dimensions, time_binding, table)
        select_items += [self._metric_expression(item, "t") + f" AS {self._q(key)}" for key, item in metrics.items()]
        where = self._where(plan, table, filters, time_binding, comparison=False)
        sql = f"SELECT {', '.join(select_items)}\nFROM {self._table(table)} AS t\nWHERE {where}"
        if group_items:
            sql += "\nGROUP BY " + ", ".join(group_items)
        sql += self._order_and_limit(plan, dimensions)
        return sql

    def _compile_yoy(self, plan, table, metrics, dimensions, filters, time_binding) -> str:
        dimension_selects, group_items = self._dimension_selects(dimensions, time_binding, table)
        metric_selects = [self._metric_expression(item, "t") + f" AS {self._q(key)}" for key, item in metrics.items()]
        current_where = self._where(plan, table, filters, time_binding, comparison=False)
        previous_where = self._where(plan, table, filters, time_binding, comparison=True)
        group_clause = "\n  GROUP BY " + ", ".join(group_items) if group_items else ""
        cte_select = ", ".join(dimension_selects + metric_selects)
        current = f"current_data AS (\n  SELECT {cte_select}\n  FROM {self._table(table)} AS t\n  WHERE {current_where}{group_clause}\n)"
        previous = f"year_ago_data AS (\n  SELECT {cte_select}\n  FROM {self._table(table)} AS t\n  WHERE {previous_where}{group_clause}\n)"
        outer_dimensions = [f"c.{self._q(key)}" for key in dimensions]
        outer_metrics: list[str] = []
        for key in metrics:
            qkey = self._q(key)
            outer_metrics.extend([
                f"c.{qkey} AS {qkey}",
                f"p.{qkey} AS {self._q('prev_' + key)}",
                f"ROUND((c.{qkey} - p.{qkey}) * 100.0 / NULLIF(p.{qkey}, 0), 2) AS {self._q(key + '_yoy_rate')}",
            ])
        if dimensions:
            joins = []
            time_grain = plan.comparison.grain if plan.comparison.grain in self.TIME_GRAINS else next(
                (key for key in dimensions if key in self.TIME_GRAINS), None
            )
            for key in dimensions:
                qkey = self._q(key)
                if key == time_grain == "week":
                    joins.extend([
                        f"EXTRACT(ISOYEAR FROM c.{qkey}) = EXTRACT(ISOYEAR FROM p.{qkey}) + 1",
                        f"EXTRACT(WEEK FROM c.{qkey}) = EXTRACT(WEEK FROM p.{qkey})",
                    ])
                elif key == time_grain:
                    joins.append(f"c.{qkey} = p.{qkey} + INTERVAL '1 year'")
                else:
                    joins.append(f"c.{qkey} = p.{qkey}")
            from_clause = "current_data AS c LEFT JOIN year_ago_data AS p ON " + " AND ".join(joins)
        else:
            from_clause = "current_data AS c CROSS JOIN year_ago_data AS p"
        sql = f"WITH {current},\n{previous}\nSELECT {', '.join(outer_dimensions + outer_metrics)}\nFROM {from_clause}"
        sql += self._order_and_limit(plan, dimensions)
        return sql

    def _compile_period_over_period(self, plan, table, metrics, dimensions, filters, time_binding, grain) -> str:
        dimension_selects, group_items = self._dimension_selects(dimensions, time_binding, table)
        metric_selects = [self._metric_expression(item, "t") + f" AS {self._q(key)}" for key, item in metrics.items()]
        where = self._period_comparison_where(plan, table, filters, time_binding, grain)
        previous_interval = "3 months" if grain == "quarter" else f"1 {grain}"
        joins = [f"p.{self._q(grain)} = c.{self._q(grain)} - INTERVAL '{previous_interval}'"]
        joins.extend(
            f"p.{self._q(key)} IS NOT DISTINCT FROM c.{self._q(key)}"
            for key in dimensions if key != grain
        )
        outputs = [f"c.{self._q(key)}" for key in dimensions]
        for key in metrics:
            qkey = self._q(key)
            outputs.extend([
                f"c.{qkey} AS {qkey}",
                f"p.{qkey} AS {self._q('prev_' + key)}",
                f"ROUND((c.{qkey} - p.{qkey}) * 100.0 / NULLIF(p.{qkey}, 0), 2) AS {self._q(key + '_mom_rate')}",
            ])
        outer_where = ""
        if plan.date_range.start:
            outer_where = (
                f"\nWHERE c.{self._q(grain)} >= "
                f"DATE_TRUNC('{grain}', {self._literal(plan.date_range.start.isoformat())}::timestamp)::date"
            )
        return (
            f"WITH period_data AS (\n  SELECT {', '.join(dimension_selects + metric_selects)}\n"
            f"  FROM {self._table(table)} AS t\n  WHERE {where}\n  GROUP BY {', '.join(group_items)}\n)\n"
            f"SELECT {', '.join(outputs)}\nFROM period_data AS c\n"
            f"LEFT JOIN period_data AS p ON {' AND '.join(joins)}" + outer_where
            + self._order_and_limit(plan, dimensions)
        )

    def _period_comparison_where(self, plan, table, filters, time_binding, grain) -> str:
        clauses = [self._filter_expression(item, filters[item.field], "t") for item in plan.filters]
        if time_binding and plan.date_range.start and plan.date_range.end:
            time_expr = self._time_expression(time_binding, table, "t")
            start = self._literal(plan.date_range.start.isoformat())
            end = self._literal((plan.date_range.end + timedelta(days=1)).isoformat())
            previous_interval = "3 months" if grain == "quarter" else f"1 {grain}"
            clauses.extend([
                f"{time_expr} >= DATE_TRUNC('{grain}', {start}::timestamp) - INTERVAL '{previous_interval}'",
                f"{time_expr} < {end}",
            ])
        columns = {item.name for item in table.columns}
        if "valid_settlement_only" in plan.default_policies and "vali_flag" in columns:
            clauses.append(f"t.{self._q('vali_flag')} = '1'")
        if "exclude_cancelled" in plan.default_policies and "refd_setl_flag" in columns:
            clauses.append(f"COALESCE(t.{self._q('refd_setl_flag')}, '0') <> '1'")
        return " AND ".join(clauses) if clauses else "TRUE"

    def _where(self, plan, table, filters, time_binding, *, comparison: bool) -> str:
        clauses = [self._filter_expression(item, filters[item.field], "t") for item in plan.filters]
        if time_binding and plan.date_range.start and plan.date_range.end:
            start = plan.date_range.comparison_start if comparison else plan.date_range.start
            end = plan.date_range.comparison_end if comparison else plan.date_range.end
            time_expr = self._time_expression(time_binding, table, "t")
            clauses.extend([
                f"{time_expr} >= {self._literal(start.isoformat())}",
                f"{time_expr} < {self._literal((end + timedelta(days=1)).isoformat())}",
            ])
        columns = {item.name for item in table.columns}
        if "valid_settlement_only" in plan.default_policies and "vali_flag" in columns:
            clauses.append(f"t.{self._q('vali_flag')} = '1'")
        if "exclude_cancelled" in plan.default_policies and "refd_setl_flag" in columns:
            clauses.append(f"COALESCE(t.{self._q('refd_setl_flag')}, '0') <> '1'")
        return " AND ".join(clauses) if clauses else "TRUE"

    def _dimension_selects(self, dimensions, time_binding, table):
        selects, groups = [], []
        for key, binding in dimensions.items():
            expression = (
                f"DATE_TRUNC('{key}', {self._time_expression(time_binding or binding, table, 't')})::date"
                if key in self.TIME_GRAINS else f"t.{self._q(binding.column_name)}"
            )
            selects.append(f"{expression} AS {self._q(key)}")
            groups.append(expression)
        return selects, groups

    @staticmethod
    def _bindings(plan, role, keys, allow_time_grain_from_time=False):
        result = {}
        for key in keys:
            binding = next((item for item in plan.semantic_bindings if item.role == role and item.key == key), None)
            if binding is None and allow_time_grain_from_time and key in DeterministicQueryCompiler.TIME_GRAINS:
                binding = next((item for item in plan.semantic_bindings if item.role == "time"), None)
            if binding is None:
                return None
            result[key] = binding
        return result

    @staticmethod
    def _filter_bindings(plan):
        result = {}
        bindings = [item for item in plan.semantic_bindings if item.role == "filter"]
        for query_filter in plan.filters:
            binding = next((item for item in bindings if query_filter.field in {item.key, item.column_name, item.object_key}), None)
            if binding is None:
                return None
            result[query_filter.field] = binding
        return result

    @staticmethod
    def _time_binding(plan, dimensions):
        binding = next((item for item in plan.semantic_bindings if item.role == "time"), None)
        return binding or next(
            (dimensions[key] for key in DeterministicQueryCompiler.TIME_GRAINS if key in dimensions), None
        )

    def _metric_expression(self, binding, alias):
        column = f"{alias}.{self._q(binding.column_name)}"
        operations = {
            "sum": f"SUM({column})", "count": f"COUNT({column})",
            "count_distinct": f"COUNT(DISTINCT {column})", "avg": f"AVG({column})",
            "min": f"MIN({column})", "max": f"MAX({column})",
        }
        if binding.aggregation not in operations:
            raise ValueError(f"unsupported metric aggregation: {binding.aggregation}")
        return operations[binding.aggregation]

    def _filter_expression(self, query_filter: QueryFilter, binding: SemanticBinding, alias: str) -> str:
        column = f"{alias}.{self._q(binding.column_name)}"
        value = query_filter.value
        if query_filter.operator == "in":
            values = value if isinstance(value, list) else [value]
            return f"{column} IN ({', '.join(self._literal(item) for item in values)})"
        if query_filter.operator == "between" and isinstance(value, list) and len(value) == 2:
            return f"{column} BETWEEN {self._literal(value[0])} AND {self._literal(value[1])}"
        operators = {"eq": "=", "ne": "<>", "gte": ">=", "lte": "<=", "contains": "ILIKE"}
        rendered = f"%{value}%" if query_filter.operator == "contains" else value
        return f"{column} {operators[query_filter.operator]} {self._literal(rendered)}"

    def _order_and_limit(self, plan, dimensions) -> str:
        order = ""
        if plan.ranking.scope or plan.ranking.limit or plan.ranking.metric != "metric_value":
            field = plan.ranking.metric
            if field == "metric_value":
                field = plan.metrics[0]
            elif field in {"yoy_rate", "mom_rate"}:
                field = plan.metrics[0] + "_" + field
            order = f"\nORDER BY {self._q(field)} {plan.ranking.direction.upper()}"
        elif dimensions:
            order = "\nORDER BY " + ", ".join(self._q(key) for key in dimensions)
        if plan.ranking.limit:
            order += f"\nLIMIT {int(plan.ranking.limit)}"
        return order

    def _time_expression(self, binding, table, alias):
        column = f"{alias}.{self._q(binding.column_name)}"
        data_type = ""
        if table:
            info = next((item for item in table.columns if item.name == binding.column_name), None)
            data_type = info.data_type.lower() if info else ""
        if data_type in {"date", "timestamp", "timestamp without time zone", "timestamp with time zone"}:
            return column
        return f"NULLIF({column}, '')::timestamp"

    def _table(self, table: TableInfo) -> str:
        return f"{self._q(table.schema)}.{self._q(table.name)}"

    @staticmethod
    def _q(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _literal(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"
