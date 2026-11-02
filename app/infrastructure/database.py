from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.conversation.models import Base
from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_async_engine(settings.system_database_url, future=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            columns = await connection.run_sync(
                lambda sync_connection: {
                    item["name"] for item in inspect(sync_connection).get_columns("data_sources")
                }
            )
            if "business_rules_json" not in columns:
                await connection.execute(text(
                    "ALTER TABLE data_sources ADD COLUMN business_rules_json TEXT NOT NULL DEFAULT '[]'"
                ))

    async def close(self) -> None:
        await self.engine.dispose()
