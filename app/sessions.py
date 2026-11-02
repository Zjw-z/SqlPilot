from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.catalog import DIMENSIONS, METRICS
from app.domain import QueryPlan


class SessionError(ValueError):
    pass


@dataclass
class PlanSession:
    session_id: str
    version: int
    plan: QueryPlan
    status: str = "awaiting_confirmation"
    confirmed_version: int | None = None
    confirmed_at: str | None = None

    @property
    def plan_hash(self) -> str:
        canonical = json.dumps(self.plan.public_dict(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def response(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "version": self.version,
            "plan_hash": self.plan_hash,
            "status": self.status,
            "plan": self.plan.public_dict(),
            "summary": summarize(self.plan),
        }


def summarize(plan: QueryPlan) -> str:
    metric = plan.metric.name if plan.metric else "尚未确定的指标"
    dimension_names = [item.name.replace("结算月份", "月份") for item in plan.dimensions]
    dimensions = "、".join(dimension_names) or "总体"
    if plan.start_date and plan.end_date:
        start_year = plan.start_date[:4]
        if plan.start_date.endswith("01-01") and plan.end_date == f"{start_year}-12-31":
            period = f"{start_year}年度"
        elif plan.start_date == f"{start_year}-01-01" and plan.end_date.startswith(start_year):
            month, day = int(plan.end_date[5:7]), int(plan.end_date[8:10])
            period = f"{start_year}年1月1日至{month}月{day}日"
        else:
            period = f"{plan.start_date}至{plan.end_date}"
    else:
        period = "全部可用时间范围内"
    clauses = []
    if plan.institution_level:
        clauses.append(f"医院范围仅限{plan.institution_level}")
    if plan.medical_type == "inpatient":
        clauses.append("就医类型仅统计住院结算")
    if plan.comparison == "mom":
        clauses.append("同时计算与上月相比的环比变化")
    elif plan.comparison == "yoy":
        clauses.append("同时与上年同期进行同比")
    if plan.order_by == "growth":
        clauses.append("结果按同比增长率从高到低排列，以找出增长较高的月份")
    if plan.top_n:
        clauses.append(f"只显示前{plan.top_n}项")
    detail = "。".join(clauses) + "。" if clauses else ""
    return f"我理解你的需求是：统计{period}各{dimensions}的{metric}。{detail}统计时仅包含有效结算，并排除已经撤销的记录。"


class SessionStore:
    def __init__(self) -> None:
        self._items: dict[str, PlanSession] = {}
        self._lock = threading.Lock()

    def create(self, plan: QueryPlan) -> PlanSession:
        session = PlanSession(str(uuid.uuid4()), 1, plan)
        with self._lock:
            self._items[session.session_id] = session
        return session

    def get(self, session_id: str) -> PlanSession:
        try:
            return self._items[session_id]
        except KeyError as exc:
            raise SessionError("查询会话不存在或已失效") from exc

    def update(self, session_id: str, base_version: int, changes: dict[str, Any]) -> PlanSession:
        with self._lock:
            session = self.get(session_id)
            if session.version != base_version:
                raise SessionError("查询计划已发生变化，请刷新后重新修改")
            plan = session.plan
            if "metric_key" in changes:
                plan.metric = next((item for item in METRICS if item.key == changes["metric_key"]), None)
                if plan.metric is None:
                    raise SessionError("所选指标不在认证指标目录中")
                plan.clarifications = [item for item in plan.clarifications if item.get("id") != "metric"]
            if "dimension_keys" in changes:
                keys = set(changes["dimension_keys"])
                plan.dimensions = [item for item in DIMENSIONS if item.key in keys]
            for key in ("start_date", "end_date", "institution_level", "top_n", "comparison", "medical_type", "order_by", "ranking_scope"):
                if key in changes:
                    setattr(plan, key, changes[key])
            if "ranking_scope" in changes:
                plan.clarifications = [item for item in plan.clarifications if item.get("id") != "ranking_scope"]
            plan.ambiguities = [item.get("question", "需要补充信息") for item in plan.clarifications]
            session.version += 1
            session.status = "awaiting_confirmation"
            session.confirmed_version = None
            session.confirmed_at = None
            return session

    def confirm(self, session_id: str, version: int, plan_hash: str) -> PlanSession:
        with self._lock:
            session = self.get(session_id)
            if session.version != version or session.plan_hash != plan_hash:
                raise SessionError("查询计划已发生变化，请重新确认当前版本")
            if session.plan.metric is None or session.plan.ambiguities:
                raise SessionError("查询计划仍有未确认内容，请先调整后再执行")
            session.status = "confirmed"
            session.confirmed_version = version
            session.confirmed_at = datetime.now(timezone.utc).isoformat()
            return session
