from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.core.config import Settings
from app.core.errors import PlannerError
from app.planning.models import QueryPlanV1
from app.text_to_sql.compiler import DeterministicQueryCompiler
from app.text_to_sql.capability_router import CapabilityRouter
from app.text_to_sql.generator import BailianSqlGenerator
from app.text_to_sql.insights import ResultInterpreter, build_chart_spec
from app.text_to_sql.presentation import build_result_schema
from app.text_to_sql.schema import PostgresSchemaRetriever
from app.text_to_sql.validator import PostgresSqlValidator


class PostgresTextToSqlEngine:
    def __init__(self, settings: Settings, schemas: PostgresSchemaRetriever | None = None) -> None:
        self.settings = settings
        self.schemas = schemas or PostgresSchemaRetriever(settings)
        self.generator = BailianSqlGenerator(settings)
        self.compiler = DeterministicQueryCompiler()
        self.capability_router = CapabilityRouter(self.compiler)
        self.validator = PostgresSqlValidator()
        self.interpreter = ResultInterpreter(settings)

    async def execute_plan(self, plan: QueryPlanV1, source_profile: dict | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        query_id = str(uuid.uuid4())
        context = await self.schemas.retrieve(plan, source_profile=source_profile)
        route = self.capability_router.decide(plan, context)
        if route.route not in {"deterministic", "model_fallback"}:
            error_codes = {
                "clarify": "QUERY_PLAN_INCOMPLETE",
                "reject": "QUERY_ROUTE_REJECTED",
                "resync_schema": "SCHEMA_RESYNC_REQUIRED",
            }
            raise PlannerError(
                error_codes[route.route], route.message, False,
                {**route.evidence(), "plan_preserved": True},
            )
        compiled = route.compiled
        generation_strategy = compiled.strategy if compiled else "bailian_sql_fallback"
        sql, correction, execution_repairs, validation_repairs, events = "", None, 0, 0, [
            {"event": "schema_retrieved", "data": {"tables": [t.name for t in context.tables], "strategy": context.strategy}},
            {"event": "capability_routed", "data": route.evidence()},
        ]
        while True:
            validation = None
            last_validation = None
            generation_attempts = 1 if compiled else 3
            for generation_round in range(generation_attempts):
                candidates = [compiled.sql] if compiled else await self.generator.generate_candidates(plan, context, correction)
                valid_candidates: list[tuple[int, int, str, Any]] = []
                round_errors: list[str] = []
                for candidate_index, candidate_sql in enumerate(candidates):
                    candidate_validation = self.validator.validate(candidate_sql, context, plan)
                    last_validation = candidate_validation
                    events.append({"event": "sql_candidate_validated", "data": {
                        "round": generation_round + 1,
                        "candidate": candidate_index + 1,
                        "passed": candidate_validation.valid,
                        "errors": candidate_validation.errors,
                        "warnings": candidate_validation.warnings,
                        "strategy": generation_strategy,
                    }})
                    if candidate_validation.valid:
                        valid_candidates.append((len(candidate_validation.warnings), candidate_index,
                                                 candidate_sql, candidate_validation))
                    else:
                        round_errors.extend(candidate_validation.errors)
                if valid_candidates:
                    _, selected_index, sql, validation = min(valid_candidates, key=lambda item: (item[0], item[1]))
                    events.append({"event": "sql_candidate_selected", "data": {
                        "round": generation_round + 1,
                        "candidate": selected_index + 1,
                        "candidate_count": len(candidates),
                        "selection": "fewest_validation_warnings_then_model_rank",
                    }})
                    break
                validation_repairs += 1
                correction = "；".join(dict.fromkeys(round_errors)) or "所有候选均未通过SQL安全与业务一致性校验"
            events.append({"event": "sql_validated", "data": {
                "passed": bool(validation and validation.valid),
                "errors": validation.errors if validation else [correction],
                "strategy": generation_strategy,
            }})
            if not validation or not validation.valid:
                code = "SQL_COMPILER_VALIDATION_FAILED" if compiled else "SQL_VALIDATION_FAILED"
                message = "确定性SQL编译结果未通过内部一致性校验" if compiled else "生成的SQL经过3轮修正仍未通过安全与业务校验"
                raise PlannerError(
                    code,
                    message,
                    False,
                    {
                        "validation_errors": (
                            validation.errors if validation else
                            last_validation.errors if last_validation else
                            ["未生成可校验的SQL"]
                        ),
                        "validation_repairs": validation_repairs,
                        "plan_preserved": True,
                    },
                )
            connection = await self.schemas.connect(source_profile)
            try:
                async with connection.transaction(readonly=True):
                    await connection.execute(f"SET LOCAL statement_timeout = '{self.settings.query_timeout_seconds}s'")
                    bounded_sql = self._bounded_sql(sql)
                    explain = await connection.fetchval("EXPLAIN (FORMAT JSON) " + bounded_sql)
                    cost = self._explain_cost(explain)
                    if (
                        cost["plan_rows"] > self.settings.query_max_estimated_rows
                        or cost["total_cost"] > self.settings.query_max_total_cost
                    ):
                        raise PlannerError(
                            "QUERY_COST_EXCEEDED",
                            "查询预计扫描数据量或执行成本过高，已阻止执行",
                            False,
                            {"estimated_rows": cost["plan_rows"], "total_cost": cost["total_cost"]},
                        )
                    records = await connection.fetch(bounded_sql)
                    truncated = len(records) > self.settings.query_max_rows
                    rows = [dict(record) for record in records[: self.settings.query_max_rows]]
                    sql = bounded_sql
                break
            except PlannerError:
                raise
            except Exception as exc:
                if compiled:
                    raise PlannerError(
                        "SQL_COMPILER_EXECUTION_FAILED",
                        f"确定性SQL执行失败：{type(exc).__name__}",
                        False,
                        {"plan_preserved": True, "strategy": generation_strategy},
                    ) from exc
                execution_repairs += 1
                events.append({"event": "execution_failed", "data": {"attempt": execution_repairs, "error_type": type(exc).__name__}})
                if execution_repairs > 2 or not self._repairable_execution_error(exc):
                    code = "SQL_EXECUTION_RETRY_EXHAUSTED" if execution_repairs > 2 else "SQL_EXECUTION_FAILED"
                    message = "查询已自动修正2次但仍无法安全执行，查询计划已保留" if execution_repairs > 2 else f"只读查询执行失败：{type(exc).__name__}"
                    raise PlannerError(code, message, False, {
                        "plan_preserved": True,
                        "attempts": execution_repairs - 1,
                        "suggested_actions": ["补充业务口径后生成新计划", "检查数据源Schema是否已同步", "稍后重新执行当前计划"],
                    }) from exc
                safe_error = " ".join(str(exc).split())[:600]
                correction = f"数据库试执行失败（{type(exc).__name__}）：{safe_error}。请修正SQL；不得改变已确认计划，修正后仍需通过全部校验。"
            finally:
                await connection.close()
        serialized_rows = json.loads(json.dumps(rows, ensure_ascii=False, default=str))
        result_warnings = self._result_warnings(plan, serialized_rows)
        events.append({"event": "result_plausibility_checked", "data": {"warnings": result_warnings}})
        result_schema = build_result_schema(serialized_rows)
        visualization = build_chart_spec(serialized_rows, result_schema)
        insight = await self.interpreter.interpret(
            plan,
            serialized_rows,
            result_schema,
            visualization,
            truncated=truncated,
        )
        return {
            "query_id": query_id,
            "status": "completed",
            "sql": sql,
            "parameters": [],
            "rows": serialized_rows,
            "truncated": truncated,
            "result_schema": result_schema,
            "visualization": visualization,
            "insight": insight,
            "validation": {"passed": validation.passed, "errors": validation.errors,
                           "warnings": validation.warnings + result_warnings},
            "trust": self._trust_result(plan, context, validation, execution_repairs, validation_repairs),
            "join_plan": [item.__dict__ for item in context.relationships],
            "evidence": {
                "data_source": f"PostgreSQL/{(source_profile or {}).get('database', self.settings.sqlpilot_db_name)}",
                "data_source_id": plan.data_source_id,
                "schema_strategy": context.strategy,
                "sql_generation_strategy": generation_strategy,
                "capability_route": route.evidence(),
                "tables": [table.name for table in context.tables],
                "read_only": True,
                "explain_available": explain is not None,
                "estimated_rows": cost["plan_rows"],
                "total_cost": cost["total_cost"],
            },
            "events": events + [
                {"event": "sql_generated", "data": {
                    "model": self.settings.sqlpilot_bailian_model if not compiled else None,
                    "strategy": generation_strategy,
                    "validation_repairs": validation_repairs,
                    "execution_repairs": execution_repairs,
                }},
                {"event": "completed", "data": {"row_count": len(rows)}},
            ],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def _bounded_sql(self, sql: str) -> str:
        clean = sql.strip().rstrip(";")
        return f"SELECT * FROM (\n{clean}\n) AS sqlpilot_bounded\nLIMIT {self.settings.query_max_rows + 1}"

    @staticmethod
    def _explain_cost(explain: Any) -> dict[str, float]:
        payload = json.loads(explain) if isinstance(explain, str) else explain
        root = payload[0]["Plan"] if isinstance(payload, list) else payload["Plan"]
        return {
            "plan_rows": float(root.get("Plan Rows", 0)),
            "total_cost": float(root.get("Total Cost", 0)),
        }

    @staticmethod
    def _repairable_execution_error(exc: Exception) -> bool:
        name = type(exc).__name__
        return name not in {"InvalidPasswordError", "InsufficientPrivilegeError", "ConnectionDoesNotExistError", "ConnectionRefusedError"}

    @staticmethod
    def _result_warnings(plan: QueryPlanV1, rows: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        if not rows:
            warnings.append("查询返回空结果，建议检查过滤值绑定、大小写和时间范围")
            return warnings
        if len(rows) == 1 and (len(plan.dimensions) > 1 or "month" in plan.dimensions):
            warnings.append("计划要求多维或按月结果，但查询只返回一行")
        columns = set(rows[0])
        missing = [item for item in plan.semantics.output_fields if item not in columns]
        if plan.semantics.confidence >= .75 and missing:
            warnings.append("结果缺少语义计划输出字段：" + "、".join(missing))
        return warnings

    @staticmethod
    def _trust_result(
        plan: QueryPlanV1, context, validation, execution_repairs: int,
        validation_repairs: int = 0,
    ) -> dict[str, Any]:
        score = 1.0
        risks: list[str] = []
        evidence_scores = [item.score for item in plan.schema_evidence]
        if evidence_scores and max(evidence_scores) < 0.55:
            score -= 0.18
            risks.append("Schema语义召回置信度偏低")
        if any(item.requires_confirmation for item in plan.schema_evidence):
            bound_keys = {item.object_key for item in plan.semantic_bindings}
            ambiguous_keys = {item.object_key for item in plan.schema_evidence if item.requires_confirmation}
            if not bound_keys.intersection(ambiguous_keys):
                score -= 0.25
                risks.append("存在未由语义绑定消解的相近字段")
        if len(context.tables) > 1 and not context.relationships:
            score -= 0.2
            risks.append("涉及多表但没有验证关系")
        if execution_repairs:
            score -= min(0.2, execution_repairs * 0.08)
            risks.append(f"SQL执行阶段自动修正{execution_repairs}次")
        if validation_repairs:
            score -= min(0.12, validation_repairs * 0.04)
            risks.append(f"SQL生成阶段通过校验自动修正{validation_repairs}次")
        score = round(max(0.0, score), 2)
        level = "A" if score >= 0.9 else "B" if score >= 0.75 else "C" if score >= 0.55 else "D"
        action = "auto_execute" if level == "A" else "review" if level in {"B", "C"} else "reject"
        return {"score": score, "level": level, "action": action, "evidence": validation.passed, "risks": risks}
