from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings
from app.planning.models import QueryPlanV1


NUMERIC_TYPES = {"currency", "number", "integer", "percent"}
TIME_TYPES = {"month", "date", "datetime"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, ValueError):
        return None


def build_chart_spec(
    rows: list[dict[str, Any]], result_schema: list[dict[str, Any]], max_points: int = 20
) -> dict[str, Any] | None:
    if not rows or not result_schema:
        return None
    dimensions = [item for item in result_schema if item.get("type") not in NUMERIC_TYPES]
    measures = [item for item in result_schema if item.get("type") in NUMERIC_TYPES]
    if not dimensions or not measures:
        return None
    category = dimensions[0]
    charts = []
    used: set[str] = set()
    base_measures = [
        item for item in measures
        if item.get("type") != "percent" and not item["key"].startswith(("prev_", "previous_"))
    ]
    for field in base_measures:
        previous = next((
            item for item in measures
            if item["key"] in {f"prev_{field['key']}", f"previous_{field['key']}"}
        ), None)
        if previous:
            charts.append(_build_single_chart(rows, category, [field, previous], max_points))
            used.update({field["key"], previous["key"]})
    remaining = [item for item in measures if item["key"] not in used and item.get("type") != "percent"]
    for family in ("currency", "integer", "number"):
        grouped = [item for item in remaining if item.get("type") == family]
        for index in range(0, len(grouped), 3):
            charts.append(_build_single_chart(rows, category, grouped[index:index + 3], max_points))
    rates = [item for item in measures if item.get("type") == "percent"]
    for index in range(0, len(rates), 3):
        chart = _build_single_chart(rows, category, rates[index:index + 3], max_points)
        if chart:
            chart["zero_baseline"] = True
            chart["title"] = "同比/环比增长率" if len(rates) > 1 else chart["title"]
            charts.append(chart)
    charts = [item for item in charts if item]
    if not charts:
        return None
    if len(charts) == 1:
        return charts[0]
    return {"type": "dashboard", "charts": charts}


def _build_single_chart(rows, category, series_fields, max_points):
    if not series_fields:
        return None
    candidates = []
    for row in rows:
        values = [_number(row.get(field["key"])) for field in series_fields]
        if all(value is None for value in values):
            continue
        candidates.append((str(row.get(category["key"], "未命名")), values))
    if not candidates:
        return None
    chart_type = "line" if category.get("type") in TIME_TYPES else "bar"
    if chart_type == "bar":
        candidates.sort(key=lambda item: item[1][0] if item[1][0] is not None else float("-inf"), reverse=True)
    visible = candidates[:max_points]
    return {
        "type": chart_type,
        "title": f"按{category['label']}查看{'、'.join(item['label'] for item in series_fields)}",
        "category": {"key": category["key"], "label": category["label"]},
        "categories": [item[0] for item in visible],
        "series": [
            {
                "key": field["key"],
                "label": field["label"],
                "unit": field.get("unit"),
                "values": [item[1][index] for item in visible],
            }
            for index, field in enumerate(series_fields)
        ],
        "displayed_points": len(visible),
        "total_points": len(candidates),
        "truncated": len(candidates) > len(visible),
    }


class ResultInterpreter:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self.settings = settings
        self.client = client or AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.sqlpilot_bailian_base_url,
            timeout=settings.planner_timeout_seconds,
            max_retries=1,
        )

    async def interpret(
        self,
        plan: QueryPlanV1,
        rows: list[dict[str, Any]],
        result_schema: list[dict[str, Any]],
        chart: dict[str, Any] | None,
        *,
        truncated: bool,
    ) -> dict[str, Any]:
        fallback = self._fallback(rows, chart, truncated)
        if not rows or not self.settings.dashscope_api_key:
            return fallback
        payload = {
            "confirmed_plan": plan.model_dump(mode="json", exclude={"provenance"}),
            "result_schema": result_schema,
            "row_count": len(rows),
            "rows": rows[:50],
            "chart": chart,
            "result_truncated": truncated,
        }
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.sqlpilot_bailian_model,
                temperature=0,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的数据分析助手。只能依据提供的查询结果陈述事实，禁止猜测业务原因或补造数据。"
                            "输出JSON：summary为1-2句总体结论；findings为最多4条重要发现；caveats为数据限制。"
                            "findings和caveats必须是字符串数组，不得输出对象；面向业务人员表达，不暴露表名、字段名或代码值。"
                            "若result_truncated为false，不得暗示结果中还有未列出的同口径记录。"
                            "金额、百分比和数量必须保留原单位；没有同期或时间序列时不得声称增长、下降或趋势。"
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
                ],
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
            summary = str(parsed.get("summary", "")).strip()
            findings = self._text_items(parsed.get("findings", []), 4)
            caveats = self._text_items(parsed.get("caveats", []), 3)
            if not summary:
                return fallback
            return {"summary": summary, "findings": findings, "caveats": caveats, "source": "bailian"}
        except Exception:
            return fallback

    @staticmethod
    def _text_items(items: Any, limit: int) -> list[str]:
        if not isinstance(items, list):
            return []
        normalized = []
        for item in items:
            if isinstance(item, dict):
                label = str(item.get("label", "")).strip()
                detail = str(item.get("detail") or item.get("text") or "").strip()
                text = f"{label}：{detail}" if label and detail else detail or label
            else:
                text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized[:limit]

    @staticmethod
    def _fallback(
        rows: list[dict[str, Any]], chart: dict[str, Any] | None, truncated: bool
    ) -> dict[str, Any]:
        if not rows:
            return {
                "summary": "当前查询条件下没有返回数据。",
                "findings": [],
                "caveats": ["可以检查时间范围、过滤条件或数据同步状态。"],
                "source": "system",
            }
        findings = []
        primary_chart = chart
        if chart and chart.get("type") == "dashboard":
            primary_chart = next((item for item in chart.get("charts", []) if item.get("series")), None)
        if primary_chart and primary_chart.get("categories") and primary_chart.get("series"):
            values = primary_chart["series"][0]["values"]
            valid = [(index, value) for index, value in enumerate(values) if value is not None]
            if valid:
                index, value = max(valid, key=lambda item: item[1])
                unit = primary_chart["series"][0].get("unit") or ""
                findings.append(
                    f"{primary_chart['categories'][index]}的{primary_chart['series'][0]['label']}最高，为{value:g}{unit}。"
                )
        caveats = []
        chart_truncated = chart and (
            chart.get("truncated")
            or any(item.get("truncated") for item in chart.get("charts", []))
        )
        if truncated or chart_truncated:
            caveats.append("结果或图表仅展示部分数据，结论应结合完整明细复核。")
        return {
            "summary": f"本次查询返回{len(rows)}条结果。",
            "findings": findings,
            "caveats": caveats,
            "source": "system",
        }
