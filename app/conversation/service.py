from __future__ import annotations

import asyncio
import inspect
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.conversation.models import ConversationStatus, QueryExecutionRecord
from app.conversation.repository import ConversationRepository
from app.core.errors import ConflictError
from app.engine import TrustworthyQueryEngine
from app.planning.base import QueryPlanner
from app.planning.legacy_adapter import to_legacy_plan
from app.planning.models import DateRange, QueryPlanV1
from app.planning.summarizer import conversation_reply, summarize_plan
from app.text_to_sql.engine import PostgresTextToSqlEngine
from app.data_sources import DataSourceService
from app.planning.models import Clarification, ClarificationOption, SchemaEvidence
from app.semantic_layer import SemanticLayerService
from app.schema_linking import link_fields
from app.memory import MemoryService
from app.context_learning import ContextLearningService


class ConversationService:
    def __init__(self, repository: ConversationRepository, planner: QueryPlanner, engine: TrustworthyQueryEngine, data_sources: DataSourceService | None = None, semantic_layer: SemanticLayerService | None = None, memory: MemoryService | None = None, context_learning: ContextLearningService | None = None) -> None:
        self.repository = repository
        self.planner = planner
        self.engine = engine
        self.data_sources = data_sources
        self.semantic_layer = semantic_layer
        self.memory = memory
        self.context_learning = context_learning

    async def create(self, tenant_id: str, user_id: str, title: str | None = None) -> dict[str, Any]:
        item = await self.repository.create(tenant_id, user_id, title or "新建数据分析")
        return self._conversation_dict(item)

    async def list(self, tenant_id: str, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.repository.list(tenant_id, user_id, limit)
        result = []
        for item in rows:
            value = self._conversation_dict(item)
            if value["title"] == "新建数据分析":
                messages = await self.repository.messages(item.id)
                first_user = next((message.content for message in messages if message.role == "user"), "")
                if first_user:
                    value["title"] = " ".join(first_user.split())[:60]
            result.append(value)
        return result

    async def send_message(self, conversation_id: str, content: str, base_plan_version: int | None, tenant_id: str, user_id: str, data_source_id: str | None = None) -> dict[str, Any]:
        conversation = await self.repository.get(conversation_id, tenant_id, user_id)
        latest = await self.repository.latest_plan(conversation_id)
        if latest and base_plan_version is not None and latest[0].version != base_plan_version:
            raise ConflictError("查询计划已被更新，请基于最新版本继续对话")
        await self.repository.add_message(conversation_id, "user", content)
        conversation_messages = await self.repository.messages(conversation_id)
        cumulative_question = "；".join(
            item.content.strip() for item in conversation_messages
            if item.role == "user" and item.content.strip()
        )
        schema_context: list[dict[str, Any]] = []
        selected_source = None
        if self.data_sources:
            inherited_source_id = latest[1].data_source_id if latest else None
            selected_source = await self.data_sources.ready_source(tenant_id, data_source_id or inherited_source_id)
            matches = await self.data_sources.search(
                tenant_id, selected_source["id"], content, limit=30
            )
            schema_context = [
                {
                    "object_type": item.get("object_type"),
                    "object_key": item.get("object_key"),
                    "business_name": item.get("business_name", ""),
                    "content": item.get("content", "")[:800],
                    "schema_name": item.get("schema_name", ""),
                    "table_name": item.get("table_name", ""),
                    "column_name": item.get("column_name"),
                    "score": item.get("score", 0),
                    "requires_confirmation": item.get("requires_confirmation", False),
                    "metadata": item.get("metadata", {}),
                }
                for item in matches[:24]
            ]
            if self.semantic_layer:
                certified_documents = await self.semantic_layer.retrieval_documents(
                    tenant_id, selected_source["id"]
                )
                existing = {item["object_key"] for item in schema_context}
                schema_context = certified_documents + [
                    item for item in schema_context if item["object_key"] not in existing.intersection(
                        {document["object_key"] for document in certified_documents}
                    )
                ]
        memory_context = await self.memory.context(
            tenant_id, user_id, selected_source["id"] if selected_source else None
        ) if self.memory else {}
        reused_path_id = None
        if selected_source and self.context_learning:
            verified_paths = await self.context_learning.context(
                tenant_id, selected_source["id"], cumulative_question,
                selected_source.get("schema_fingerprint", ""),
            )
            memory_context["verified_query_paths"] = verified_paths
            exact = await self.context_learning.find_exact_plan(
                tenant_id, selected_source["id"], cumulative_question,
                selected_source.get("schema_fingerprint", ""),
            )
            if exact:
                plan, reused_path_id = exact
        if latest and latest[1].intent != "unsupported" and not reused_path_id:
            parameters = inspect.signature(self.planner.revise_plan).parameters
            kwargs = {}
            if "schema_context" in parameters:
                kwargs["schema_context"] = schema_context
            if "memory_context" in parameters:
                kwargs["memory_context"] = memory_context
            plan = await self.planner.revise_plan(latest[1], content, **kwargs)
        elif not reused_path_id:
            parameters = inspect.signature(self.planner.create_plan).parameters
            kwargs = {}
            if "schema_context" in parameters:
                kwargs["schema_context"] = schema_context
            if "memory_context" in parameters:
                kwargs["memory_context"] = memory_context
            plan = await self.planner.create_plan(content, **kwargs)
        if plan.intent == "unsupported":
            # Keep a version for history/concurrency, but never carry a stale
            # executable plan into an unrelated conversation turn.
            plan = QueryPlanV1(
                intent="unsupported",
                date_range=DateRange(type="all"),
                data_source_id=selected_source["id"] if selected_source else None,
                provenance=plan.provenance,
            )
            message = "这个问题不属于已连接数据库的数据查询，我不会生成或执行 SQL。你可以问我想分析哪些数据、时间范围和统计口径。"
            record = await self.repository.save_plan(
                conversation_id, plan, ConversationStatus.UNSUPPORTED.value
            )
            await self.repository.add_message(conversation_id, "assistant", message, "unsupported")
            return self._plan_response(
                conversation_id, record.version, record.plan_hash,
                ConversationStatus.UNSUPPORTED.value, plan, message,
            )
        if selected_source:
            plan.data_source_id = selected_source["id"]
            plan.default_policies = list(selected_source.get("business_rules", []))
            if self.semantic_layer:
                await self.semantic_layer.apply_certified(tenant_id, plan)
            self._normalize_explicit_time_binding(plan)
            self._align_semantics_to_certified_bindings(plan)
            self._link_filter_values(plan, schema_context)
            self._remove_redundant_year_filter(plan)
            plan.schema_evidence = [
                SchemaEvidence(
                    object_key=item["object_key"],
                    business_name=item.get("business_name", ""),
                    score=float(item.get("score", 0)),
                    requires_confirmation=bool(item.get("requires_confirmation", False)),
                )
                for item in schema_context
            ]
            plan.field_candidates = link_fields(content, schema_context, plan)
            ambiguous = [item for item in schema_context[:8] if item.get("requires_confirmation")]
            bound_keys = {item.object_key for item in plan.semantic_bindings}
            if ambiguous and not bound_keys.intersection({item["object_key"] for item in ambiguous}):
                plan.clarifications = [item for item in plan.clarifications if item.id != "field_binding"]
                plan.clarifications.append(
                    Clarification(
                        id="field_binding",
                        question="检索到多个含义接近的数据字段，请确认本次查询采用哪个业务口径？",
                        reason="候选字段语义得分接近，直接选择可能导致统计口径错误。",
                        options=[
                            ClarificationOption(
                                value=item["object_key"],
                                label=(item.get("business_name") or item["object_key"]),
                                description=item.get("content", "")[:240],
                            )
                            for item in ambiguous[:5]
                        ],
                    )
                )
            invalid_bindings = await self._invalid_schema_bindings(
                tenant_id, selected_source["id"], plan
            )
            missing_bindings = self._missing_semantic_bindings(plan)
            binding_issues = invalid_bindings + missing_bindings
            if binding_issues:
                failed = {
                    item.object_key: item for item in plan.semantic_bindings
                    if item.object_key in invalid_bindings
                }
                targeted_matches: list[dict[str, Any]] = []
                for binding in failed.values():
                    search_text = self._binding_correction_query(plan, binding)
                    targeted_matches.extend(await self.data_sources.search(
                        tenant_id,
                        selected_source["id"],
                        search_text,
                        limit=12,
                    ))
                for requirement in missing_bindings:
                    targeted_matches.extend(await self.data_sources.search(
                        tenant_id,
                        selected_source["id"],
                        self._missing_binding_query(requirement),
                        limit=12,
                    ))
                if any(item in missing_bindings for item in ("missing:dimension:month", "missing:time:date_range")):
                    table_keys = list(dict.fromkeys(
                        (item.schema_name, item.table_name)
                        for item in plan.semantic_bindings
                        if item.role in {"metric", "filter"}
                    ))
                    for schema_name, table_name in table_keys[:3]:
                        try:
                            detail = await self.data_sources.table_detail(
                                tenant_id, selected_source["id"], schema_name, table_name
                            )
                        except Exception:
                            continue
                        time_columns = sorted(
                            detail.get("columns", []),
                            key=self._time_column_score,
                            reverse=True,
                        )
                        for column in time_columns[:8]:
                            if self._time_column_score(column) <= 0:
                                continue
                            column_name = column.get("column_name", "")
                            targeted_matches.append({
                                "object_type": "column",
                                "object_key": f"{schema_name}.{table_name}.{column_name}",
                                "business_name": column.get("display_name") or column.get("database_comment") or column_name,
                                "content": "；".join(filter(None, [
                                    column.get("database_comment", ""),
                                    column.get("description", ""),
                                    f"数据类型：{column.get('data_type', '')}",
                                ]))[:800],
                                "schema_name": schema_name,
                                "table_name": table_name,
                                "column_name": column_name,
                                "score": 1.0,
                                "requires_confirmation": False,
                            })
                seen = {item["object_key"] for item in schema_context}
                correction_context = list(schema_context)
                for item in targeted_matches:
                    if item["object_key"] in seen:
                        continue
                    seen.add(item["object_key"])
                    correction_context.append({
                        "object_type": item.get("object_type"),
                        "object_key": item.get("object_key"),
                        "business_name": item.get("business_name", ""),
                        "content": item.get("content", "")[:800],
                        "schema_name": item.get("schema_name", ""),
                        "table_name": item.get("table_name", ""),
                        "column_name": item.get("column_name"),
                        "score": item.get("score", 0),
                        "requires_confirmation": item.get("requires_confirmation", False),
                        "metadata": item.get("metadata", {}),
                    })
                parameters = inspect.signature(self.planner.revise_plan).parameters
                correction_message = (
                    "系统校验发现以下字段不存在，或字段语义不能满足当前查询："
                    + "、".join(binding_issues)
                    + "。请根据新的Schema候选只修正错误的semantic_bindings及其对应维度或过滤字段，"
                    "不得猜测候选之外的字段，不得改变用户的指标、时间、比较和其他需求。"
                )
                plan = await self.planner.revise_plan(
                    plan, correction_message, schema_context=correction_context
                ) if "schema_context" in parameters else await self.planner.revise_plan(plan, correction_message)
                plan.data_source_id = selected_source["id"]
                plan.default_policies = list(selected_source.get("business_rules", []))
                self._normalize_explicit_time_binding(plan)
                self._align_semantics_to_certified_bindings(plan)
                self._link_filter_values(plan, correction_context)
                self._remove_redundant_year_filter(plan)
                plan.schema_evidence = [
                    SchemaEvidence(
                        object_key=item["object_key"],
                        business_name=item.get("business_name", ""),
                        score=float(item.get("score", 0)),
                        requires_confirmation=bool(item.get("requires_confirmation", False)),
                    )
                    for item in correction_context
                ]
                plan.field_candidates = link_fields(content, correction_context, plan)
                invalid_bindings = await self._invalid_schema_bindings(
                    tenant_id, selected_source["id"], plan
                )
                missing_bindings = self._missing_semantic_bindings(plan)
                binding_issues = invalid_bindings + missing_bindings
            if binding_issues:
                plan.clarifications = [
                    item for item in plan.clarifications if item.id != "schema_binding_invalid"
                ]
                plan.clarifications.append(
                    Clarification(
                        id="schema_binding_invalid",
                        question="模型选择的部分业务字段在当前数据源中不存在，请重新选择或先同步Schema。",
                        reason="以下绑定未通过Schema存在性、语义或完整性验证：" + "、".join(binding_issues),
                        options=[],
                    )
                )
        status = ConversationStatus.CLARIFYING.value if plan.needs_clarification else ConversationStatus.AWAITING_CONFIRMATION.value
        record = await self.repository.save_plan(conversation_id, plan, status)
        if self.memory:
            await self.memory.save_conversation_summary(conversation_id, record.version, plan)
        assistant_message = conversation_reply(plan, is_revision=latest is not None)
        if reused_path_id:
            assistant_message = (
                "已匹配并复用经过审核的认证查询路径，指标口径、字段绑定和查询关系均沿用已确认版本；"
                "系统仍会按当前Schema重新校验并生成只读 SQL。" + assistant_message
            )
        await self.repository.add_message(
            conversation_id,
            "assistant",
            assistant_message,
            "clarification" if plan.needs_clarification else "plan_summary",
        )
        response = self._plan_response(conversation_id, record.version, record.plan_hash, status, plan, assistant_message)
        response["knowledge_reuse"] = {
            "query_path_id": reused_path_id,
            "type": "certified_query_path",
            "label": "已复用认证查询路径",
        } if reused_path_id else None
        return response

    async def confirm(self, conversation_id: str, version: int, plan_hash: str, tenant_id: str, user_id: str) -> dict[str, Any]:
        await self.repository.get(conversation_id, tenant_id, user_id)
        record = await self.repository.confirm(conversation_id, version, plan_hash)
        latest = await self.repository.latest_plan(conversation_id)
        if self.semantic_layer and latest:
            await self.semantic_layer.observe_confirmation(tenant_id, latest[1])
        return {"conversation_id": conversation_id, "status": "confirmed", "plan_version": record.version, "plan_hash": record.plan_hash}

    async def execute(self, conversation_id: str, version: int, tenant_id: str, user_id: str) -> dict[str, Any]:
        conversation = await self.repository.get(conversation_id, tenant_id, user_id)
        latest = await self.repository.latest_plan(conversation_id)
        if not latest or latest[0].version != version or latest[0].status != "confirmed":
            raise ConflictError("只能执行已经确认的最新查询计划")
        plan = latest[1]
        execution = QueryExecutionRecord(
            conversation_id=conversation_id,
            plan_version=version,
            status="executing",
        )
        try:
            if isinstance(self.engine, PostgresTextToSqlEngine):
                source_profile = await self.data_sources.connection_profile(tenant_id, plan.data_source_id) if self.data_sources and plan.data_source_id else None
                result = await self.engine.execute_plan(plan, source_profile=source_profile)
            else:
                legacy = to_legacy_plan(plan)
                result = await asyncio.to_thread(self.engine.execute_plan, legacy)
            execution.status = "completed"
            execution.sql_text = result["sql"]
            # Persist the complete presentation snapshot, not only the raw rows.
            # This lets history restore the exact Chinese columns, chart, insight,
            # validation evidence and trust assessment shown after execution.
            execution.result_json = json.dumps(result, ensure_ascii=False, default=str)
            execution.completed_at = datetime.now(timezone.utc)
            await self.repository.save_execution(execution)
            return {"conversation_id": conversation_id, "plan_version": version,
                    "execution_id": execution.id, **result}
        except Exception as exc:
            execution.status = "failed"
            execution.error_code = getattr(exc, "code", type(exc).__name__)
            execution.completed_at = datetime.now(timezone.utc)
            await self.repository.save_execution(execution)
            raise

    async def detail(self, conversation_id: str, tenant_id: str, user_id: str) -> dict[str, Any]:
        conversation = await self.repository.get(conversation_id, tenant_id, user_id)
        messages = await self.repository.messages(conversation_id)
        executions = await self.repository.executions(conversation_id)
        latest = await self.repository.latest_plan(conversation_id)
        result = self._conversation_dict(conversation)
        result["messages"] = [
            {"id": item.id, "role": item.role, "content": item.content, "type": item.message_type, "created_at": item.created_at.isoformat()}
            for item in messages
        ]
        result["executions"] = [self._execution_response(item) for item in executions]
        if latest:
            result["current_plan"] = self._plan_response(
                conversation_id, latest[0].version, latest[0].plan_hash, latest[0].status, latest[1], summarize_plan(latest[1])
            )
        return result

    @staticmethod
    def _execution_response(item: QueryExecutionRecord) -> dict[str, Any]:
        stored = json.loads(item.result_json) if item.result_json else {}
        # Records created before full snapshots were introduced contain only a
        # list of rows. Keep them readable without a data migration.
        snapshot = {"rows": stored, "sql": item.sql_text, "truncated": False} if isinstance(stored, list) else stored
        snapshot.setdefault("rows", [])
        snapshot.setdefault("sql", item.sql_text or "")
        snapshot.setdefault("truncated", False)
        return {
            "id": item.id,
            "plan_version": item.plan_version,
            "status": item.status,
            "sql": snapshot["sql"],
            "rows": snapshot["rows"],
            "result": snapshot,
            "error_code": item.error_code,
            "created_at": item.created_at.isoformat(),
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        }

    async def _invalid_schema_bindings(
        self, tenant_id: str, source_id: str, plan: QueryPlanV1
    ) -> list[str]:
        if not self.data_sources:
            return []
        catalog: dict[tuple[str, str], set[str] | None] = {}
        invalid: list[str] = []
        for binding in plan.semantic_bindings:
            key = (binding.schema_name, binding.table_name)
            if key not in catalog:
                try:
                    detail = await self.data_sources.table_detail(
                        tenant_id, source_id, binding.schema_name, binding.table_name
                    )
                    catalog[key] = {item["column_name"] for item in detail["columns"]}
                except Exception:
                    catalog[key] = None
            columns = catalog[key]
            if (
                columns is None
                or binding.column_name not in columns
                or self._binding_semantically_incompatible(plan, binding)
            ):
                invalid.append(binding.object_key)
        return invalid

    @staticmethod
    def _binding_semantically_incompatible(plan: QueryPlanV1, binding) -> bool:
        key = binding.key.lower()
        column = binding.column_name.lower()
        if binding.role == "dimension" and key in {"day", "week", "month", "quarter"} and column in {"year", "yyyy", "fiscal_year"}:
            return True
        if binding.role == "time" and column in {"year", "yyyy", "fiscal_year"}:
            date_range = plan.date_range
            if date_range.start and date_range.end and (
                date_range.start.month != 1
                or date_range.start.day != 1
                or date_range.end.month != 12
                or date_range.end.day != 31
            ):
                return True
        if binding.role == "filter" and column in {"insutype", "insurance_type"}:
            for item in plan.filters:
                if item.field in {binding.key, binding.column_name, binding.object_key}:
                    if "住院" in item.display_value:
                        return True
        return False

    @staticmethod
    def _binding_correction_query(plan: QueryPlanV1, binding) -> str:
        if binding.role == "dimension" and binding.key.lower() in {"day", "week", "month", "quarter", "year"}:
            labels = {"day": "日期", "week": "周", "month": "月份", "quarter": "季度", "year": "年度"}
            return f"{labels[binding.key.lower()]} 日期 时间 结算时间 按{labels[binding.key.lower()]}统计"
        if binding.role == "time" and binding.column_name.lower() in {"year", "yyyy", "fiscal_year"}:
            return "日期 时间 结算时间 精确时间范围"
        if binding.role == "filter" and binding.column_name.lower() in {"insutype", "insurance_type"}:
            if any("住院" in item.display_value for item in plan.filters):
                return "住院 就医类别 医疗类别 结算类别"
        return f"{binding.label} {binding.key}"

    @staticmethod
    def _missing_semantic_bindings(plan: QueryPlanV1) -> list[str]:
        missing: list[str] = []
        metric_keys = {item.key for item in plan.semantic_bindings if item.role == "metric"}
        dimension_keys = {item.key for item in plan.semantic_bindings if item.role == "dimension"}
        filter_keys = {
            value
            for item in plan.semantic_bindings if item.role == "filter"
            for value in (item.key, item.column_name, item.object_key)
        }
        for metric in plan.metrics:
            if metric not in metric_keys:
                missing.append(f"missing:metric:{metric}")
        for dimension in plan.dimensions:
            derived_from_time = dimension in {"day", "week", "month", "quarter", "year"} and any(
                item.role == "time"
                and item.column_name.lower() not in {"year", "yyyy", "fiscal_year"}
                and any(token in item.column_name.lower() for token in ("date", "time", "month"))
                for item in plan.semantic_bindings
            )
            if dimension not in dimension_keys and not derived_from_time:
                missing.append(f"missing:dimension:{dimension}")
        for query_filter in plan.filters:
            if query_filter.field not in filter_keys and query_filter.field.rsplit(".", 1)[-1] not in filter_keys:
                missing.append(f"missing:filter:{query_filter.field}")
        if plan.date_range.start and plan.date_range.end:
            time_bindings = [item for item in plan.semantic_bindings if item.role == "time"]
            time_like_dimensions = [
                item for item in plan.semantic_bindings
                if item.role == "dimension"
                and any(token in item.column_name.lower() for token in ("date", "time", "month"))
            ]
            date_filter_fields = {
                query_filter.field for query_filter in plan.filters
                if query_filter.operator in {"between", "gte", "lte"}
            }
            time_like_filters = [
                item for item in plan.semantic_bindings
                if item.role == "filter"
                and item.object_key in date_filter_fields
                and item.column_name.lower() not in {"year", "yyyy", "fiscal_year"}
                and any(token in item.column_name.lower() for token in ("date", "time", "month"))
            ]
            if not time_bindings and not time_like_dimensions and not time_like_filters:
                missing.append("missing:time:date_range")
        return list(dict.fromkeys(missing))

    @staticmethod
    def _normalize_explicit_time_binding(plan: QueryPlanV1) -> None:
        """date_range已完整表达值时，将模型的time_range过滤绑定规范化为时间角色。"""
        if not (plan.date_range.start and plan.date_range.end):
            return
        normalized = False
        for binding in plan.semantic_bindings:
            name = binding.column_name.lower()
            if (
                binding.role == "filter"
                and binding.key in {"time", "time_range", "date_range", "stat_time"}
                and name not in {"year", "yyyy", "fiscal_year"}
                and any(token in name for token in ("date", "time", "month"))
            ):
                binding.role = "time"
                normalized = True
        if normalized:
            plan.clarifications = [
                item for item in plan.clarifications
                if item.id not in {"filter_value:time_range", "filter_value:date_range", "filter_value:time"}
            ]

    @staticmethod
    def _align_semantics_to_certified_bindings(plan: QueryPlanV1) -> None:
        """认证绑定覆盖模型字段后，同步重建给编译器和验证器使用的语义IR。"""
        metrics = {
            item.key: item for item in plan.semantic_bindings
            if item.role == "metric" and item.key in plan.metrics and item.certified
        }
        dimensions = {
            item.key: item for item in plan.semantic_bindings
            if item.role == "dimension" and item.key in plan.dimensions and item.certified
        }
        if len(metrics) != len(plan.metrics) or len(dimensions) != len(plan.dimensions):
            return
        output_expressions: list[dict[str, Any]] = []
        for key in plan.dimensions:
            binding = dimensions[key]
            output_expressions.append({
                "field": binding.object_key, "alias": key, "expression": binding.object_key,
            })
        aggregations: list[dict[str, Any]] = []
        for key in plan.metrics:
            binding = metrics[key]
            function = binding.aggregation
            expression = binding.object_key if function == "none" else f"{function.upper()}({binding.object_key})"
            output_expressions.append({
                "field": binding.object_key, "alias": key, "expression": expression,
            })
            if plan.comparison.type != "none":
                comparison_suffix = "yoy_rate" if plan.comparison.type == "year_over_year" else "mom_rate"
                output_expressions.extend([
                    {
                        "field": binding.object_key,
                        "alias": f"prev_{key}",
                        "expression": f"PREVIOUS_PERIOD({expression})",
                    },
                    {
                        "field": binding.object_key,
                        "alias": f"{key}_{comparison_suffix}",
                        "expression": f"GROWTH_RATE({key}, prev_{key})",
                    },
                ])
            if function != "none":
                aggregations.append({
                    "function": function, "object": binding.object_key,
                    "is_distinct": function == "count_distinct",
                })
        plan.semantics.output_fields = [item["alias"] for item in output_expressions]
        plan.semantics.output_expressions = output_expressions
        plan.semantics.aggregations = aggregations
        plan.semantics.group_by = [dimensions[key].object_key for key in plan.dimensions]
        explicit_ranking = bool(
            plan.ranking.scope or plan.ranking.limit or plan.ranking.metric != "metric_value"
        )
        if not explicit_ranking:
            plan.semantics.ordering = []

    @staticmethod
    def _missing_binding_query(requirement: str) -> str:
        if requirement == "missing:dimension:month":
            return "月份 日期 时间 结算时间 按月统计"
        if requirement == "missing:time:date_range":
            return "日期 时间 结算时间 统计时间范围"
        if requirement.startswith("missing:filter:"):
            return requirement.rsplit(":", 1)[-1] + " 过滤条件 业务代码"
        return requirement.rsplit(":", 1)[-1] + " 指标 字段"

    @staticmethod
    def _time_column_score(column: dict[str, Any]) -> int:
        name = str(column.get("column_name", "")).lower()
        description = " ".join(str(column.get(key, "")) for key in (
            "database_comment", "display_name", "description", "data_type"
        )).lower()
        text = f"{name} {description}"
        score = 0
        if any(token in text for token in ("time", "date", "timestamp", "日期", "时间", "月份")):
            score += 4
        if any(token in text for token in ("setl", "结算")):
            score += 8
        if any(token in text for token in ("brdy", "birth", "出生")):
            score -= 20
        if name in {"year", "yyyy", "fiscal_year"}:
            score -= 20
        return score

    @staticmethod
    def _link_filter_values(plan: QueryPlanV1, schema_context: list[dict[str, Any]]) -> None:
        """Resolve business labels to codes only when the catalog explicitly supplies the mapping."""
        evidence = {item.get("object_key"): item for item in schema_context}
        bindings = [item for item in plan.semantic_bindings if item.role == "filter"]
        for query_filter in plan.filters:
            binding = next((item for item in bindings if query_filter.field in {
                item.key, item.column_name, item.object_key,
            }), None)
            if not binding or "住院" not in query_filter.display_value:
                continue
            values = query_filter.value if isinstance(query_filter.value, list) else [query_filter.value]
            if values and all(re.fullmatch(r"[A-Za-z0-9_.-]+", str(value)) for value in values):
                continue
            content = " ".join(str(evidence.get(binding.object_key, {}).get(key, "")) for key in (
                "business_name", "content",
            ))
            match = re.search(r"所有住院类型(?:为|[:：])\s*([0-9][0-9、,，\s]*)", content)
            codes = list(dict.fromkeys(re.findall(r"\d+", match.group(1)))) if match else []
            if codes:
                query_filter.operator = "in"
                query_filter.value = codes
                query_filter.display_value = "住院（所有类型）"

    @staticmethod
    def _remove_redundant_year_filter(plan: QueryPlanV1) -> None:
        if not (plan.date_range.start and plan.date_range.end):
            return
        has_precise_time = any(
            item.role in {"time", "dimension"}
            and item.column_name.lower() not in {"year", "yyyy", "fiscal_year"}
            and any(token in item.column_name.lower() for token in ("date", "time", "month"))
            for item in plan.semantic_bindings
        )
        if not has_precise_time:
            return
        removed_fields = {
            item.field for item in plan.filters
            if item.field.rsplit(".", 1)[-1].lower() in {"year", "yyyy", "fiscal_year"}
        }
        if not removed_fields:
            return
        plan.filters = [item for item in plan.filters if item.field not in removed_fields]
        plan.semantic_bindings = [
            item for item in plan.semantic_bindings
            if not (
                item.role == "filter"
                and item.column_name.lower() in {"year", "yyyy", "fiscal_year"}
            )
        ]

    @staticmethod
    def _conversation_dict(item) -> dict[str, Any]:
        return {"id": item.id, "tenant_id": item.tenant_id, "user_id": item.user_id,
                "title": item.title, "status": item.status,
                "current_plan_version": item.current_plan_version,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat()}

    @staticmethod
    def _plan_response(conversation_id: str, version: int, plan_hash: str, status: str, plan: QueryPlanV1, message: str) -> dict[str, Any]:
        return {
            "conversation_id": conversation_id,
            "status": status,
            "assistant_message": message,
            "plan_version": version,
            "plan_hash": plan_hash,
            "plan": plan.model_dump(mode="json"),
            "summary": summarize_plan(plan),
        }
