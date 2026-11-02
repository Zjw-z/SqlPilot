import asyncio
from types import SimpleNamespace

from app.conversation.service import ConversationService
from app.planning.models import DateRange, PlanProvenance, QueryPlanV1


def _plan(intent: str) -> QueryPlanV1:
    return QueryPlanV1(
        intent=intent,
        metrics=["total_fee"] if intent != "unsupported" else [],
        date_range=DateRange(type="all"),
        provenance=PlanProvenance(planner="test", model="fake", prompt_version="test"),
    )


class _Repository:
    def __init__(self):
        self.latest = None
        self.history = []

    async def get(self, conversation_id, tenant_id, user_id):
        return SimpleNamespace(id=conversation_id)

    async def latest_plan(self, conversation_id):
        return self.latest

    async def add_message(self, conversation_id, role, content, message_type="text"):
        self.history.append(SimpleNamespace(role=role, content=content, message_type=message_type))

    async def messages(self, conversation_id):
        return self.history

    async def save_plan(self, conversation_id, plan, status):
        record = SimpleNamespace(
            version=(self.latest[0].version + 1 if self.latest else 1),
            plan_hash=plan.stable_hash(), status=status,
        )
        self.latest = (record, plan)
        return record


class _Planner:
    def __init__(self):
        self.created = 0
        self.revised = 0

    async def create_plan(self, content):
        self.created += 1
        return _plan("unsupported" if "天气" in content else "aggregate_analysis")

    async def revise_plan(self, previous, content):
        self.revised += 1
        return await self.create_plan(content)


def test_off_topic_turn_clears_plan_and_next_question_starts_fresh():
    asyncio.run(_exercise_off_topic_turn())


async def _exercise_off_topic_turn():
    repository, planner = _Repository(), _Planner()
    service = ConversationService(repository, planner, engine=None)

    first = await service.send_message("conversation", "统计医疗总费用", None, "tenant", "user")
    unrelated = await service.send_message(
        "conversation", "今天天气怎么样", first["plan_version"], "tenant", "user"
    )
    assert unrelated["status"] == "unsupported"
    assert unrelated["plan"]["metrics"] == []
    assert unrelated["plan"]["dimensions"] == []
    assert repository.history[-1].message_type == "unsupported"
    assert planner.revised == 1

    next_query = await service.send_message(
        "conversation", "统计医疗总费用", unrelated["plan_version"], "tenant", "user"
    )
    assert next_query["status"] == "awaiting_confirmation"
    assert next_query["plan"]["metrics"] == ["total_fee"]
    assert planner.revised == 1
    assert planner.created == 2
