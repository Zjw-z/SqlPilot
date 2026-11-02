from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from openai import AsyncOpenAI

from app.core.config import Settings


class PgVectorKnowledgeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.dashscope_api_key,
            base_url=settings.sqlpilot_bailian_base_url, timeout=settings.planner_timeout_seconds,
            max_retries=settings.planner_max_retries)

    async def connect(self):
        return await asyncpg.connect(host=self.settings.sqlpilot_kb_host or self.settings.sqlpilot_db_host,
            port=self.settings.sqlpilot_kb_port or self.settings.sqlpilot_db_port,
            database=self.settings.sqlpilot_kb_name or self.settings.sqlpilot_db_name,
            user=self.settings.sqlpilot_kb_user or self.settings.sqlpilot_db_user,
            password=self.settings.sqlpilot_kb_password or self.settings.sqlpilot_db_password, timeout=10)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        size = self.settings.sqlpilot_embedding_batch_size
        for start in range(0, len(texts), size):
            response = await self.client.embeddings.create(model=self.settings.sqlpilot_embedding_model,
                input=texts[start:start + size], dimensions=self.settings.sqlpilot_embedding_dimensions,
                encoding_format="float")
            result.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        return result

    async def replace_version(self, tenant_id: str, source_id: str, version: str, fingerprint: str,
        table_count: int, column_count: int, documents: list[dict[str, Any]]) -> None:
        embeddings = await self.embed([item["content"] for item in documents])
        connection = await self.connect()
        try:
            async with connection.transaction():
                await connection.execute("""INSERT INTO sqlpilot_kb.schema_versions
                    (source_id,version,fingerprint,embedding_model,embedding_dimensions,status,table_count,column_count,document_count,active)
                    VALUES($1::uuid,$2,$3,$4,$5,'building',$6,$7,$8,false)
                    ON CONFLICT(source_id,version) DO UPDATE SET status='building',document_count=EXCLUDED.document_count""",
                    source_id, version, fingerprint, self.settings.sqlpilot_embedding_model,
                    self.settings.sqlpilot_embedding_dimensions, table_count, column_count, len(documents))
                await connection.execute("DELETE FROM sqlpilot_kb.schema_documents WHERE source_id=$1::uuid AND schema_version=$2", source_id, version)
                rows=[]
                for item, vector in zip(documents, embeddings):
                    rows.append((str(uuid.uuid4()),tenant_id,source_id,version,item["object_type"],item["object_key"],
                        item["schema_name"],item["table_name"],item.get("column_name"),item.get("business_name",""),
                        item["content"],json.dumps(item.get("aliases",[]),ensure_ascii=False),
                        json.dumps(item.get("metadata",{}),ensure_ascii=False,default=str),
                        "[" + ",".join(f"{value:.8f}" for value in vector) + "]"))
                await connection.executemany("""INSERT INTO sqlpilot_kb.schema_documents
                    (id,tenant_id,source_id,schema_version,object_type,object_key,schema_name,table_name,column_name,
                     business_name,content,aliases,metadata,embedding)
                    VALUES($1::uuid,$2,$3::uuid,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13::jsonb,$14::vector)""", rows)
                await connection.execute("UPDATE sqlpilot_kb.schema_versions SET active=false WHERE source_id=$1::uuid", source_id)
                await connection.execute("""UPDATE sqlpilot_kb.schema_versions SET active=true,status='ready',activated_at=now()
                    WHERE source_id=$1::uuid AND version=$2""", source_id, version)
        finally:
            await connection.close()

    async def search(self, tenant_id: str, source_id: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
        vector = (await self.embed([query]))[0]
        vector_literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
        connection = await self.connect()
        try:
            rows = await connection.fetch("""SELECT d.object_type,d.object_key,d.schema_name,d.table_name,d.column_name,
                       d.business_name,d.content,d.metadata,
                       round((1-(d.embedding <=> $4::vector))::numeric,4) vector_score,
                       round(similarity(d.content,$5)::numeric,4) lexical_score,
                       round((0.7*(1-(d.embedding <=> $4::vector))+0.3*similarity(d.content,$5))::numeric,4) score
                FROM sqlpilot_kb.schema_documents d
                JOIN sqlpilot_kb.schema_versions v ON v.source_id=d.source_id AND v.version=d.schema_version AND v.active
                WHERE d.tenant_id=$1 AND d.source_id=$2::uuid AND d.enabled
                ORDER BY (0.7*(d.embedding <=> $4::vector)-0.3*similarity(d.content,$5)) ASC LIMIT $3""",
                tenant_id, source_id, limit, vector_literal, query)
            result = [{"score":float(row["score"]),"vector_score":float(row["vector_score"]),
                "lexical_score":float(row["lexical_score"]),"object_type":row["object_type"],
                "object_key":row["object_key"],"schema_name":row["schema_name"],"table_name":row["table_name"],
                "column_name":row["column_name"],"business_name":row["business_name"],"content":row["content"],
                "metadata":json.loads(row["metadata"]) if isinstance(row["metadata"],str) else row["metadata"]} for row in rows]
            columns = [item for item in result if item["object_type"] == "column"]
            ambiguous_keys: set[str] = set()
            if len(columns) > 1 and columns[0]["score"] - columns[1]["score"] < 0.02:
                cutoff = columns[0]["score"] - 0.02
                ambiguous_keys = {item["object_key"] for item in columns if item["score"] >= cutoff}
            for item in result:
                item["match_level"] = "高度相关" if item["score"] >= 0.6 else "相关" if item["score"] >= 0.4 else "可能相关"
                item["requires_confirmation"] = item["object_key"] in ambiguous_keys
            return result
        finally:
            await connection.close()

    async def stats(self, source_id: str) -> dict[str, Any]:
        connection = await self.connect()
        try:
            row=await connection.fetchrow("""SELECT version,embedding_model,embedding_dimensions,document_count,active
                FROM sqlpilot_kb.schema_versions WHERE source_id=$1::uuid ORDER BY created_at DESC LIMIT 1""",source_id)
            return dict(row) if row else {}
        finally:
            await connection.close()
