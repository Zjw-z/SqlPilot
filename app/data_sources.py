from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
from openai import APIConnectionError, APITimeoutError, RateLimitError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.conversation.models import (
    DataSourceRecord,
    SchemaCatalogOverrideRecord,
    SchemaKnowledgeDocumentRecord,
    SchemaSyncJobRecord,
)
from app.core.config import Settings
from app.core.errors import PlannerError
from app.infrastructure.secrets import protect_secret, unprotect_secret
from app.knowledge_store import PgVectorKnowledgeStore


TOOLS = ["search_schema", "get_table_detail", "lookup_dimension_values", "explain_sql", "execute_readonly_sql"]


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    words.update(chinese[index:index + 2] for index in range(max(0, len(chinese) - 1)))
    return {item for item in words if item}


def _embedding(text: str, dimensions: int = 256) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _dictionary_candidate(column: dict[str, Any]) -> bool:
    """Select stable low-cardinality business dimensions, never free text/PII."""
    data_type = str(column.get("data_type", "")).lower()
    if not any(kind in data_type for kind in ("char", "text", "bool", "smallint", "integer")):
        return False
    text = " ".join(str(column.get(key, "")) for key in ("column_name", "column_comment")).lower()
    sensitive = ("name", "phone", "mobile", "address", "id_card", "certno", "姓名", "电话", "地址", "证件")
    if any(term in text for term in sensitive):
        return False
    hints = ("type", "code", "status", "state", "flag", "category", "class", "kind", "level", "grade", "gender", "sex",
             "类别", "类型", "代码", "状态", "标志", "等级", "级别", "性别")
    return any(term in text for term in hints)


async def _dictionary_samples(connection, rows: list[Any], max_columns: int = 250,
                              max_values: int = 20) -> dict[tuple[str, str, str], list[Any]]:
    result: dict[tuple[str, str, str], list[Any]] = {}
    candidates = [dict(row) for row in rows if _dictionary_candidate(dict(row))][:max_columns]
    for column in candidates:
        schema = str(column["table_schema"]).replace('"', '""')
        table = str(column["table_name"]).replace('"', '""')
        name = str(column["column_name"]).replace('"', '""')
        try:
            values = await connection.fetch(
                f'SELECT "{name}" value FROM "{schema}"."{table}" '
                f'WHERE "{name}" IS NOT NULL GROUP BY "{name}" LIMIT {max_values + 1}'
            )
        except asyncpg.PostgresError:
            continue
        if 0 < len(values) <= max_values:
            result[(column["table_schema"], column["table_name"], column["column_name"])] = [
                item["value"] for item in values if len(str(item["value"])) <= 120
            ]
    return result


