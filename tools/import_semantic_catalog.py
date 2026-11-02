from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.conversation.models import DataSourceRecord
from app.core.config import get_settings
from app.infrastructure.database import Database
from app.semantic_layer import SemanticLayerService


async def import_catalog(path: Path, source_id: str | None, source_name: str | None) -> dict[str, int]:
    database = Database(get_settings())
    await database.initialize()
    try:
        async with database.sessions() as session:
            query = select(DataSourceRecord)
            if source_id:
                query = query.where(DataSourceRecord.id == source_id)
            elif source_name:
                query = query.where(DataSourceRecord.name == source_name)
            else:
                query = query.where(DataSourceRecord.status == "ready")
            sources = (await session.scalars(query)).all()
        if len(sources) != 1:
            raise ValueError(f"expected exactly one data source, found {len(sources)}")
        source = sources[0]
        definitions = json.loads(path.read_text(encoding="utf-8"))
        service = SemanticLayerService(database.sessions)
        counts = {"certified": 0, "draft": 0, "disabled": 0}
        for payload in definitions:
            await service.upsert_definition(source.tenant_id, source.id, payload)
            counts[payload["status"]] += 1
        return counts
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import governed semantic definitions into SQLPilot")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--source-id")
    parser.add_argument("--source-name")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(import_catalog(args.catalog, args.source_id, args.source_name)), ensure_ascii=False))


if __name__ == "__main__":
    main()
