from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.data_sources import _cosine, _embedding, _tokens


INDEX_VERSION = 3


def _variants(text: str) -> set[str]:
    result = set(_tokens(text))
    for token in list(result):
        if len(token) > 4 and token.endswith("ies"):
            result.add(token[:-3] + "y")
        elif len(token) > 3 and token.endswith("s"):
            result.add(token[:-1])
    return result


@dataclass(frozen=True)
class SpiderKnowledgeHit:
    object_key: str
    object_type: str
    table_name: str
    content: str
    score: float
    vector_score: float
    lexical_score: float
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_key": self.object_key, "object_type": self.object_type,
            "table_name": self.table_name, "content": self.content,
            "score": self.score, "vector_score": self.vector_score,
            "lexical_score": self.lexical_score, "metadata": self.metadata,
            "schema_name": "main",
            "column_name": self.metadata.get("column_name"),
            "business_name": self.metadata.get("business_name", ""),
        }


class SpiderKnowledgeAdapter:
    """Persistent, db_id-isolated Schema knowledge used by the benchmark pipeline.

    Gold SQL and benchmark questions are deliberately not accepted by the builder,
    preventing evaluation-label leakage into retrieval.
    """

    def __init__(self, dataset_dir: Path, index_dir: Path) -> None:
        self.dataset_dir = Path(dataset_dir)
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def index_path(self, db_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", db_id)
        return self.index_dir / f"{safe}.json"

    def build(self, db_id: str, database: Path, schema: dict[str, Any]) -> dict[str, Any]:
        documents = self._documents(db_id, database, schema)
        payload = {
            "version": INDEX_VERSION, "namespace": f"spider:{db_id}",
            "db_id": db_id, "database": str(database), "documents": documents,
        }
        self.index_path(db_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"db_id": db_id, "document_count": len(documents), "path": str(self.index_path(db_id))}

    def ensure(self, db_id: str, database: Path, schema: dict[str, Any]) -> dict[str, Any]:
        path = self.index_path(db_id)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("version") == INDEX_VERSION and payload.get("db_id") == db_id:
                    return payload
            except (OSError, json.JSONDecodeError):
                pass
        self.build(db_id, database, schema)
        return json.loads(path.read_text(encoding="utf-8"))

    def search(self, db_id: str, question: str, database: Path, schema: dict[str, Any],
               limit: int = 12) -> list[SpiderKnowledgeHit]:
        payload = self.ensure(db_id, database, schema)
        query_tokens, query_vector = _variants(question), _embedding(question)
        ranked: list[SpiderKnowledgeHit] = []
        for document in payload["documents"]:
            terms = _variants(document["content"])
            lexical = len(query_tokens & terms) / max(1, len(query_tokens))
            substring = sum(
                1 for left in query_tokens for right in terms
                if min(len(left), len(right)) > 5 and (left in right or right in left)
            )
            vector = _cosine(query_vector, document["embedding"])
            values = document.get("metadata", {}).get("sample_values", [])
            value_match = any(
                str(value).strip() and str(value).lower().strip() in question.lower()
                for value in values
            )
            column_coverage = 0
            if document["object_type"] == "table":
                column_coverage = sum(
                    1 for column in document.get("metadata", {}).get("columns", [])
                    if query_tokens & _variants(
                        f'{column.get("name", "")} {column.get("business_name", "")}'
                    )
                )
            metadata = document.get("metadata", {})
            column_name = str(metadata.get("column_name", "")).lower()
            business_name = str(metadata.get("business_name", "")).lower()
            concept_overlap = len(query_tokens & _variants(f"{column_name} {business_name}"))
            asks_identifier = bool(re.search(r"\b(id|ids|identifier|code|codes)\b", question.lower()))
            identifier_penalty = .12 if document["object_type"] == "column" and (
                column_name.endswith("id") or column_name.endswith("_id")
            ) and not asks_identifier and any(word in question.lower() for word in ("name", "title", "description", "type")) else 0
            score = (vector * .42 + lexical * .30 + min(substring, 3) * .05
                     + (.35 if value_match else 0) + min(column_coverage, 2) * .18)
            score += min(concept_overlap, 2) * .12
            score -= identifier_penalty
            ranked.append(SpiderKnowledgeHit(
                document["object_key"], document["object_type"], document["table_name"],
                document["content"], round(score, 6), round(vector, 6),
                round(lexical, 6), document["metadata"],
            ))
        ranked.sort(key=lambda item: (-item.score, item.object_key))
        positive = [item for item in ranked if item.score > 0]
        return (positive or ranked)[:limit]

    @staticmethod
    def _documents(db_id: str, database: Path, schema: dict[str, Any]) -> list[dict[str, Any]]:
        names = schema.get("table_names_original", [])
        friendly = schema.get("table_names", names)
        columns = schema.get("column_names_original", [])
        column_friendly = schema.get("column_names", columns)
        primary_keys = set(schema.get("primary_keys", []))
        foreign_keys = schema.get("foreign_keys", [])
        table_columns: dict[int, list[dict[str, Any]]] = {index: [] for index in range(len(names))}
        for column_index, (table_index, column_name) in enumerate(columns):
            if table_index < 0:
                continue
            friendly_name = column_friendly[column_index][1] if column_index < len(column_friendly) else column_name
            table_columns[table_index].append({
                "index": column_index, "name": column_name, "business_name": friendly_name,
                "primary_key": column_index in primary_keys,
            })
        samples = SpiderKnowledgeAdapter._samples(database, names, table_columns)
        documents: list[dict[str, Any]] = []
        for table_index, table_name in enumerate(names):
            cols = table_columns[table_index]
            column_text = "；".join(
                f'{item["name"]}（{item["business_name"]}）'
                + ("，主键" if item["primary_key"] else "")
                + (f'，样例值：{"、".join(map(str, samples.get((table_name, item["name"]), [])))}'
                   if samples.get((table_name, item["name"])) else "")
                for item in cols
            )
            content = f"Spider数据源 {db_id}；表 {table_name}（{friendly[table_index]}）；字段：{column_text}"
            documents.append(SpiderKnowledgeAdapter._document(
                "table", f"{db_id}.{table_name}", table_name, content,
                {"db_id": db_id, "table_name": table_name, "business_name": friendly[table_index], "columns": cols},
            ))
            for item in cols:
                values = samples.get((table_name, item["name"]), [])
                content = (
                    f'Spider数据源 {db_id}；表名 {table_name}；表业务名 {friendly[table_index]}；'
                    f'字段名 {item["name"]}；字段业务名 {item["business_name"]}'
                    + (f'；样例值：{"、".join(map(str, values))}' if values else "")
                )
                documents.append(SpiderKnowledgeAdapter._document(
                    "column", f'{db_id}.{table_name}.{item["name"]}', table_name, content,
                    {"db_id": db_id, "table_name": table_name, "column_name": item["name"],
                     "business_name": item["business_name"], "sample_values": values,
                     "primary_key": item["primary_key"]},
                ))
        for left, right in foreign_keys:
            try:
                left_table, left_name = columns[left]
                right_table, right_name = columns[right]
                source, target = names[left_table], names[right_table]
            except (IndexError, TypeError):
                continue
            content = f"Spider数据源 {db_id}；表关系：{source}.{left_name}关联{target}.{right_name}"
            documents.append(SpiderKnowledgeAdapter._document(
                "relationship", f"{db_id}.{source}.{left_name}->{target}.{right_name}", source,
                content, {"db_id": db_id, "source_table": source, "source_column": left_name,
                          "target_table": target, "target_column": right_name},
            ))
        return documents

    @staticmethod
    def _document(object_type: str, object_key: str, table_name: str, content: str,
                  metadata: dict[str, Any]) -> dict[str, Any]:
        return {"object_type": object_type, "object_key": object_key, "table_name": table_name,
                "content": content, "embedding": _embedding(content), "metadata": metadata}

    @staticmethod
    def _samples(database: Path, names: list[str], columns: dict[int, list[dict[str, Any]]],
                 limit: int = 50) -> dict[tuple[str, str], list[Any]]:
        result: dict[tuple[str, str], list[Any]] = {}
        uri = database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=8) as connection:
            connection.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
            connection.execute("PRAGMA query_only=ON")
            for table_index, table_name in enumerate(names):
                safe_table = table_name.replace('"', '""')
                for column in columns.get(table_index, []):
                    safe_column = column["name"].replace('"', '""')
                    try:
                        rows = connection.execute(
                            f'SELECT DISTINCT "{safe_column}" FROM "{safe_table}" '
                            f'WHERE "{safe_column}" IS NOT NULL LIMIT {int(limit)}'
                        ).fetchall()
                    except sqlite3.Error:
                        continue
                    values = [
                        row[0] if isinstance(row[0], (str, int, float, bool)) else str(row[0])
                        for row in rows if len(str(row[0])) <= 80
                    ]
                    if values:
                        result[(table_name, column["name"])] = values
        return result
