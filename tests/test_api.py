from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.planning.models import (
    Clarification,
    ClarificationOption,
    Comparison,
    DateRange,
    PlanProvenance,
    QueryFilter,
    QueryPlanV1,
    Ranking,
)


def make_plan(clarifying: bool = False) -> QueryPlanV1:
    clarifications = []
    if clarifying:
        clarifications = [
            Clarification(
                id="ranking_scope",
                question="增长较高的月份应该在哪个范围内比较？",
                reason="存在多个合理排名范围",
                options=[
                    ClarificationOption(value="within_institution", label="每家机构分别排名"),
                    ClarificationOption(value="global", label="所有机构月份统一排名"),
                ],
            )
        ]
    return QueryPlanV1(
        intent="aggregate_analysis",
        metric="fund_pay_total",
        dimensions=["month", "institution"],
        date_range=DateRange(
            type="explicit",
            start=date(2025, 1, 1),
            end=date(2025, 6, 30),
            comparison_start=date(2024, 1, 1),
            comparison_end=date(2024, 6, 30),
        ),
        filters=[QueryFilter(field="medical_type", value="inpatient", display_value="住院")],
        comparison=Comparison(type="year_over_year", grain="month"),
        ranking=Ranking(metric="yoy_rate", scope=None if clarifying else "global", direction="desc"),
        clarifications=clarifications,
        provenance=PlanProvenance(planner="test", model="fake", prompt_version="test-v1"),
    )


class FakePlanner:
    async def create_plan(self, question: str) -> QueryPlanV1:
        return make_plan(clarifying=True)

    async def revise_plan(self, current_plan: QueryPlanV1, user_message: str) -> QueryPlanV1:
        return make_plan(clarifying=False)


def create_test_client(planner=None):
    db_path = Path("data") / f"test_system_{uuid4().hex}.db"
    settings = Settings(
        system_database_url=f"sqlite+aiosqlite:///{db_path.resolve().as_posix()}",
        dashscope_api_key="test",
        sqlpilot_db_host="",
        sqlpilot_db_name="",
        sqlpilot_db_user="",
        sqlpilot_db_password="",
        auth_required=False,
    )
    return TestClient(create_app(settings=settings, planner=planner or FakePlanner()))


def test_unrelated_question_cannot_confirm_or_inherit_previous_query():
    class TopicPlanner(FakePlanner):
        def __init__(self):
            self.create_calls = 0

        async def create_plan(self, question: str) -> QueryPlanV1:
            self.create_calls += 1
            if "天气" in question:
                return QueryPlanV1(
                    intent="unsupported", date_range=DateRange(type="all"),
                    provenance=PlanProvenance(planner="test", model="fake", prompt_version="test-v1"),
                )
            return make_plan()

        async def revise_plan(self, current_plan: QueryPlanV1, user_message: str) -> QueryPlanV1:
            return await self.create_plan(user_message)

    planner = TopicPlanner()
    with create_test_client(planner) as client:
        conversation = client.post("/api/v1/conversations", json={}).json()["data"]
        url = f"/api/v1/conversations/{conversation['id']}/messages"
        first = client.post(url, json={"content": "统计医疗费用"}).json()["data"]
        unrelated = client.post(url, json={
            "content": "今天天气怎么样", "base_plan_version": first["plan_version"],
        }).json()["data"]

        assert unrelated["status"] == "unsupported"
        assert unrelated["plan"]["metrics"] == []
        assert unrelated["plan"]["dimensions"] == []
        assert "不会生成或执行 SQL" in unrelated["assistant_message"]
        assert client.post(
            f"/api/v1/conversations/{conversation['id']}/confirm",
            json={"plan_version": unrelated["plan_version"], "plan_hash": unrelated["plan_hash"]},
        ).status_code == 409
        assert client.post(
            f"/api/v1/conversations/{conversation['id']}/execute",
            json={"plan_version": unrelated["plan_version"]},
        ).status_code == 409

        resumed = client.post(url, json={
            "content": "统计医疗费用", "base_plan_version": unrelated["plan_version"],
        }).json()["data"]
        assert resumed["status"] == "awaiting_confirmation"
        assert resumed["plan"]["metrics"] == ["fund_pay_total"]
        assert planner.create_calls == 3


def create_auth_test_client():
    db_path = Path("data") / f"test_auth_{uuid4().hex}.db"
    settings = Settings(
        system_database_url=f"sqlite+aiosqlite:///{db_path.resolve().as_posix()}",
        dashscope_api_key="test", sqlpilot_secret_key="test-auth-secret",
        sqlpilot_db_host="", sqlpilot_db_name="", sqlpilot_db_user="", sqlpilot_db_password="",
        auth_required=True, bootstrap_admin_username="admin", bootstrap_admin_password="Sqlpilot@123",
    )
    return TestClient(create_app(settings=settings, planner=FakePlanner()))


