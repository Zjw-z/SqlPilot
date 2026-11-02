from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from app.core.config import Settings
from app.planning.models import QueryPlanV1


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    comment: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class TableInfo:
    schema: str
    name: str
    comment: str = ""
    columns: list[ColumnInfo] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    cardinality: str = "N:1"
    source: str = "database_foreign_key"
    certified: bool = True


@dataclass
class SchemaContext:
    tables: list[TableInfo]
    relationships: list[Relationship]
    strategy: str = "postgres_catalog_lexical_rag"

    @property
    def allowed_tables(self) -> set[str]:
        return {table.name for table in self.tables}

    @property
    def allowed_qualified_tables(self) -> set[tuple[str, str]]:
        return {(table.schema, table.name) for table in self.tables}

    @property
    def columns_by_table(self) -> dict[tuple[str, str], set[str]]:
        return {
            (table.schema, table.name): {column.name for column in table.columns}
            for table in self.tables
        }

    @property
    def allowed_columns(self) -> set[str]:
        return {column.name for table in self.tables for column in table.columns}

    def prompt_text(self) -> str:
        lines = []
        for table in self.tables:
            lines.append(f"TABLE {table.schema}.{table.name} -- {table.comment}")
            for column in table.columns:
                lines.append(f"  {column.name} {column.data_type} -- {column.comment}")
        if self.relationships:
            lines.append("VERIFIED RELATIONSHIPS")
            for item in self.relationships:
                lines.append(
                    f"  {item.source_table}.{item.source_column} -> "
                    f"{item.target_table}.{item.target_column} "
                    f"[{item.cardinality}, {item.source}, certified={str(item.certified).lower()}]"
                )
        return "\n".join(lines)


class PostgresSchemaRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.override_loader = None
        self.knowledge_search_loader = None

    def set_override_loader(self, loader) -> None:
        self.override_loader = loader

    def set_knowledge_search_loader(self, loader) -> None:
        self.knowledge_search_loader = loader

    async def connect(self, source_profile: dict | None = None):
        profile = source_profile or {}
        return await asyncpg.connect(
            host=profile.get("host", self.settings.sqlpilot_db_host),
            port=profile.get("port", self.settings.sqlpilot_db_port),
            database=profile.get("database", self.settings.sqlpilot_db_name),
            user=profile.get("username", self.settings.sqlpilot_db_user),
            password=profile.get("password", self.settings.sqlpilot_db_password),
            timeout=10,
        )

    async def retrieve(self, plan: QueryPlanV1, limit: int = 6, source_profile: dict | None = None) -> SchemaContext:
        tables_list = await self.load_catalog(source_profile)
        tables = {table.name: table for table in tables_list}
        if self.override_loader:
            overrides = await self.override_loader((source_profile or {}).get("tenant_id", "default"))
            for table_name in list(tables):
                table = tables[table_name]
                table_override = overrides.get((table_name, ""), {})
                if not table_override.get("enabled", True):
                    del tables[table_name]
                    continue
                table.aliases = table_override.get("aliases", [])
                table.comment = " ".join(filter(None, [table_override.get("display_name"), table_override.get("description"), table.comment]))
                enabled_columns = []
                for column in table.columns:
                    override = overrides.get((table_name, column.name), {})
                    if not override.get("enabled", True):
                        continue
                    column.aliases = override.get("aliases", [])
                    column.comment = " ".join(filter(None, [override.get("display_name"), override.get("description"), column.comment]))
                    enabled_columns.append(column)
                table.columns = enabled_columns
        connection = await self.connect(source_profile)
        try:
            keywords = self._keywords(plan)
            knowledge_tables: set[str] = set()
            evidence_tables = {
                item.object_key.split(".")[1]
                for item in plan.schema_evidence
                if len(item.object_key.split(".")) >= 2
            }
            if evidence_tables:
                knowledge_tables = evidence_tables
            elif self.knowledge_search_loader:
                matches = await self.knowledge_search_loader(" ".join(sorted(keywords)))
                knowledge_tables = {item["table_name"] for item in matches}
            ranked = sorted(tables.values(), key=lambda item: self._score(item, keywords), reverse=True)
            if knowledge_tables:
                ranked.sort(key=lambda item: (item.name in knowledge_tables, self._score(item, keywords)), reverse=True)
            selected = [item for item in ranked if self._score(item, keywords) > 0][:limit]
            if not selected:
                selected = ranked[:limit]
            selected_names = {item.name for item in selected}
            schemas = (source_profile or {}).get("schemas") or [self.settings.business_schema]
            all_relations = await self._relationships(connection, set(), schemas)
            expanded_names = self._bridge_tables(selected_names, all_relations, limit)
            selected = [table for table in tables.values() if table.name in expanded_names]
            selected.sort(key=lambda item: (item.name not in selected_names, -self._score(item, keywords), item.name))
            relations = [item for item in all_relations
                         if item.source_table in expanded_names and item.target_table in expanded_names]
            strategy = "knowledge_base_hybrid_rag_fk_graph" if knowledge_tables else "managed_catalog_lexical_rag_fk_graph"
            return SchemaContext(selected, relations, strategy)
        finally:
            await connection.close()

    async def load_catalog(self, source_profile: dict | None = None) -> list[TableInfo]:
        connection = await self.connect(source_profile)
        try:
            rows = await connection.fetch(
                """
                SELECT c.table_schema, c.table_name, c.column_name, c.data_type,
                       c.is_nullable = 'YES' AS nullable,
                       COALESCE(obj_description(pc.oid), '') AS table_comment,
                       COALESCE(col_description(pc.oid, pa.attnum), '') AS column_comment
                FROM information_schema.columns c
                JOIN pg_class pc ON pc.relname = c.table_name
                JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = c.table_schema
                JOIN pg_attribute pa ON pa.attrelid = pc.oid AND pa.attname = c.column_name
                WHERE c.table_schema = ANY($1::text[]) AND pc.relkind IN ('r', 'v')
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
                """,
                (source_profile or {}).get("schemas") or [self.settings.business_schema],
            )
            tables: dict[tuple[str, str], TableInfo] = {}
            for row in rows:
                table = tables.setdefault(
                    (row["table_schema"], row["table_name"]),
                    TableInfo(row["table_schema"], row["table_name"], row["table_comment"]),
                )
                table.columns.append(
                    ColumnInfo(row["column_name"], row["data_type"], row["nullable"], row["column_comment"])
                )
            return list(tables.values())
        finally:
            await connection.close()

    @staticmethod
    def _keywords(plan: QueryPlanV1) -> set[str]:
        mapping = {
            "fund_pay_total": {"基金支付总额", "fund_pay_sumamt", "基金支付金额", "fund_payamt", "结算"},
            "total_fee": {"医疗费总额", "medfee_sumamt", "项目总金额", "结算"},
            "settlement_count": {"结算id", "setl_id", "结算"},
            "month": {"结算时间", "setl_time", "月份"},
            "day": {"结算时间", "setl_time", "日期", "日"},
            "week": {"结算时间", "setl_time", "周", "星期"},
            "quarter": {"结算时间", "setl_time", "季度"},
            "year": {"结算时间", "setl_time", "年度", "年份"},
            "institution": {"定点医药机构", "fixmedins", "医疗机构"},
            "institution_level": {"医院等级", "hosp_lv", "医疗机构等级"},
        }
        result: set[str] = set()
        for metric in plan.metrics:
            result.update(mapping.get(metric, set()))
        for dimension in plan.dimensions:
            result.update(mapping.get(dimension, set()))
        for item in plan.filters:
            result.update({item.field, str(item.value), item.display_value})
        for binding in plan.semantic_bindings:
            result.update({binding.key, binding.label, binding.table_name, binding.column_name})
        return {item.lower() for item in result}

    @staticmethod
    def _score(table: TableInfo, keywords: set[str]) -> int:
        table_text = f"{table.name} {table.comment} {' '.join(table.aliases)}".lower()
        score = sum(3 for keyword in keywords if keyword in table_text)
        for column in table.columns:
            text = f"{column.name} {column.comment} {' '.join(column.aliases)}".lower()
            score += sum(2 for keyword in keywords if keyword in text)
        return score

    async def _relationships(self, connection, tables: set[str], schemas: list[str]) -> list[Relationship]:
        rows = await connection.fetch(
            """
            SELECT src.relname source_table, sa.attname source_column,
                   dst.relname target_table, da.attname target_column
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_class dst ON dst.oid = con.confrelid
            JOIN pg_namespace ns ON ns.oid = src.relnamespace
            JOIN unnest(con.conkey) WITH ORDINALITY sk(attnum, ord) ON true
            JOIN unnest(con.confkey) WITH ORDINALITY dk(attnum, ord) ON dk.ord = sk.ord
            JOIN pg_attribute sa ON sa.attrelid = src.oid AND sa.attnum = sk.attnum
            JOIN pg_attribute da ON da.attrelid = dst.oid AND da.attnum = dk.attnum
            WHERE con.contype = 'f' AND ns.nspname = ANY($1::text[])
            """,
            schemas,
        )
        return [
            Relationship(row["source_table"], row["source_column"], row["target_table"], row["target_column"])
            for row in rows
            if not tables or (row["source_table"] in tables and row["target_table"] in tables)
        ]

    @staticmethod
    def _bridge_tables(selected: set[str], relations: list[Relationship], limit: int) -> set[str]:
        """Add only tables on verified shortest FK paths between selected seeds."""
        if len(selected) < 2:
            return set(selected)
        graph: dict[str, set[str]] = {}
        for edge in relations:
            graph.setdefault(edge.source_table, set()).add(edge.target_table)
            graph.setdefault(edge.target_table, set()).add(edge.source_table)
        result = set(selected)
        seeds = sorted(selected)
        for index, start in enumerate(seeds):
            for target in seeds[index + 1:]:
                queue = [(start, [start])]
                visited = {start}
                found: list[str] | None = None
                while queue:
                    node, path = queue.pop(0)
                    if node == target:
                        found = path
                        break
                    for neighbor in sorted(graph.get(node, set())):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append((neighbor, path + [neighbor]))
                if found and len(result | set(found)) <= limit:
                    result.update(found)
        return result