class DataSourceService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker, knowledge_store: PgVectorKnowledgeStore | None = None) -> None:
        self.settings = settings
        self.sessions = sessions
        self.knowledge_store = knowledge_store
        self.context_learning = None

    async def bootstrap_current(self) -> None:
        if not self.settings.business_database_configured:
            return
        async with self.sessions() as session:
            existing = await session.scalar(select(DataSourceRecord).where(
                DataSourceRecord.tenant_id == "default", DataSourceRecord.name == "默认医保数据源"
            ))
            if existing:
                if not json.loads(existing.business_rules_json or "[]"):
                    existing.business_rules_json = json.dumps(
                        ["valid_settlement_only", "exclude_cancelled"], ensure_ascii=False
                    )
                    await session.commit()
                return
            session.add(DataSourceRecord(
                tenant_id="default", name="默认医保数据源", database_type="postgresql",
                host=self.settings.sqlpilot_db_host, port=self.settings.sqlpilot_db_port,
                database_name=self.settings.sqlpilot_db_name, username=self.settings.sqlpilot_db_user,
                password_cipher=protect_secret(self.settings.sqlpilot_db_password, self.settings.secret_encryption_key),
                schemas_json=json.dumps([self.settings.business_schema]), status="connected",
                business_rules_json=json.dumps(["valid_settlement_only", "exclude_cancelled"]),
            ))
            await session.commit()

    async def list(self, tenant_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(DataSourceRecord).where(DataSourceRecord.tenant_id == tenant_id)
                .order_by(DataSourceRecord.created_at))).all()
        return [self._public(row) for row in rows]

    async def create(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["database_type"] != "postgresql":
            raise PlannerError("UNSUPPORTED_DATABASE", "当前版本暂时只支持PostgreSQL", False)
        record = DataSourceRecord(
            tenant_id=tenant_id, name=payload["name"], database_type=payload["database_type"],
            host=payload["host"], port=payload["port"], database_name=payload["database_name"],
            username=payload["username"], password_cipher=protect_secret(payload["password"], self.settings.secret_encryption_key),
            schemas_json=json.dumps(payload.get("schemas") or ["public"], ensure_ascii=False), status="connecting",
            business_rules_json="[]",
        )
        await self._connect(record)
        record.status = "connected"
        async with self.sessions() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return self._public(record)

    async def _connect(self, source: DataSourceRecord):
        try:
            return await asyncpg.connect(host=source.host, port=source.port, database=source.database_name,
                user=source.username, password=unprotect_secret(source.password_cipher, self.settings.secret_encryption_key), timeout=10)
        except Exception as exc:
            raise PlannerError("DATA_SOURCE_CONNECTION_FAILED", f"数据源连接失败：{type(exc).__name__}", True) from exc

    async def test(self, tenant_id: str, source_id: str) -> dict[str, Any]:
        source = await self._get(tenant_id, source_id)
        connection = await self._connect(source)
        try:
            version = await connection.fetchval("SELECT version()")
            read_only = await connection.fetchval("SHOW default_transaction_read_only")
            return {"connected": True, "database_version": version.split(",")[0], "default_read_only": read_only}
        finally:
            await connection.close()

    async def update_business_rules(
        self, tenant_id: str, source_id: str, business_rules: list[str]
    ) -> dict[str, Any]:
        allowed = {"valid_settlement_only", "exclude_cancelled"}
        if any(item not in allowed for item in business_rules):
            raise PlannerError("INVALID_BUSINESS_RULE", "包含不支持的数据源业务规则", False)
        async with self.sessions.begin() as session:
            source = await session.scalar(select(DataSourceRecord).where(
                DataSourceRecord.id == source_id,
                DataSourceRecord.tenant_id == tenant_id,
            ))
            if source is None:
                raise PlannerError("DATA_SOURCE_NOT_FOUND", "数据源不存在", False)
            source.business_rules_json = json.dumps(
                list(dict.fromkeys(business_rules)), ensure_ascii=False
            )
        return {"source_id": source_id, "business_rules": list(dict.fromkeys(business_rules))}

    async def queue_sync(self, tenant_id: str, source_id: str) -> dict[str, Any]:
        source = await self._get(tenant_id, source_id)
        async with self.sessions.begin() as session:
            active = await session.scalar(
                select(SchemaSyncJobRecord).where(
                    SchemaSyncJobRecord.source_id == source.id,
                    SchemaSyncJobRecord.status.in_(["queued", "running"]),
                ).order_by(SchemaSyncJobRecord.started_at.desc()).limit(1)
            )
            if active:
                return {
                    "job_id": active.id, "status": active.status,
                    "stage": active.stage, "progress": active.progress,
                    "duplicate": True,
                }
            job = SchemaSyncJobRecord(
                source_id=source.id, status="queued", stage="queued", progress=0
            )
            session.add(job)
        return {
            "job_id": job.id, "status": "queued", "stage": "queued",
            "progress": 0, "duplicate": False,
        }

    async def sync(self, tenant_id: str, source_id: str, job_id: str | None = None) -> dict[str, Any]:
        source = await self._get(tenant_id, source_id)
        if job_id:
            async with self.sessions.begin() as session:
                job = await session.get(SchemaSyncJobRecord, job_id)
                if job is None or job.source_id != source.id:
                    raise PlannerError("SYNC_JOB_NOT_FOUND", "Schema同步任务不存在", False)
                job.status = "running"
                job.stage = "connecting"
                job.progress = 5
        else:
            job = SchemaSyncJobRecord(source_id=source.id, status="running", stage="connecting", progress=5)
            async with self.sessions() as session:
                session.add(job); await session.commit(); await session.refresh(job)
        try:
            connection = await self._connect(source)
            schemas = json.loads(source.schemas_json)
            try:
                rows = await connection.fetch("""
                    SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,
                           c.is_nullable='YES' nullable,COALESCE(obj_description(pc.oid),'') table_comment,
                           COALESCE(col_description(pc.oid,pa.attnum),'') column_comment
                    FROM information_schema.columns c JOIN pg_class pc ON pc.relname=c.table_name
                    JOIN pg_namespace pn ON pn.oid=pc.relnamespace AND pn.nspname=c.table_schema
                    JOIN pg_attribute pa ON pa.attrelid=pc.oid AND pa.attname=c.column_name
                    WHERE c.table_schema=ANY($1::text[]) AND pc.relkind IN ('r','v')
                    ORDER BY c.table_schema,c.table_name,c.ordinal_position""", schemas)
                relations = await connection.fetch("""
                    SELECT ns.nspname schema_name,src.relname source_table,sa.attname source_column,
                           dst.relname target_table,da.attname target_column
                    FROM pg_constraint con JOIN pg_class src ON src.oid=con.conrelid
                    JOIN pg_class dst ON dst.oid=con.confrelid JOIN pg_namespace ns ON ns.oid=src.relnamespace
                    JOIN unnest(con.conkey) WITH ORDINALITY sk(attnum,ord) ON true
                    JOIN unnest(con.confkey) WITH ORDINALITY dk(attnum,ord) ON dk.ord=sk.ord
                    JOIN pg_attribute sa ON sa.attrelid=src.oid AND sa.attnum=sk.attnum
                    JOIN pg_attribute da ON da.attrelid=dst.oid AND da.attnum=dk.attnum
                    WHERE con.contype='f' AND ns.nspname=ANY($1::text[])""", schemas)
                dictionary_samples = await _dictionary_samples(connection, rows)
            finally:
                await connection.close()
            await self._update_sync_job(
                job.id, stage="catalog_scanned", progress=30,
                table_count=len({(row["table_schema"], row["table_name"]) for row in rows}),
                column_count=len(rows),
            )
            async with self.sessions() as session:
                override_rows = (await session.scalars(select(SchemaCatalogOverrideRecord).where(
                    SchemaCatalogOverrideRecord.tenant_id == tenant_id
                ))).all()
            overrides = {
                (item.schema_name, item.table_name, item.column_name): {
                    "display_name": item.display_name,
                    "description": item.description,
                    "aliases": json.loads(item.aliases_json or "[]"),
                    "enabled": bool(item.enabled),
                }
                for item in override_rows
            }
            canonical = json.dumps(
                {
                    "database_schema": [dict(row) for row in rows],
                    "business_metadata": [
                        {"schema": key[0], "table": key[1], "column": key[2], **value}
                        for key, value in sorted(overrides.items())
                    ],
                },
                ensure_ascii=False, default=str, sort_keys=True,
            )
            fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
            version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + fingerprint[:8]
            tables: dict[tuple[str, str], dict] = {}
            for row in rows:
                key = (row["table_schema"], row["table_name"])
                tables.setdefault(key, {"schema": row["table_schema"], "name": row["table_name"],
                    "comment": row["table_comment"], "columns": []})["columns"].append(dict(row))
            documents = []
            for (schema, table_name), table in tables.items():
                table_override = overrides.get((schema, table_name, ""), {})
                if table_override.get("enabled") is False:
                    continue
                table_business_text = "；".join(filter(None, [
                    table_override.get("display_name", ""), table_override.get("description", ""),
                    "、".join(table_override.get("aliases", [])), table["comment"],
                ]))
                enabled_columns = [
                    column for column in table["columns"]
                    if overrides.get((schema, table_name, column["column_name"]), {}).get("enabled", True)
                ]
                column_text = "；".join(
                    f'{c["column_name"]}({c["data_type"]}) '
                    + "；".join(filter(None, [
                        overrides.get((schema, table_name, c["column_name"]), {}).get("display_name", ""),
                        overrides.get((schema, table_name, c["column_name"]), {}).get("description", ""),
                        "、".join(overrides.get((schema, table_name, c["column_name"]), {}).get("aliases", [])),
                        c["column_comment"],
                    ]))
                    for c in enabled_columns
                )
                table_metadata = {**table, "business_metadata": table_override}
                content = f'表 {schema}.{table_name}。{table_business_text}。字段：{column_text}'
                documents.append(("table", f"{schema}.{table_name}", table_name, content, table_metadata))
                for column in table["columns"]:
                    override = overrides.get((schema, table_name, column["column_name"]), {})
                    if override.get("enabled") is False:
                        continue
                    business_text = "；".join(filter(None, [
                        override.get("display_name", ""), override.get("description", ""),
                        "、".join(override.get("aliases", [])), column["column_comment"],
                    ]))
                    values = dictionary_samples.get((schema, table_name, column["column_name"]), [])
                    value_text = "、".join(str(value).strip() for value in values)
                    content = (
                        f'Schema {schema}；表名 {table_name}；表注释 {table_business_text}；'
                        f'字段名 {column["column_name"]}；字段类型 {column["data_type"]}；'
                        f'字段注释与业务别名 {business_text}'
                        + (f'；低基数字典值 {value_text}' if value_text else "")
                    )
                    metadata = {**column, "business_metadata": override, "sample_values": values,
                                "dictionary_values": bool(values)}
                    documents.append(("column", f'{schema}.{table_name}.{column["column_name"]}', table_name, content, metadata))
            for relation in relations:
                key = f'{relation["schema_name"]}.{relation["source_table"]}.{relation["source_column"]}->{relation["target_table"]}.{relation["target_column"]}'
                content = f'表关系：{relation["source_table"]}.{relation["source_column"]}关联{relation["target_table"]}.{relation["target_column"]}'
                documents.append(("relationship", key, relation["source_table"], content, dict(relation)))
            if self.knowledge_store:
                await self._update_sync_job(
                    job.id, stage="embedding", progress=55,
                    document_count=len(documents),
                )
                pg_documents=[]
                for object_type, object_key, table_name, content, metadata in documents:
                    parts=object_key.split(".")
                    managed = metadata.get("business_metadata", {}) if isinstance(metadata, dict) else {}
                    raw_name = metadata.get("column_comment", "") if object_type == "column" else metadata.get("comment", "") if isinstance(metadata, dict) else ""
                    business_name = managed.get("display_name") or (raw_name.split("；", 1)[0].strip() if raw_name else "")
                    pg_documents.append({"object_type":object_type,"object_key":object_key,
                        "schema_name":parts[0],"table_name":table_name,
                        "column_name":parts[2] if object_type=="column" and len(parts)>2 else None,
                        "business_name":business_name,"content":content,
                        "aliases":managed.get("aliases", []),"metadata":metadata})
                await self.knowledge_store.replace_version(tenant_id,source.id,version,fingerprint,len(tables),len(rows),pg_documents)
                await self._update_sync_job(job.id, stage="activating", progress=90)
            invalidated_paths = 0
            if self.context_learning:
                invalidated_paths = await self.context_learning.invalidate_for_schema_change(
                    tenant_id, source.id, source.schema_fingerprint, fingerprint
                )
            async with self.sessions() as session:
                db_source = await session.get(DataSourceRecord, source.id)
                db_job = await session.get(SchemaSyncJobRecord, job.id)
                db_source.status="ready"; db_source.schema_version=version; db_source.schema_fingerprint=fingerprint
                db_source.tools_json=json.dumps(TOOLS); db_source.last_error=""; db_source.last_synced_at=datetime.now(timezone.utc)
                db_job.status="completed"; db_job.stage="ready"; db_job.progress=100
                db_job.table_count=len(tables); db_job.column_count=len(rows); db_job.document_count=len(documents)
                db_job.completed_at=datetime.now(timezone.utc); await session.commit()
            return {"job_id": job.id, "status": "completed", "stage": "ready", "progress": 100,
                "table_count": len(tables), "column_count": len(rows), "document_count": len(documents),
                "schema_version": version, "tools": TOOLS,
                "invalidated_query_paths": invalidated_paths}
        except Exception as exc:
            async with self.sessions() as session:
                db_source=await session.get(DataSourceRecord,source.id); db_job=await session.get(SchemaSyncJobRecord,job.id)
                db_source.status="failed"; db_source.last_error=type(exc).__name__; db_job.status="failed"; db_job.stage="failed"
                db_job.error_message=type(exc).__name__; db_job.completed_at=datetime.now(timezone.utc); await session.commit()
            raise

    async def search(self, tenant_id: str, source_id: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
        source = await self._get(tenant_id, source_id)
        if self.knowledge_store and source.status == "ready":
            try:
                return await self.knowledge_store.search(tenant_id,source_id,query,limit)
            except (
                ConnectionError, OSError, asyncpg.PostgresError,
                APIConnectionError, APITimeoutError, RateLimitError,
            ) as exc:
                raise PlannerError(
                    "KNOWLEDGE_STORE_UNAVAILABLE",
                    "Schema知识检索服务暂不可用，请确认PostgreSQL、pgvector及Embedding模型连接正常",
                    True,
                ) from exc
        query_tokens, query_vector = _tokens(query), _embedding(query)
        async with self.sessions() as session:
            rows = (await session.scalars(select(SchemaKnowledgeDocumentRecord).where(
                SchemaKnowledgeDocumentRecord.source_id == source.id,
                SchemaKnowledgeDocumentRecord.schema_version == source.schema_version,
                SchemaKnowledgeDocumentRecord.enabled == 1))).all()
        ranked=[]
        for row in rows:
            lexical=len(query_tokens & _tokens(row.content))/max(1,len(query_tokens))
            vector=max(0.0,_cosine(query_vector,json.loads(row.embedding_json)))
            score=round(0.6*lexical+0.4*vector,4)
            if score>0: ranked.append((score,row))
        ranked.sort(key=lambda item:item[0],reverse=True)
        return [{"score":score,"object_type":row.object_type,"object_key":row.object_key,
            "table_name":row.table_name,"content":row.content,"metadata":json.loads(row.metadata_json)} for score,row in ranked[:limit]]

    async def latest_job(self, tenant_id: str, source_id: str) -> dict[str, Any] | None:
        await self._get(tenant_id, source_id)
        async with self.sessions() as session:
            row=await session.scalar(select(SchemaSyncJobRecord).where(SchemaSyncJobRecord.source_id==source_id)
                .order_by(SchemaSyncJobRecord.started_at.desc()).limit(1))
        return None if not row else {key:getattr(row,key) for key in ("id","status","stage","progress","table_count","column_count","document_count","error_message")}

    async def _update_sync_job(self, job_id: str, **values: Any) -> None:
        async with self.sessions.begin() as session:
            job = await session.get(SchemaSyncJobRecord, job_id)
            if job is None:
                return
            for key, value in values.items():
                setattr(job, key, value)

    async def ready_source(self, tenant_id: str, source_id: str | None = None) -> dict[str, Any]:
        if source_id:
            source = await self._get(tenant_id, source_id)
            if source.status != "ready":
                raise PlannerError("DATA_SOURCE_NOT_READY", "所选数据源尚未完成Schema知识库构建", False)
        else:
            async with self.sessions() as session:
                source = await session.scalar(
                    select(DataSourceRecord).where(
                        DataSourceRecord.tenant_id == tenant_id,
                        DataSourceRecord.status == "ready",
                    ).order_by(DataSourceRecord.created_at)
                )
            if source is None:
                raise PlannerError("DATA_SOURCE_NOT_READY", "当前没有可用于查询的已就绪数据源", False)
        return self._public(source)

    async def connection_profile(self, tenant_id: str, source_id: str) -> dict[str, Any]:
        source = await self._get(tenant_id, source_id)
        if source.status != "ready":
            raise PlannerError("DATA_SOURCE_NOT_READY", "所选数据源尚未就绪", False)
        return {
            "id": source.id,
            "tenant_id": tenant_id,
            "host": source.host,
            "port": source.port,
            "database": source.database_name,
            "username": source.username,
            "password": unprotect_secret(source.password_cipher, self.settings.secret_encryption_key),
            "schemas": json.loads(source.schemas_json),
            "schema_version": source.schema_version,
        }

    async def schema_tables(self, tenant_id: str, source_id: str) -> list[dict[str, Any]]:
        source = await self._get(tenant_id, source_id)
        connection = await self._connect(source)
        try:
            schemas = json.loads(source.schemas_json)
            rows = await connection.fetch(
                """SELECT n.nspname schema_name,c.relname table_name,
                          COALESCE(obj_description(c.oid),'') description,
                          COUNT(a.attnum) FILTER (WHERE a.attnum>0 AND NOT a.attisdropped) column_count
                   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   LEFT JOIN pg_attribute a ON a.attrelid=c.oid
                   WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','v')
                   GROUP BY n.nspname,c.relname,c.oid ORDER BY n.nspname,c.relname""",
                schemas,
            )
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def table_detail(self, tenant_id: str, source_id: str, schema_name: str, table_name: str) -> dict[str, Any]:
        source = await self._get(tenant_id, source_id)
        if schema_name not in json.loads(source.schemas_json):
            raise PlannerError("SCHEMA_NOT_ALLOWED", "Schema不在当前数据源授权范围内", False)
        connection = await self._connect(source)
        try:
            rows = await connection.fetch(
                """SELECT c.column_name,c.data_type,c.is_nullable='YES' nullable,
                          COALESCE(col_description(pc.oid,pa.attnum),'') description
                   FROM information_schema.columns c
                   JOIN pg_class pc ON pc.relname=c.table_name
                   JOIN pg_namespace pn ON pn.oid=pc.relnamespace AND pn.nspname=c.table_schema
                   JOIN pg_attribute pa ON pa.attrelid=pc.oid AND pa.attname=c.column_name
                   WHERE c.table_schema=$1 AND c.table_name=$2 ORDER BY c.ordinal_position""",
                schema_name,
                table_name,
            )
            if not rows:
                raise PlannerError("TABLE_NOT_FOUND", "数据源中不存在该表或视图", False)
            return {"schema_name": schema_name, "table_name": table_name, "columns": [dict(row) for row in rows]}
        finally:
            await connection.close()

    async def dimension_values(
        self,
        tenant_id: str,
        source_id: str,
        schema_name: str,
        table_name: str,
        column_name: str,
        limit: int = 50,
    ) -> list[Any]:
        detail = await self.table_detail(tenant_id, source_id, schema_name, table_name)
        if column_name not in {item["column_name"] for item in detail["columns"]}:
            raise PlannerError("COLUMN_NOT_FOUND", "数据源中不存在该字段", False)
        source = await self._get(tenant_id, source_id)
        connection = await self._connect(source)
        quote = lambda value: '"' + value.replace('"', '""') + '"'
        sql = (
            f"SELECT {quote(column_name)} value, COUNT(*) frequency "
            f"FROM {quote(schema_name)}.{quote(table_name)} "
            f"WHERE {quote(column_name)} IS NOT NULL GROUP BY {quote(column_name)} "
            "ORDER BY frequency DESC LIMIT $1"
        )
        try:
            async with connection.transaction(readonly=True):
                rows = await connection.fetch(sql, max(1, min(limit, 100)))
            return [{"value": row["value"], "frequency": row["frequency"]} for row in rows]
        finally:
            await connection.close()

    async def _get(self, tenant_id: str, source_id: str) -> DataSourceRecord:
        async with self.sessions() as session:
            row=await session.scalar(select(DataSourceRecord).where(DataSourceRecord.id==source_id,DataSourceRecord.tenant_id==tenant_id))
        if not row: raise PlannerError("DATA_SOURCE_NOT_FOUND","数据源不存在",False)
        return row

    @staticmethod
    def _public(row: DataSourceRecord) -> dict[str, Any]:
        return {"id":row.id,"name":row.name,"database_type":row.database_type,"host":row.host,"port":row.port,
            "database_name":row.database_name,"username":row.username,"schemas":json.loads(row.schemas_json),
            "status":row.status,"schema_version":row.schema_version,"tools":json.loads(row.tools_json),
            "schema_fingerprint":row.schema_fingerprint,
            "business_rules":json.loads(row.business_rules_json or "[]"),
            "last_error":row.last_error,"last_synced_at":row.last_synced_at.isoformat() if row.last_synced_at else None}
