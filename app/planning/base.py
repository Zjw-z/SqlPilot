from __future__ import annotations

from typing import Any, Protocol

from app.planning.models import QueryPlanV1


class QueryPlanner(Protocol):
    async def create_plan(self, question: str, schema_context: list[dict[str, Any]] | None = None, memory_context: dict[str, Any] | None = None) -> QueryPlanV1: ...

    async def revise_plan(
        self, current_plan: QueryPlanV1, user_message: str, schema_context: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> QueryPlanV1: ...
