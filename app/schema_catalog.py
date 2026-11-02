from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.conversation.models import SchemaCatalogOverrideRecord
from app.text_to_sql.schema import PostgresSchemaRetriever


class SchemaCatalogService:
    def __init__(self, retriever: PostgresSchemaRetriever, sessions: async_sessionmaker) -> None:
        self.retriever = retriever
        self.sessions = sessions

    async def list_catalog(self, tenant_id: str = "default") -> dict:
        tables = await self.retriever.load_catalog()
        overrides = await self.load_overrides(tenant_id)
        result = []
        for table in tables:
            table_override = overrides.get((table.name, ""), {})
            columns = []
            for column in table.columns:
                override = overrides.get((table.name, column.name), {})
                columns.append({
                    "name": column.name,
                    "data_type": column.data_type,
                    "nullable": column.nullable,
                    "database_comment": column.comment,
                    "display_name": override.get("display_name", ""),
                    "description": override.get("description", ""),
                    "aliases": override.get("aliases", []),
                    "enabled": override.get("enabled", True),
                })
            result.append({
                "schema": table.schema, "name": table.name, "database_comment": table.comment,
                "display_name": table_override.get("display_name", ""),
                "description": table_override.get("description", ""),
                "aliases": table_override.get("aliases", []), "enabled": table_override.get("enabled", True),
                "columns": columns,
            })
        return {"strategy": "postgres_catalog + managed_business_metadata + lexical_rag + foreign_key_graph", "tables": result}

    async def load_overrides(self, tenant_id: str = "default") -> dict[tuple[str, str], dict]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(SchemaCatalogOverrideRecord).where(
                SchemaCatalogOverrideRecord.tenant_id == tenant_id
            ))).all()
        return {(row.table_name, row.column_name): {
            "display_name": row.display_name, "description": row.description,
            "aliases": json.loads(row.aliases_json or "[]"), "enabled": bool(row.enabled),
        } for row in rows}

    async def upsert(self, tenant_id: str, payload: dict) -> dict:
        column_name = payload.get("column_name") or ""
        async with self.sessions() as session:
            record = await session.scalar(select(SchemaCatalogOverrideRecord).where(and_(
                SchemaCatalogOverrideRecord.tenant_id == tenant_id,
                SchemaCatalogOverrideRecord.schema_name == payload["schema_name"],
                SchemaCatalogOverrideRecord.table_name == payload["table_name"],
                SchemaCatalogOverrideRecord.column_name == column_name,
            )))
            if record is None:
                record = SchemaCatalogOverrideRecord(tenant_id=tenant_id, schema_name=payload["schema_name"],
                    table_name=payload["table_name"], column_name=column_name)
                session.add(record)
            record.display_name = payload.get("display_name", "").strip()
            record.description = payload.get("description", "").strip()
            record.aliases_json = json.dumps(payload.get("aliases", []), ensure_ascii=False)
            record.enabled = 1 if payload.get("enabled", True) else 0
            await session.commit()
        return {"saved": True, "table_name": payload["table_name"], "column_name": column_name}