def test_authentication_and_user_conversation_isolation():
    with create_auth_test_client() as client:
        assert client.get("/api/v1/conversations").status_code == 401
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Sqlpilot@123"})
        assert login.status_code == 200
        admin_conversation = client.post("/api/v1/conversations", json={"title": "管理员查询"}).json()["data"]
        created_user = client.post("/api/v1/users", json={
            "username": "analyst1", "display_name": "分析员一", "password": "Analyst@123", "role": "analyst",
        })
        assert created_user.status_code == 200
        client.post("/api/v1/auth/logout")
        assert client.post("/api/v1/auth/login", json={"username": "analyst1", "password": "Analyst@123"}).status_code == 200
        assert client.get("/api/v1/conversations").json()["data"] == []
        assert client.get(f"/api/v1/conversations/{admin_conversation['id']}").status_code == 404
        assert client.get("/api/v1/users").status_code == 403


def test_multi_turn_clarify_confirm_and_execute():
    with create_test_client() as client:
        health = client.get("/api/v1/health").json()
        assert health["data"]["status"] == "ready"

        conversation = client.post("/api/v1/conversations", json={"title": "基金同比分析"}).json()["data"]
        first = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"content": "统计今年住院医保基金，找增长较高月份"},
        ).json()["data"]
        assert first["status"] == "clarifying"
        assert first["plan"]["clarifications"]
        assert first["assistant_message"].startswith("我已经初步理解了你的需求")

        revised = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"content": "所有机构和月份统一排名", "base_plan_version": first["plan_version"]},
        ).json()["data"]
        assert revised["status"] == "awaiting_confirmation"
        assert revised["plan_version"] == 2
        assert not revised["plan"]["clarifications"]
        assert revised["assistant_message"].startswith("已按你的补充更新查询计划")
        assert "当前最终需求是" in revised["assistant_message"]
        assert revised["assistant_message"].endswith("确认后我再生成并执行 SQL。")

        confirmed = client.post(
            f"/api/v1/conversations/{conversation['id']}/confirm",
            json={"plan_version": revised["plan_version"], "plan_hash": revised["plan_hash"]},
        )
        assert confirmed.status_code == 200

        executed = client.post(
            f"/api/v1/conversations/{conversation['id']}/execute",
            json={"plan_version": revised["plan_version"]},
        ).json()["data"]
        assert executed["status"] == "completed"
        assert "SELECT" in executed["sql"]

        detail = client.get(f"/api/v1/conversations/{conversation['id']}").json()["data"]
        assert len(detail["messages"]) == 4
        assert detail["current_plan"]["plan_version"] == 2
        assert detail["executions"][0]["status"] == "completed"
        assert detail["executions"][0]["rows"]
        assert detail["executions"][0]["result"]["rows"] == detail["executions"][0]["rows"]
        assert detail["executions"][0]["result"]["sql"] == executed["sql"]
        assert detail["executions"][0]["result"]["status"] == "completed"
        assert detail["status"] == "completed"

        history = client.get("/api/v1/conversations").json()["data"]
        assert history[0]["id"] == conversation["id"]
        assert history[0]["title"] == "基金同比分析"


def test_first_message_becomes_history_title_for_untitled_conversation():
    with create_test_client() as client:
        conversation = client.post("/api/v1/conversations", json={}).json()["data"]
        client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"content": "统计今年各医疗机构基金支付总额"},
        )
        history = client.get("/api/v1/conversations").json()["data"]
        assert history[0]["title"] == "统计今年各医疗机构基金支付总额"


def test_memory_is_governed_and_persisted():
    with create_test_client() as client:
        preference = client.put("/api/v1/memory/preferences", json={
            "key": "chart.preference", "value": "line", "enabled": True,
        })
        assert preference.status_code == 200
        assert client.get("/api/v1/memory/preferences").json()["data"][0]["value"] == "line"

        draft = client.put("/api/v1/memory/business", json={
            "key": "fund.total", "category": "metric_definition",
            "title": "基金支付总额", "content": "按有效结算记录求和", "status": "draft",
        }).json()["data"]
        assert draft["status"] == "draft"
        certified = client.put("/api/v1/memory/business", json={
            "key": "fund.total", "category": "metric_definition",
            "title": "基金支付总额", "content": "按有效结算记录求和", "status": "certified",
            "evidence": "业务负责人确认",
        }).json()["data"]
        assert certified["version"] == 2
        assert certified["status"] == "certified"
        rows = client.get("/api/v1/memory/business").json()["data"]
        assert rows[0]["evidence"] == "业务负责人确认"
        assert client.delete(f"/api/v1/memory/business/{certified['id']}").json()["data"]["deleted"]


def test_stale_plan_confirmation_is_rejected():
    with create_test_client() as client:
        cid = client.post("/api/v1/conversations", json={}).json()["data"]["id"]
        first = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "问题"}).json()["data"]
        second = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "补充", "base_plan_version": first["plan_version"]},
        ).json()["data"]
        response = client.post(
            f"/api/v1/conversations/{cid}/confirm",
            json={"plan_version": first["plan_version"], "plan_hash": first["plan_hash"]},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "VERSION_CONFLICT"


def test_conversation_is_isolated_by_tenant_and_user():
    with create_test_client() as client:
        created = client.post(
            "/api/v1/conversations",
            json={},
            headers={"X-Tenant-Id": "tenant-a", "X-User-Id": "user-a"},
        ).json()["data"]
        response = client.get(
            f"/api/v1/conversations/{created['id']}",
            headers={"X-Tenant-Id": "tenant-b", "X-User-Id": "user-a"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
