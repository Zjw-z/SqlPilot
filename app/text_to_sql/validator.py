from __future__ import annotations

from dataclasses import dataclass, field
import re
from datetime import timedelta

import sqlglot
from sqlglot import exp

from app.text_to_sql.schema import SchemaContext
from app.planning.models import QueryPlanV1


@dataclass
class SqlValidation:
    errors: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


class PostgresSqlValidator:
    FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)

    def validate(self, sql: str, context: SchemaContext, plan: QueryPlanV1 | None = None) -> SqlValidation:
        result = SqlValidation()
        try:
            statements = sqlglot.parse(sql, read="postgres")
        except sqlglot.errors.ParseError as exc:
            result.errors.append(f"PostgreSQL语法错误：{exc}")
            return result
        if len(statements) != 1:
            result.errors.append("只允许单条SQL")
            return result
        statement = statements[0]
        if any(statement.find(kind) for kind in self.FORBIDDEN):
            result.errors.append("SQL包含禁止的写入或DDL操作")
        if not statement.find(exp.Select) and not isinstance(statement, exp.Select):
            result.errors.append("只允许SELECT查询")
        ctes = {cte.alias for cte in statement.find_all(exp.CTE)}
        physical_tables = [table for table in statement.find_all(exp.Table) if table.name not in ctes]
        table_aliases: dict[str, tuple[str, str]] = {}
        for table in physical_tables:
            schema_name = table.db or ""
            matches = [item for item in context.tables if item.name == table.name and (not schema_name or item.schema == schema_name)]
            if len(matches) != 1:
                result.errors.append(f"引用未授权或存在歧义的表：{schema_name + '.' if schema_name else ''}{table.name}")
                continue
            target = (matches[0].schema, matches[0].name)
            table_aliases[table.alias_or_name] = target
            table_aliases[table.name] = target
        referenced_columns = {column.name for column in statement.find_all(exp.Column)}
        unknown_columns = referenced_columns - context.allowed_columns
        # CTE output aliases are safe and do not exist in the physical catalog.
        aliases = {alias.alias for alias in statement.find_all(exp.Alias)}
        unknown_columns -= aliases
        if unknown_columns:
            result.errors.append("引用未知字段：" + ", ".join(sorted(unknown_columns)))
        for column in statement.find_all(exp.Column):
            if not column.table or column.table not in table_aliases:
                continue
            target = table_aliases[column.table]
            if column.name not in context.columns_by_table.get(target, set()) and column.name not in aliases:
                result.errors.append(f"字段不属于指定表：{column.table}.{column.name}")
        normalized = " ".join(sql.lower().split())
        if re.search(r"<=\s*'\d{4}-\d{2}-\d{2}\s+23:59:59(?:\.0+)?'", normalized):
            result.errors.append("时间戳结束边界必须使用小于次日零点的半开区间，不能使用23:59:59")
        if plan:
            semantics = plan.semantics
            top_select = statement if isinstance(statement, exp.Select) else statement.find(exp.Select)
            if semantics.confidence >= 0.75 and top_select is not None:
                if semantics.output_fields and len(top_select.expressions) != len(semantics.output_fields):
                    result.errors.append(
                        f"SQL输出列数量与语义计划不一致：计划{len(semantics.output_fields)}列，SQL为{len(top_select.expressions)}列"
                    )
                if semantics.group_by and statement.find(exp.Group) is None:
                    result.errors.append("语义计划要求分组，但SQL缺少GROUP BY")
                if semantics.distinct_keys and any(statement.find(kind) for kind in (exp.Count, exp.Sum)):
                    if statement.find(exp.Distinct) is None:
                        result.errors.append("聚合查询存在业务去重键，但SQL未实现DISTINCT实体粒度")
                if semantics.output_expressions and top_select is not None:
                    aliases_in_order = [item.alias_or_name for item in top_select.expressions]
                    expected_aliases = [str(item.get("alias") or item.get("key") or "") for item in semantics.output_expressions]
                    expected_aliases = [item for item in expected_aliases if item]
                    if expected_aliases and aliases_in_order != expected_aliases:
                        result.errors.append("SQL输出列别名或顺序与语义计划output_expressions不一致")
                if semantics.having and statement.find(exp.Having) is None:
                    result.errors.append("语义计划包含聚合后过滤，但SQL缺少HAVING")
                if semantics.ordering and statement.args.get("order") is None:
                    result.errors.append("语义计划要求排序，但SQL缺少ORDER BY")
                operator_tokens = {
                    "union": exp.Union, "intersect": exp.Intersect, "except": exp.Except,
                }
                expected = operator_tokens.get(semantics.logical_operator)
                if expected and statement.find(expected) is None:
                    result.errors.append(f"语义计划要求{semantics.logical_operator.upper()}集合逻辑，但SQL未实现")
                if semantics.logical_operator == "not_exists" and "not exists" not in normalized:
                    result.errors.append("语义计划要求NOT EXISTS反集合逻辑，但SQL未实现")
            for metric in plan.metrics:
                if metric not in aliases:
                    result.errors.append(f"SQL缺少计划指标结果列：{metric}")
            period_start = plan.date_range.start
            period_end = plan.date_range.end
            if period_start and period_start.isoformat() not in normalized:
                result.errors.append(f"SQL没有覆盖计划中的开始日期：{period_start.isoformat()}")
            if period_end:
                accepted_ends = {period_end.isoformat(), (period_end + timedelta(days=1)).isoformat()}
                if not any(value in normalized for value in accepted_ends):
                    result.errors.append(f"SQL没有覆盖计划中的结束日期：{period_end.isoformat()}")
            if plan.comparison.type == "none" and any(token in normalized for token in ("_yoy", "yoy_rate", "year_ago_data")):
                result.errors.append("查询计划未要求同比，SQL不得擅自增加同比计算")
            explicit_ranking = bool(
                plan.ranking.scope or plan.ranking.limit or plan.ranking.metric != "metric_value"
            )
            if (
                not explicit_ranking
                and statement.args.get("order") is not None
                and not self._orders_only_by_dimensions(statement, plan)
            ):
                result.errors.append("查询计划未要求排序，SQL不得擅自增加顶层排序")
            for query_filter in plan.filters:
                field_name = query_filter.field.rsplit(".", 1)[-1].lower()
                if field_name not in normalized:
                    result.errors.append(f"SQL缺少计划过滤字段：{query_filter.field}")
                values = query_filter.value if isinstance(query_filter.value, list) else [query_filter.value]
                for value in values:
                    if str(value).lower() not in normalized:
                        result.errors.append(f"SQL缺少计划过滤值：{query_filter.display_value}={value}")
        if plan and plan.comparison.type == "year_over_year":
            monthly_comparison = plan.comparison.grain == "month"
            if monthly_comparison and re.search(r"\b(?:c|cur|current_data)\.\w+\s*=\s*(?:y|p|prev|year_ago_data)\.\w+\s*-\s*interval\s*'1 year'", normalized):
                result.errors.append("同比月份关联方向错误：当前月份不能等于同期月份减一年")
            if not re.search(r"(?:\*\s*100(?:\.0)?|100(?:\.0)?\s*\*)", normalized):
                result.errors.append("同比增长率没有转换为百分比")
            if re.search(r"nullif\([^,)]*-[^,)]*,\s*0\s*\)", normalized):
                result.errors.append("同比公式错误：不能对增长差额使用NULLIF，零增长应返回0")
            comparison_start = plan.date_range.comparison_start
            comparison_end = plan.date_range.comparison_end
            if comparison_start and comparison_start.isoformat() not in normalized:
                result.errors.append(f"SQL没有覆盖计划中的同期开始日期：{comparison_start.isoformat()}")
            if comparison_end:
                accepted_ends = {comparison_end.isoformat(), (comparison_end + timedelta(days=1)).isoformat()}
                if not any(value in normalized for value in accepted_ends):
                    result.errors.append(f"SQL没有覆盖计划中的同期结束日期：{comparison_end.isoformat()}")
        if plan and plan.ranking.metric == "yoy_rate" and (plan.ranking.scope or plan.ranking.limit):
            order_part = normalized.rsplit("order by", 1)[-1] if "order by" in normalized else ""
            if "yoy_rate" not in order_part or "desc" not in order_part:
                result.errors.append("增长查询必须按yoy_rate降序排列")
        if plan and plan.ranking.scope in {"within_institution", "within_dimension"}:
            partition_keys = (
                ["institution"] if plan.ranking.scope == "within_institution"
                else plan.ranking.partition_by
            )
            expected_columns = {
                key: {
                    key.lower(),
                    *(binding.column_name.lower() for binding in plan.semantic_bindings
                      if binding.role == "dimension" and binding.key == key),
                }
                for key in partition_keys
            }
            windows = list(statement.find_all(exp.Window))
            partitioned = any(
                all(
                    expected_columns[key] & {
                        column.name.lower() for part in (window.args.get("partition_by") or [])
                        for column in part.find_all(exp.Column)
                    }
                    for key in partition_keys
                )
                for window in windows
            )
            if not partitioned:
                result.errors.append("分组排名SQL缺少与计划一致的PARTITION BY，不能退化为全局排名")
            if statement.args.get("limit") is not None:
                result.errors.append("分组排名不能使用顶层全局LIMIT")
            window_aliases = {
                alias.alias.lower() for alias in statement.find_all(exp.Alias)
                if isinstance(alias.this, exp.Window)
            }
            has_rank_filter = any(
                column.name.lower() in window_aliases
                for where in statement.find_all(exp.Where)
                for column in where.find_all(exp.Column)
            ) or statement.find(exp.Qualify) is not None
            if plan.ranking.limit and not has_rank_filter:
                result.errors.append("分组排名SQL缺少按每组排名结果筛选Top N")
        if not result.errors:
            result.passed.extend(["单条PostgreSQL只读查询", "表和字段均来自动态Schema白名单"])
        return result

    @staticmethod
    def _orders_only_by_dimensions(statement: exp.Expression, plan: QueryPlanV1) -> bool:
        """Allow presentation ordering by confirmed dimensions without treating it as ranking."""
        order = statement.args.get("order")
        if not order:
            return True
        dimension_names = {item.lower() for item in plan.dimensions}
        for binding in plan.semantic_bindings:
            if binding.role == "dimension":
                dimension_names.update({binding.key.lower(), binding.column_name.lower()})
        for ordered in order.expressions:
            expression = ordered.this if isinstance(ordered, exp.Ordered) else ordered
            names = {column.name.lower() for column in expression.find_all(exp.Column)}
            if isinstance(expression, exp.Column):
                names.add(expression.name.lower())
            if not names or any(
                not any(name == dimension or name.endswith(f"_{dimension}") or dimension in name for dimension in dimension_names)
                for name in names
            ):
                return False
        return True
