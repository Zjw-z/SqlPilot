from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.conversation.models import DataSourceRecord, SemanticBindingObservationRecord, SemanticDefinitionRecord
from app.core.errors import NotFoundError, PlannerError
from app.planning.models import QueryPlanV1, SemanticBinding


class SemanticLayerService:
    KINDS = {"metric", "dimension", "value_set", "join", "business_rule", "golden_query"}
    STATUSES = {"draft", "certified", "disabled"}

    def __init__(self, sessions: async_sessionmaker) -> None:
        self.sessions = sessions

    async def list_definitions(self, tenant_id: str, source_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(SemanticDefinitionRecord).where(
                SemanticDefinitionRecord.tenant_id == tenant_id,
                SemanticDefinitionRecord.source_id == source_id,
            ).order_by(SemanticDefinitionRecord.kind, SemanticDefinitionRecord.semantic_key))).all()
        return [self._definition_dict(item) for item in rows]

    async def retrieval_documents(self, tenant_id: str, source_id: str) -> list[dict[str, Any]]:
        """将已认证业务口径作为高优先级Schema证据提供给规划器。"""
        definitions = await self.list_definitions(tenant_id, source_id)
        documents: list[dict[str, Any]] = []
        for item in definitions:
            if item["status"] != "certified" or item["kind"] not in {"metric", "dimension", "value_set"}:
                continue
            definition = item["definition"]
            binding = definition.get("binding", {})
            object_key = binding.get("object_key") or definition.get("field")
            if not object_key:
                continue
            values = definition.get("values", {})
            value_text = "、".join(
                f"{label}={','.join(value) if isinstance(value, list) else value}"
                for label, value in values.items()
            )
            documents.append({
                "object_type": f"semantic_{item['kind']}",
                "object_key": object_key,
                "business_name": item["label"],
                "content": "；".join(filter(None, [
                    f"已认证{item['kind']}：{item['label']}", definition.get("description", ""),
                    f"聚合方式：{binding.get('aggregation')}" if binding.get("aggregation") else "",
                    f"业务码值：{value_text}" if value_text else "",
                ])),
                "schema_name": binding.get("schema_name", object_key.split(".")[0]),
                "table_name": binding.get("table_name", object_key.split(".")[1] if object_key.count(".") >= 2 else ""),
                "column_name": binding.get("column_name", object_key.rsplit(".", 1)[-1]),
                "score": 1.0,
                "requires_confirmation": False,
                "metadata": {"semantic_key": item["semantic_key"], "certified": True,
                             "semantic_kind": item["kind"]},
            })
        return documents

    async def upsert_definition(self, tenant_id: str, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        kind, status = payload["kind"], payload["status"]
        if kind not in self.KINDS or status not in self.STATUSES:
            raise PlannerError("SEMANTIC_DEFINITION_INVALID", "语义定义类型或状态无效", False)
        self._validate_definition(payload)
        async with self.sessions.begin() as session:
            source = await session.get(DataSourceRecord, source_id)
            if source is None or source.tenant_id != tenant_id:
                raise NotFoundError("数据源")
            row = await session.scalar(select(SemanticDefinitionRecord).where(
                SemanticDefinitionRecord.tenant_id == tenant_id,
                SemanticDefinitionRecord.source_id == source_id,
                SemanticDefinitionRecord.kind == kind,
                SemanticDefinitionRecord.semantic_key == payload["semantic_key"],
            ))
            if row is None:
                row = SemanticDefinitionRecord(
                    tenant_id=tenant_id, source_id=source_id, kind=kind,
                    semantic_key=payload["semantic_key"], label=payload["label"],
                )
                session.add(row)
            else:
                row.version += 1
            row.label = payload["label"]
            row.definition_json = json.dumps(payload["definition"], ensure_ascii=False)
            row.status = status
        return self._definition_dict(row)

    async def apply_certified(self, tenant_id: str, plan: QueryPlanV1) -> list[str]:
        if not plan.data_source_id:
            return []
        async with self.sessions() as session:
            rows = (await session.scalars(select(SemanticDefinitionRecord).where(
                SemanticDefinitionRecord.tenant_id == tenant_id,
                SemanticDefinitionRecord.source_id == plan.data_source_id,
                SemanticDefinitionRecord.status == "certified",
            ))).all()
        applied = []
        by_key = {(item.kind, item.semantic_key): item for item in rows}
        for role, keys in (("metric", plan.metrics), ("dimension", plan.dimensions)):
            for key in keys:
                record = by_key.get((role, key))
                if record:
                    self._replace_binding(plan, SemanticBinding.model_validate(json.loads(record.definition_json)["binding"]))
                    applied.append(f"{role}:{key}")
        for query_filter in plan.filters:
            key = query_filter.field.rsplit(".", 1)[-1]
            record = by_key.get(("value_set", key))
            if not record:
                continue
            definition = json.loads(record.definition_json)
            mapping = definition.get("values", {})
            mapped = mapping.get(query_filter.display_value) or mapping.get(str(query_filter.value))
            if mapped is not None:
                query_filter.operator = "in" if isinstance(mapped, list) else "eq"
                query_filter.value = mapped
                applied.append(f"value_set:{key}")
        if applied:
            plan.assumptions = [item for item in plan.assumptions if not item.startswith("认证语义层：")]
            plan.assumptions.append("认证语义层：" + "、".join(applied))
        return applied

    async def observe_confirmation(self, tenant_id: str, plan: QueryPlanV1) -> None:
        if not plan.data_source_id:
            return
        now = datetime.now(timezone.utc)
        async with self.sessions.begin() as session:
            for binding in plan.semantic_bindings:
                row = await session.scalar(select(SemanticBindingObservationRecord).where(
                    SemanticBindingObservationRecord.tenant_id == tenant_id,
                    SemanticBindingObservationRecord.source_id == plan.data_source_id,
                    SemanticBindingObservationRecord.role == binding.role,
                    SemanticBindingObservationRecord.semantic_key == binding.key,
                    SemanticBindingObservationRecord.object_key == binding.object_key,
                ))
                if row:
                    row.confirmation_count += 1
                    row.last_confirmed_at = now
                    row.label = binding.label
                else:
                    session.add(SemanticBindingObservationRecord(
                        tenant_id=tenant_id, source_id=plan.data_source_id, role=binding.role,
                        semantic_key=binding.key, label=binding.label, object_key=binding.object_key,
                        last_confirmed_at=now,
                    ))

    async def observations(self, tenant_id: str, source_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(SemanticBindingObservationRecord).where(
                SemanticBindingObservationRecord.tenant_id == tenant_id,
                SemanticBindingObservationRecord.source_id == source_id,
            ).order_by(SemanticBindingObservationRecord.confirmation_count.desc()))).all()
        return [{
            "role": item.role, "semantic_key": item.semantic_key, "label": item.label,
            "object_key": item.object_key, "confirmation_count": item.confirmation_count,
            "last_confirmed_at": item.last_confirmed_at.isoformat(),
        } for item in rows]

    @staticmethod
    def compiler_capabilities() -> dict[str, Any]:
        return {
            "strategy": "deterministic_ir_v1",
            "router": {
                "routes": ["deterministic", "model_fallback", "clarify", "reject", "resync_schema"],
                "model_fallback_preconditions": [
                    "semantic_bindings_complete", "schema_objects_exist", "verified_join_path_if_multitable",
                ],
            },
            "supported": {
                "intents": ["aggregate_analysis"],
                "topologies": ["single_fact_table"],
                "aggregations": ["sum", "count", "count_distinct", "avg", "min", "max"],
                "dimensions": ["month", "certified_direct_dimension"],
                "comparisons": ["none", "year_over_year", "month_over_month"],
                "filters": ["eq", "ne", "in", "gte", "lte", "between", "contains"],
                "ranking": ["metric_value", "yoy_rate", "mom_rate", "top_n"],
            },
            "fallback": {
                "strategy": "bailian_sql_fallback",
                "cases": ["multi_table", "detail_query", "unsupported_expression"],
                "requires_validation": True,
            },
        }

    @staticmethod
    def _replace_binding(plan: QueryPlanV1, binding: SemanticBinding) -> None:
        plan.semantic_bindings = [
            item for item in plan.semantic_bindings
            if not (item.role == binding.role and item.key == binding.key)
        ] + [binding.model_copy(update={"certified": True, "confidence": 1.0})]

    @staticmethod
    def _validate_definition(payload: dict[str, Any]) -> None:
        kind, key, definition = payload["kind"], payload["semantic_key"], payload["definition"]
        try:
            if kind in {"metric", "dimension"}:
                binding = SemanticBinding.model_validate(definition["binding"])
                if binding.role != kind or binding.key != key:
                    raise ValueError("binding role or key mismatch")
            elif kind == "value_set":
                if not isinstance(definition.get("values"), dict) or not definition["values"]:
                    raise ValueError("value_set values required")
            elif kind == "join":
                required = {"source_table", "source_column", "target_table", "target_column", "cardinality"}
                if not required.issubset(definition):
                    raise ValueError("join definition incomplete")
                if definition["cardinality"] not in {"1:1", "1:N", "N:1", "N:N"}:
                    raise ValueError("join cardinality invalid")
            elif kind == "business_rule":
                required = {"rule_type", "field", "operator", "value"}
                if not required.issubset(definition):
                    raise ValueError("business rule definition incomplete")
                if definition["rule_type"] not in {"time_semantics", "record_scope", "deduplication"}:
                    raise ValueError("business rule type invalid")
            elif kind == "golden_query":
                if not definition.get("question") or not isinstance(definition.get("expected"), dict):
                    raise ValueError("golden query definition incomplete")
        except (KeyError, TypeError, ValueError) as exc:
            raise PlannerError(
                "SEMANTIC_DEFINITION_INVALID", "语义定义内容不符合类型要求", False,
                {"kind": kind, "semantic_key": key},
            ) from exc

    @staticmethod
    def _definition_dict(item: SemanticDefinitionRecord) -> dict[str, Any]:
        return {
            "id": item.id, "source_id": item.source_id, "kind": item.kind,
            "semantic_key": item.semantic_key, "label": item.label,
            "definition": json.loads(item.definition_json or "{}"), "status": item.status,
            "version": item.version, "updated_at": item.updated_at.isoformat(),
        }
