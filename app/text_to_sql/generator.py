from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.errors import PlannerError
from app.planning.models import QueryPlanV1
from app.text_to_sql.schema import SchemaContext


SQL_SYSTEM_PROMPT = """你是PostgreSQL医疗数据查询专家。只返回JSON对象 {"sql_candidates":["...", "..."]}。
只能使用提供的Schema，禁止猜测表或字段，禁止任何写操作。
业务字段优先使用查询计划semantic_bindings；没有绑定时才根据候选Schema的字段注释判断，禁止依赖固定表名。
查询计划metrics中的每一个指标都必须生成对应结果列，不得只选择第一个指标。
WHERE条件必须显式包含查询计划date_range中的起止日期，不得用CURRENT_DATE改写计划范围。
时间戳字段的结束边界必须使用“小于结束日期次日零点”的半开区间，禁止使用<=当天23:59:59，以免遗漏毫秒或微秒数据；纯date字段可以使用<=结束日期。
comparison.type=none时禁止查询同期数据或生成任何同比/环比列；只有计划明确要求时才能计算对比指标。
码值、有效标识和撤销标识只有在Schema注释或查询计划中有明确证据时才能使用，禁止对未知数据源套用医保演示库编码。
日期字段的实际类型和格式以提供的Schema注释为准，不得凭空假设；按自然日、ISO周、自然月、自然季度或自然年统计时，使用与comparison.grain一致的日期截断口径。
同比必须查询当前期和上年同期。day/month/quarter/year按相同自然周期连接；week按相同ISO周编号和相邻ISO年连接；comparison.grain=period_total时分别汇总两个期间后计算，不得擅自增加时间维度。
环比必须按comparison.grain计算上一自然日、ISO周、自然月、自然季度或自然年；为了计算首个展示周期，应额外读取前一周期，但不得把该辅助周期输出给用户。
同比百分比公式必须是ROUND((当前值-同期值)*100.0/NULLIF(同期值,0),2)，只能对分母使用NULLIF，零增长必须返回0。
只有ranking明确要求时才排序；如果排序指标是yoy_rate，ORDER BY必须包含yoy_rate及计划方向。仅计算同比增长率时不得擅自排序。
ranking.scope=within_dimension时，必须对ranking.partition_by列出的每个维度使用PARTITION BY进行分组排名，并在每组内取ranking.limit项；不能只用全局LIMIT。within_institution时必须按institution分组排名。
必须使用schema限定表名；结果列使用易懂英文别名；最多返回500行。禁止SELECT *。"""


class BailianSqlGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.sqlpilot_bailian_base_url,
            timeout=settings.planner_timeout_seconds,
            max_retries=settings.planner_max_retries,
        )

    async def generate_candidates(self, plan: QueryPlanV1, context: SchemaContext, correction: str | None = None) -> list[str]:
        content = (
            "已确认的查询计划：\n" + plan.model_dump_json(exclude={"provenance"})
            + "\n候选Schema：\n" + context.prompt_text()
        )
        if correction:
            content += f"\n上一次SQL校验失败，请纠正：{correction}"
        content += (
            f"\n请生成1至{self.settings.sql_candidate_count}个语义等价的候选SQL，最可靠的放在第一个。"
            "候选可以采用不同的安全连接或子查询方式，但不得改变已确认计划语义。"
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.sqlpilot_bailian_model,
                messages=[{"role": "system", "content": SQL_SYSTEM_PROMPT}, {"role": "user", "content": content}],
                temperature=0,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            raw_candidates = payload.get("sql_candidates") or ([payload["sql"]] if payload.get("sql") else [])
            candidates = self._normalize_candidates(raw_candidates, self.settings.sql_candidate_count)
            if not candidates:
                raise ValueError("missing sql")
            return candidates
        except Exception as exc:
            raise PlannerError("SQL_GENERATION_FAILED", f"SQL生成失败：{type(exc).__name__}", True) from exc

    async def generate(self, plan: QueryPlanV1, context: SchemaContext, correction: str | None = None) -> str:
        """兼容旧调用方；新执行引擎使用 generate_candidates 进行确定性筛选。"""
        return (await self.generate_candidates(plan, context, correction))[0]

    @staticmethod
    def _normalize_candidates(values: object, limit: int) -> list[str]:
        if not isinstance(values, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            sql = str(value).strip().rstrip(";") if isinstance(value, str) else ""
            canonical = " ".join(sql.split()).lower()
            if sql and canonical not in seen:
                seen.add(canonical)
                result.append(sql)
            if len(result) >= limit:
                break
        return result
