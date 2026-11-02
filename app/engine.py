from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict
from datetime import date
from typing import Any, Callable

import sqlglot
from sqlglot import exp

from app.catalog import JOINS, SCHEMA, VALUE_DICTIONARY
from app.database import connect, initialize_demo_database
from app.domain import JoinEdge, QueryPlan, TrustReport, ValidationReport
from app.planner import understand


EventSink = Callable[[str, dict[str, Any]], None]


class QueryRejected(ValueError):
    pass


class TrustworthyQueryEngine:
    def __init__(self, planner: Any | None = None) -> None:
        initialize_demo_database()
        self._planner = planner

    def plan(self, question: str) -> QueryPlan:
        if self._planner is not None:
            return self._planner.plan(question)
        return understand(question)

    def _required_tables(self, plan: QueryPlan) -> set[str]:
        tables = {plan.metric.source_table} if plan.metric else set()
        tables.update(item.source_table for item in plan.dimensions)
        if plan.institution_level:
            tables.add("medical_org")
        return tables

    def _join_plan(self, tables: set[str]) -> list[JoinEdge]:
        if len(tables) < 2:
            return []
        selected = [edge for edge in JOINS if edge.left_table in tables and edge.right_table in tables]
        covered = {table for edge in selected for table in (edge.left_table, edge.right_table)}
        if not tables.issubset(covered):
            raise QueryRejected("无法找到覆盖全部候选表的已验证关联路径")
        return selected

    def compile_sql(self, plan: QueryPlan, joins: list[JoinEdge]) -> tuple[str, list[Any]]:
        if not plan.metric:
            raise QueryRejected("问题没有匹配到认证指标，不能安全生成SQL")
        dimensions = plan.dimensions.copy()
        if plan.comparison in {"mom", "yoy"} and not any(item.key == "month" for item in dimensions):
            dimensions.insert(0, next(item for item in __import__("app.catalog", fromlist=["DIMENSIONS"]).DIMENSIONS if item.key == "month"))
            plan.assumptions.append("同期分析自动增加结算月份维度")

        select_parts = [f"{item.expression} AS {item.key}" for item in dimensions]
        select_parts.append(f"{plan.metric.expression} AS metric_value")
        tables = self._required_tables(plan)
        from_clause = "settlement s" if "settlement" in tables else "medical_org o"
        join_clause = "".join(f"\nLEFT JOIN {edge.right_table} o ON {edge.condition}" for edge in joins)
        where = list(plan.metric.required_filters)
        params: list[Any] = []
        query_start = plan.start_date
        if plan.comparison == "yoy" and plan.start_date:
            start = date.fromisoformat(plan.start_date)
            query_start = start.replace(year=start.year - 1).isoformat()
        if plan.start_date:
            where.append("s.settle_date BETWEEN ? AND ?")
            params.extend((query_start, plan.end_date))
        if plan.medical_type == "inpatient":
            where.append("s.medical_type = '21'")
        if plan.institution_level:
            field, value = VALUE_DICTIONARY[plan.institution_level]
            where.append(f"{field} = ?")
            params.append(value)
        group_by = ", ".join(item.expression for item in dimensions)
        inner = "SELECT\n  " + ",\n  ".join(select_parts)
        inner += f"\nFROM {from_clause}{join_clause}"
        if where:
            inner += "\nWHERE " + " AND ".join(where)
        if group_by:
            inner += f"\nGROUP BY {group_by}"

        if plan.comparison == "mom":
            partition = [item.key for item in dimensions if item.key != "month"]
            partition_sql = f"PARTITION BY {', '.join(partition)} " if partition else ""
            sql = (
                "WITH base AS (\n" + inner + "\n)\n"
                "SELECT *, ROUND((metric_value - LAG(metric_value) OVER ("
                f"{partition_sql}ORDER BY month)) * 100.0 / NULLIF(LAG(metric_value) OVER ("
                f"{partition_sql}ORDER BY month), 0), 2) AS mom_rate\nFROM base"
            )
        elif plan.comparison == "yoy":
            join_keys = [item.key for item in dimensions if item.key != "month"]
            key_join = "".join(f" AND cur.{key} = prev.{key}" for key in join_keys)
            sql = (
                "WITH base AS (\n" + inner + "\n)\n"
                "SELECT cur.*, prev.metric_value AS same_period_value, "
                "ROUND((cur.metric_value - prev.metric_value) * 100.0 / NULLIF(prev.metric_value, 0), 2) AS yoy_rate\n"
                "FROM base cur\nLEFT JOIN base prev ON prev.month = strftime('%Y-%m', date(cur.month || '-01', '-1 year'))"
                f"{key_join}\nWHERE cur.month BETWEEN ? AND ?"
            )
            params.extend((plan.start_date[:7], plan.end_date[:7]))
        else:
            sql = inner
        order_field = "yoy_rate" if plan.order_by == "growth" and plan.comparison == "yoy" else "metric_value"
        if plan.ranking_scope == "within_institution" and plan.top_n and any(item.key == "institution" for item in dimensions):
            sql = (
                "WITH ranked_result AS (\nSELECT compared.*, ROW_NUMBER() OVER (PARTITION BY institution "
                f"ORDER BY {order_field} DESC) AS rank_no\nFROM (\n{sql}\n) compared\n)\n"
                "SELECT * FROM ranked_result WHERE rank_no <= ?\nORDER BY institution, rank_no"
            )
            params.append(plan.top_n)
        else:
            sql += f"\nORDER BY {order_field} DESC"
            if plan.top_n:
                sql += "\nLIMIT ?"
                params.append(plan.top_n)
        return sql, params

    def validate(self, sql: str, joins: list[JoinEdge]) -> ValidationReport:
        report = ValidationReport()
        normalized = re.sub(r"\s+", " ", sql.strip()).upper()
        try:
            statements = sqlglot.parse(sql, read="sqlite")
            if len(statements) != 1:
                report.errors.append("禁止执行多条SQL语句")
            elif not isinstance(statements[0], (exp.Select, exp.Union)) and not statements[0].find(exp.Select):
                report.errors.append("SQL AST中未找到只读查询")
            else:
                report.passed.append("SQL AST语法与方言校验通过")
        except sqlglot.errors.ParseError as exc:
            report.errors.append(f"SQL语法解析失败：{exc.errors[0].get('description', '未知错误')}")
        if not normalized.startswith(("SELECT ", "WITH ")):
            report.errors.append("仅允许SELECT或WITH查询")
        forbidden = re.findall(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|PRAGMA)\b", normalized)
        if forbidden:
            report.errors.append(f"检测到禁止的SQL操作：{', '.join(sorted(set(forbidden)))}")
        if ";" in sql.rstrip(";\n ") and "禁止执行多条SQL语句" not in report.errors:
            report.errors.append("禁止执行多条SQL语句")
        if not report.errors:
            report.passed.append("SQL仅包含只读查询")
        if all(edge.verified for edge in joins):
            report.passed.append("JOIN路径均来自已验证关系")
        if any(edge.cardinality.endswith(":N") for edge in joins):
            report.warnings.append("查询包含一对多关系，需要检查聚合膨胀")
        else:
            report.passed.append("未发现一对多JOIN膨胀风险")
        known_tables = set(SCHEMA)
        referenced = set(re.findall(r"(?:FROM|JOIN)\s+([a-zA-Z_]\w*)", sql, re.IGNORECASE))
        unknown = referenced - known_tables - {"base"}
        if unknown:
            report.errors.append(f"引用了未知表：{', '.join(sorted(unknown))}")
        else:
            report.passed.append("引用的表均存在于受控Schema")
        return report

    def _trust(self, plan: QueryPlan, validation: ValidationReport, joins: list[JoinEdge]) -> TrustReport:
        score = 1.0
        risks = [*plan.ambiguities, *validation.warnings]
        if plan.metric is None:
            score -= 0.5
        if plan.ambiguities:
            score -= 0.18 * len(plan.ambiguities)
        if validation.errors:
            score -= 0.5
        if any(not edge.verified for edge in joins):
            score -= 0.2
        score = max(0.0, min(1.0, score))
        if score >= 0.9:
            level, action = "A", "auto_execute"
        elif score >= 0.75:
            level, action = "B", "confirm"
        elif score >= 0.5:
            level, action = "C", "review"
        else:
            level, action = "D", "reject"
        return TrustReport(score, level, action, validation.passed, risks + validation.errors)

    def run(self, question: str, confirmed: bool = False, event_sink: EventSink | None = None) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        def emit(name: str, payload: dict[str, Any]) -> None:
            event = {"event": name, "data": payload}
            events.append(event)
            if event_sink:
                event_sink(name, payload)

        started = time.perf_counter()
        query_id = str(uuid.uuid4())
        plan = self.plan(question)
        emit("query_understood", {"plan": plan.public_dict()})
        tables = self._required_tables(plan)
        emit("schema_retrieved", {"tables": sorted(tables), "strategy": "certified semantic catalog"})
        joins = self._join_plan(tables)
        emit("join_path_selected", {"joins": [asdict(edge) for edge in joins]})
        sql, params = self.compile_sql(plan, joins)
        emit("sql_generated", {"sql": sql})
        validation = self.validate(sql, joins)
        trust = self._trust(plan, validation, joins)
        emit("sql_validated", {"validation": asdict(validation), "trust": asdict(trust)})
        if validation.errors or trust.action == "reject":
            raise QueryRejected("；".join(validation.errors or trust.risks))
        if trust.action in {"confirm", "review"} and not confirmed:
            return self._response(query_id, plan, joins, sql, params, validation, trust, [], events, started, "confirmation_required")
        emit("query_executing", {"read_only": True})
        with connect(read_only=True) as db:
            rows = [dict(row) for row in db.execute(sql, params).fetchall()]
        emit("completed", {"row_count": len(rows)})
        return self._response(query_id, plan, joins, sql, params, validation, trust, rows, events, started, "completed")

    def execute_plan(self, plan: QueryPlan, event_sink: EventSink | None = None) -> dict[str, Any]:
        """Compile and execute an already confirmed business plan."""
        events: list[dict[str, Any]] = []

        def emit(name: str, payload: dict[str, Any]) -> None:
            event = {"event": name, "data": payload}
            events.append(event)
            if event_sink:
                event_sink(name, payload)

        started = time.perf_counter()
        query_id = str(uuid.uuid4())
        emit("plan_confirmed", {"plan": plan.public_dict()})
        tables = self._required_tables(plan)
        emit("schema_retrieved", {"tables": sorted(tables), "strategy": "certified semantic catalog"})
        joins = self._join_plan(tables)
        emit("join_path_selected", {"joins": [asdict(edge) for edge in joins]})
        sql, params = self.compile_sql(plan, joins)
        emit("sql_generated", {"sql": sql})
        validation = self.validate(sql, joins)
        trust = self._trust(plan, validation, joins)
        emit("sql_validated", {"validation": asdict(validation), "trust": asdict(trust)})
        if validation.errors or trust.action == "reject":
            raise QueryRejected("；".join(validation.errors or trust.risks))
        emit("query_executing", {"read_only": True})
        with connect(read_only=True) as db:
            rows = [dict(row) for row in db.execute(sql, params).fetchall()]
        emit("completed", {"row_count": len(rows)})
        return self._response(query_id, plan, joins, sql, params, validation, trust, rows, events, started, "completed")

    @staticmethod
    def _response(query_id: str, plan: QueryPlan, joins: list[JoinEdge], sql: str, params: list[Any], validation: ValidationReport, trust: TrustReport, rows: list[dict[str, Any]], events: list[dict[str, Any]], started: float, status: str) -> dict[str, Any]:
        return {
            "query_id": query_id,
            "status": status,
            "understanding": plan.public_dict(),
            "join_plan": [asdict(edge) for edge in joins],
            "sql": sql,
            "parameters": params,
            "validation": asdict(validation),
            "trust": asdict(trust),
            "evidence": {
                "data_source": "SQLPilot demo healthcare database",
                "metric": plan.metric.name if plan.metric else None,
                "metric_definition": plan.metric.description if plan.metric else None,
                "tables": sorted({plan.metric.source_table} | {d.source_table for d in plan.dimensions}) if plan.metric else [],
                "read_only": True,
            },
            "rows": rows,
            "events": events,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
