from __future__ import annotations

import re
from typing import Any

from app.planning.models import FieldCandidate, QueryPlanV1


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower()))


def link_fields(question: str, schema_context: list[dict[str, Any]],
                plan: QueryPlanV1 | None = None, limit: int = 16) -> list[FieldCandidate]:
    """Produce auditable field candidates before SQL generation.

    It never invents a field: candidates must be column documents returned by
    the active Schema knowledge namespace.
    """
    query_terms = _terms(question)
    lower_question = question.lower()
    asks_identifier = bool(re.search(r"\b(id|ids|identifier|code|codes)\b|编号|编码|代码", lower_question))
    asks_label = any(term in lower_question for term in ("name", "title", "description", "type", "名称", "姓名", "类型", "描述"))
    selected = {item.object_key for item in plan.semantic_bindings} if plan else set()
    candidates: list[FieldCandidate] = []
    for item in schema_context:
        if item.get("object_type") != "column" or not item.get("column_name"):
            continue
        metadata = item.get("metadata") or {}
        values = metadata.get("sample_values") or metadata.get("values") or []
        matched_value = next(
            (value for value in values if str(value).strip() and str(value).strip().lower() in lower_question), None
        )
        value_match = matched_value is not None
        text = " ".join(str(item.get(key, "")) for key in (
            "business_name", "column_name", "content",
        ))
        overlap = len(query_terms & _terms(text)) / max(1, len(query_terms))
        column_name = str(item.get("column_name", "")).lower()
        identifier_penalty = .12 if asks_label and not asks_identifier and (
            column_name.endswith("_id") or column_name.endswith("id")
        ) else 0
        score = min(1.0, float(item.get("score", 0)) * .65 + overlap * .25
                    + (.25 if value_match else 0) - identifier_penalty)
        candidates.append(FieldCandidate(
            mention=next((str(value) for value in values if str(value).lower() in question.lower()),
                         item.get("business_name") or item.get("column_name") or ""),
            object_key=item["object_key"], schema_name=item.get("schema_name", ""),
            table_name=item.get("table_name", ""), column_name=item.get("column_name", ""),
            business_name=item.get("business_name", ""), score=round(score, 4),
            value_match=value_match, matched_value=matched_value,
            selected=item["object_key"] in selected,
        ))
    candidates.sort(key=lambda value: (-int(value.selected), -int(value.value_match), -value.score, value.object_key))
    return candidates[:limit]
