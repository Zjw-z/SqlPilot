from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import expressions as exp

from app.benchmarks.spider import SpiderBenchmark
from app.benchmarks.spider_knowledge import SpiderKnowledgeAdapter
from app.schema_linking import link_fields
from tools.spider_generate import extract_sql, load_env, schema_prompt


def tokens(text: str) -> set[str]:
    raw = set(re.findall(r"[a-z0-9_]+", text.lower()))
    variants = set(raw)
    for token in raw:
        if len(token) > 4 and token.endswith("ies"):
            variants.add(token[:-3] + "y")
        elif len(token) > 3 and token.endswith("s"):
            variants.add(token[:-1])
    return variants


def table_documents(schema: dict[str, Any]) -> list[dict[str, Any]]:
    names = schema.get("table_names_original", [])
    friendly = schema.get("table_names", names)
    columns = schema.get("column_names_original", [])
    docs = [{"table": name, "text": f"{name} {friendly[i]}", "columns": []} for i, name in enumerate(names)]
    for table_index, column in columns:
        if table_index >= 0:
            docs[table_index]["columns"].append(column)
            docs[table_index]["text"] += " " + column
    return docs


def schema_neighbors(schema: dict[str, Any]) -> dict[str, set[str]]:
    names = schema.get("table_names_original", [])
    columns = schema.get("column_names_original", [])
    graph = {name: set() for name in names}
    for left_column, right_column in schema.get("foreign_keys", []):
        try:
            left_index, right_index = columns[left_column][0], columns[right_column][0]
            left, right = names[left_index], names[right_index]
        except (IndexError, TypeError):
            continue
        graph[left].add(right)
        graph[right].add(left)
    return graph


def retrieve_tables(question: str, schema: dict[str, Any], limit: int = 12) -> list[str]:
    query = tokens(question)
    ranked = []
    for doc in table_documents(schema):
        terms = tokens(doc["text"])
        overlap = len(query & terms)
        substring = sum(1 for q in query for term in terms
                        if min(len(q), len(term)) > 5 and (q in term or term in q))
        ranked.append((overlap * 3 + substring, doc["table"]))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    lexical = [table for score, table in ranked if score > 0]
    selected = lexical[:limit] or [table for _, table in ranked[:min(4, limit)]]
    # Graph expansion supplies bridge and dimension tables without flattening the whole schema.
    graph = schema_neighbors(schema)
    frontier = list(selected)
    while frontier and len(selected) < limit:
        table = frontier.pop(0)
        for neighbor in sorted(graph.get(table, set())):
            if neighbor not in selected:
                selected.append(neighbor)
                frontier.append(neighbor)
                if len(selected) >= limit:
                    break
    return selected


def rerank_retrieved_tables(question: str, schema: dict[str, Any], hits: list[Any],
                            limit: int = 12) -> list[str]:
    """Fuse field-level RAG, lexical table coverage and FK graph paths."""
    hit_scores: dict[str, float] = {}
    for hit in hits:
        hit_scores[hit.table_name] = max(hit_scores.get(hit.table_name, -1), float(hit.score))
    lexical = retrieve_tables(question, schema, limit=limit)
    lexical_rank = {table: index for index, table in enumerate(lexical)}
    names = schema.get("table_names_original", [])
    ranked = sorted(names, key=lambda table: (
        -hit_scores.get(table, -1), lexical_rank.get(table, 10_000), table.lower()
    ))
    direct = [table for table in ranked if table in hit_scores or table in lexical_rank][:max(2, limit - 3)]
    graph = schema_neighbors(schema)
    selected = list(direct)
    # Add one-hop bridges around the strongest tables; farther paths remain in
    # the relationship prompt but should not crowd out directly relevant tables.
    for table in list(direct[:6]):
        for neighbor in sorted(graph.get(table, set()), key=lambda value: (
            lexical_rank.get(value, 10_000), -hit_scores.get(value, -1), value.lower()
        )):
            if neighbor not in selected:
                selected.append(neighbor)
            if len(selected) >= limit:
                return selected
    return selected[:limit]


def chat(base_url: str, api_key: str, model: str, system: str, user: str, timeout: int = 90) -> str:
    data = json.dumps({"model": model, "temperature": 0, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user},
    ]}).encode("utf-8")
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=data, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"]


def parse_json(content: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.I | re.S)
    raw = fenced.group(1) if fenced else content
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("planner did not return JSON")
    return json.loads(raw[start:end + 1])


def parse_sql_candidates(content: str, limit: int = 3) -> list[str]:
    payload = parse_json(content)
    values = payload.get("sql_candidates") or ([payload["sql"]] if payload.get("sql") else [])
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        sql = str(value).strip().rstrip(";") if isinstance(value, str) else ""
        canonical = " ".join(sql.split()).lower()
        if sql and canonical not in seen:
            seen.add(canonical)
            result.append(sql)
        if len(result) >= limit:
            break
    if not result:
        raise ValueError("SQL generator did not return candidates")
    return result


def filtered_schema(schema: dict[str, Any], selected: list[str]) -> dict[str, Any]:
    names = schema.get("table_names_original", [])
    indexes = {index for index, name in enumerate(names) if name.lower() in {v.lower() for v in selected}}
    if not indexes:
        return schema
    # Keeping the original schema is safer for FK index integrity; prompt is filtered separately.
    result = dict(schema)
    result["_selected_indexes"] = sorted(indexes)
    return result


def selected_schema_prompt(schema: dict[str, Any], selected: list[str]) -> str:
    full = schema_prompt(schema).splitlines()
    lowered = {name.lower() for name in selected}
    tables = [line for line in full if line.startswith("TABLE ") and line.split(" ", 2)[1].lower() in lowered]
    joins = [line for line in full if " = " in line and any(f"{name.lower()}." in line.lower() for name in selected)]
    return "\n".join(tables + ["FOREIGN KEYS:"] + joins)


def validate_and_execute(database: Path, sql: str) -> list[tuple[Any, ...]]:
    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ValueError("only SELECT/WITH is allowed")
    forbidden = re.search(r"\b(insert|update|delete|drop|alter|create|attach|pragma|vacuum)\b", sql, re.I)
    if forbidden:
        raise ValueError(f"forbidden operation: {forbidden.group(1)}")
    uri = database.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=8) as connection:
        connection.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
        return connection.execute(sql).fetchall()


def dimension_evidence(database: Path, selected_tables: list[str], question: str,
                       max_columns: int = 12, max_values: int = 12) -> list[dict[str, Any]]:
    """Retrieve real categorical values without exposing whole tables to the model."""
    uri = database.resolve().as_uri() + "?mode=ro"
    evidence: list[dict[str, Any]] = []
    question_terms = tokens(question)
    normalized_question = re.sub(r"[^a-z0-9]", "", question.lower())
    with sqlite3.connect(uri, uri=True, timeout=8) as connection:
        connection.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
        connection.execute("PRAGMA query_only=ON")
        for table in selected_tables:
            safe_table = table.replace('"', '""')
            try:
                columns = connection.execute(f'PRAGMA table_info("{safe_table}")').fetchall()
            except sqlite3.Error:
                continue
            candidates = []
            for column in columns:
                name, data_type = str(column[1]), str(column[2] or "").lower()
                relevance = sum(term in name.lower() or name.lower() in term for term in question_terms if len(term) > 2)
                if any(kind in data_type for kind in ("char", "text", "clob")):
                    candidates.append((relevance, name))
            candidates.sort(key=lambda item: (-item[0], item[1]))
            for column_relevance, column in candidates[:max_columns]:
                safe_column = column.replace('"', '""')
                try:
                    rows = connection.execute(
                        f'SELECT DISTINCT "{safe_column}" FROM "{safe_table}" '
                        f'WHERE "{safe_column}" IS NOT NULL LIMIT {int(max_values)}'
                    ).fetchall()
                except sqlite3.Error:
                    continue
                values = [row[0] for row in rows if str(row[0]).strip()]
                value_relevance = any(
                    any(len(term) > 2 and (term in str(value).lower() or str(value).lower() in term)
                        for term in question_terms)
                    for value in values
                ) or any(
                    len(compact) > 2 and compact in normalized_question
                    for compact in (re.sub(r"[^a-z0-9]", "", str(value).lower()) for value in values)
                )
                if values and (value_relevance or column_relevance > 0):
                    evidence.append({"table": table, "column": column, "values": values})
    return evidence[:24]


def semantic_risks(question: str, sql: str) -> list[str]:
    q, normalized = question.lower(), " " + re.sub(r"\s+", " ", sql.lower()) + " "
    has_distinct = re.search(r"\bdistinct\b", normalized) is not None
    risks = []
    anti_membership = any(phrase in q for phrase in (
        "do not own", "does not own", "don't own", "without", "do not speak",
        "does not speak", "not have", "never", "none of", "not the official language",
    ))
    if anti_membership and (" != " in normalized or " <> " in normalized):
        risks.append("否定集合不能用行级!=代替；应使用NOT EXISTS、EXCEPT或反连接，避免实体同时拥有匹配和不匹配记录")
    if anti_membership and not any(token in normalized for token in (" not exists ", " except ", " not in ")):
        risks.append("查询表达了实体级不存在关系，但SQL没有反集合操作")
    if anti_membership and " except " in normalized:
        positive_arm = normalized.split(" except ", 1)[0]
        if " join " in positive_arm:
            risks.append("EXCEPT左侧全集不应先连接关系表，否则会遗漏从未建立关系的主体；左侧应直接来自主体表")
    if ("different" in q or "distinct" in q or "everybody" in q) and " join " in normalized and not has_distinct:
        risks.append("一对多连接可能产生重复实体，应核对是否需要DISTINCT")
    if any(phrase in q for phrase in ("how many different", "number of different", "how many unique", "number of unique")) \
            and not has_distinct:
        risks.append("问题要求统计不同/唯一实体，COUNT必须使用DISTINCT业务实体字段")
    greater_than_any = re.search(r"\b(greater|larger|more)\b.{0,50}\bthan any\b", q) is not None
    less_than_any = re.search(r"\b(less|smaller|lower)\b.{0,50}\bthan any\b", q) is not None
    if greater_than_any and " min(" in normalized:
        risks.append("自然语言greater/larger than any通常表示大于集合中所有成员，子查询应使用MAX而非MIN")
    if less_than_any and " max(" in normalized:
        risks.append("自然语言less/smaller than any通常表示小于集合中所有成员，子查询应使用MIN而非MAX")
    return list(dict.fromkeys(risks))


def plan_sql_risks(question: str, plan: dict[str, Any], sql: str) -> list[str]:
    """Check SQL against the confirmed semantic IR before execution."""
    risks = semantic_risks(question, sql)
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return risks + ["SQL无法解析，不能验证输出、聚合和去重语义"]
    top_select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    output_fields = [str(value) for value in plan.get("output_fields", []) if str(value).strip()]
    if top_select is not None and output_fields and len(top_select.expressions) != len(output_fields):
        risks.append(f"输出列数量应为{len(output_fields)}，当前SQL为{len(top_select.expressions)}；必须严格按计划投影")
    normalized_question = question.lower()
    explicit_unique = any(phrase in normalized_question for phrase in (
        "distinct", "different", "unique", "how many types", "number of types",
    ))
    plan_distinct = bool(plan.get("distinct_keys"))
    has_distinct = tree.find(exp.Distinct) is not None or any(
        isinstance(node, exp.Count) and node.find(exp.Distinct) is not None for node in tree.walk()
    )
    if (explicit_unique or plan_distinct) and not has_distinct:
        risks.append("问题或计划明确要求唯一实体，SQL缺少DISTINCT或COUNT(DISTINCT ...)语义")
    if has_distinct and not explicit_unique and not plan_distinct:
        risks.append("计划没有去重要求，不应仅因存在JOIN而防御性添加DISTINCT；这会改变结果重复语义")
    logical = str(plan.get("logical_operator", "and")).lower()
    sql_text = " " + re.sub(r"\s+", " ", sql.lower()) + " "
    if logical in {"intersect", "except", "union"} and f" {logical} " not in sql_text:
        risks.append(f"计划要求{logical.upper()}集合运算，但SQL没有实现对应集合结构")
    if logical == "not_exists" and not any(token in sql_text for token in (" not exists ", " not in ", " except ")):
        risks.append("计划要求实体级不存在关系，但SQL没有反连接或反集合结构")
    return list(dict.fromkeys(risks))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SQLPilot's complete logical pipeline on Spider")
    parser.add_argument("--dataset", type=Path, default=Path("data/benchmarks/spider-data/spider_data"))
    parser.add_argument("--input-predictions", type=Path, default=Path("data/benchmarks/work/predictions-stratified-20.jsonl"))
    parser.add_argument("--all-cases", action="store_true", help="run from the complete Spider split")
    parser.add_argument("--output", type=Path, default=Path("data/benchmarks/reports/spider-full-pipeline-20.json"))
    parser.add_argument("--max-repairs", type=int, default=3)
    parser.add_argument("--knowledge-dir", type=Path, default=Path("data/benchmarks/knowledge/spider"))
    parser.add_argument("--case-id", action="append", help="run only selected Spider case id; may be repeated")
    args = parser.parse_args()
    load_env(Path(".env"))
    api_key, model = os.getenv("DASHSCOPE_API_KEY", ""), os.getenv("SQLPILOT_BAILIAN_MODEL", "")
    base_url = os.getenv("SQLPILOT_BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not api_key or not model:
        raise SystemExit("Bailian model is not configured")
    benchmark = SpiderBenchmark(args.dataset)
    knowledge = SpiderKnowledgeAdapter(args.dataset, args.knowledge_dir)
    schemas = benchmark.load_schema()
    all_cases = benchmark.load_cases()
    if args.all_cases:
        cases = all_cases
    else:
        seed_predictions = benchmark.load_predictions(args.input_predictions)
        cases = [case for case in all_cases if case.case_id in seed_predictions]
    if args.case_id:
        selected_case_ids = set(args.case_id)
        cases = [case for case in cases if case.case_id in selected_case_ids]
    results = []
    for position, case in enumerate(cases, 1):
        started = time.perf_counter()
        events: list[dict[str, Any]] = []
        schema = schemas[case.db_id]
        database = benchmark.database_path(case.db_id)
        hits = knowledge.search(case.db_id, case.question, database, schema, limit=36)
        retrieved = rerank_retrieved_tables(case.question, schema, hits, limit=12)
        field_links = link_fields(case.question, [hit.as_dict() for hit in hits])
        events.append({"stage": "schema_rag", "namespace": f"spider:{case.db_id}",
                       "provider": "persistent_schema_knowledge", "tables": retrieved,
                       "hits": [hit.as_dict() for hit in hits[:12]]})
        events.append({"stage": "field_linking", "candidates": [item.model_dump() for item in field_links]})
        try:
            plan = parse_json(chat(base_url, api_key, model,
                "You are SQLPilot's query planner. Return strict JSON only. Do not write SQL. "
                "Preserve the exact requested output columns, entity grain, uniqueness, aggregation target, quantifiers, exclusions, and whether multiple conditions apply to the same entity. "
                "Use matched_value from FIELD LINK CANDIDATES exactly, including case and whitespace. Prefer one table that directly contains all requested attributes over an unnecessary join. "
                "A statement that an entity does not have an official language means absence of a matching official-language row, not presence of an unofficial row. "
                "Distinguish business concepts and labels from surrogate ID columns: when the user asks for different named types or categories, use the descriptive business field unless they explicitly ask for IDs.",
                "Create a query plan for the question using only candidate tables. JSON keys: "
                "intent, metrics, dimensions, filters, comparison, selected_tables, entity_grain, output_fields, "
                "output_expressions, aggregations, group_by, having, distinct_keys, ordering, limit, "
                "logical_operator, predicate_scopes, confidence, needs_clarification, clarification_question. "
                "output_fields must contain exactly one item for every user-requested result column; a measure used only to rank/sort (for example count in 'which year has most concerts') is not an output column unless the user asks to show it. aggregations must distinguish a stored aggregate column from AVG/SUM/COUNT computed over rows; distinct_keys must be empty unless uniqueness is requested or required by entity grain.\n"
                f"QUESTION: {case.question}\nFIELD LINK CANDIDATES:\n"
                f"{json.dumps([item.model_dump() for item in field_links], ensure_ascii=False)}\n"
                f"CANDIDATE SCHEMA:\n{selected_schema_prompt(schema, retrieved)}"))
            selected = [str(v) for v in plan.get("selected_tables", [])] or retrieved
            events.append({"stage": "plan_created", "plan": plan})
            if plan.get("needs_clarification"):
                events.append({"stage": "auto_confirmation", "decision": "benchmark_question_is_authoritative"})
            else:
                events.append({"stage": "auto_confirmation", "decision": "confirmed"})
            prompt_schema = selected_schema_prompt(schema, list(dict.fromkeys(selected + retrieved)))
            values = dimension_evidence(benchmark.database_path(case.db_id), list(dict.fromkeys(selected + retrieved)), case.question)
            events.append({"stage": "dimension_value_lookup", "evidence": values})
            sql = ""
            error = ""
            rows: list[tuple[Any, ...]] = []
            for attempt in range(args.max_repairs + 1):
                instruction = (
                    f"PLAN:\n{json.dumps(plan, ensure_ascii=False)}\nSCHEMA:\n{prompt_schema}\n"
                    f"FIELD LINK CANDIDATES:\n{json.dumps([item.model_dump() for item in field_links], ensure_ascii=False)}\n"
                    f"ACTUAL DIMENSION VALUES:\n{json.dumps(values, ensure_ascii=False)}\nQUESTION:\n{case.question}\n"
                    + (f"PREVIOUS SQL:\n{sql}\nVALIDATION ERROR:\n{error}\nRepair the SQL.\n" if error else "")
                    + 'Return JSON only: {"sql_candidates":["..."]}. Generate up to 3 semantically equivalent candidates, best first.'
                )
                candidates = parse_sql_candidates(chat(base_url, api_key, model,
                    "You are SQLPilot's SQL generator. Generate read-only SQLite SQL from the confirmed plan. Return strict JSON only. "
                    "Project exactly the attributes requested, no more and no fewer. Prefer a fact table's direct semantic column over an unnecessary dimension join. "
                    "Use DISTINCT only when the confirmed plan has distinct_keys or entity-grain uniqueness explicitly requires it; never add DISTINCT defensively just because a JOIN exists. "
                    "For entities satisfying both independent relationship conditions use INTERSECT, two EXISTS clauses, or GROUP BY with COUNT(DISTINCT condition); do not use a plain IN list. "
                    "For without/none/not-the-official-language use NOT EXISTS or a correct anti-set; an entity can have both official and unofficial rows. Use matched_value evidence exactly. In ordinary natural language, greater than any member means greater than all members (compare with MAX), and less than any member means less than all members (compare with MIN). "
                    "For different business types/categories, DISTINCT the descriptive business field rather than a surrogate ID unless IDs were explicitly requested.",
                    instruction))
                executable: list[tuple[int, int, str, list[tuple[Any, ...]], list[str]]] = []
                candidate_errors: list[str] = []
                for candidate_index, candidate_sql in enumerate(candidates):
                    try:
                        candidate_rows = validate_and_execute(benchmark.database_path(case.db_id), candidate_sql)
                        candidate_risks = plan_sql_risks(case.question, plan, candidate_sql)
                        executable.append((len(candidate_risks), candidate_index, candidate_sql,
                                           candidate_rows, candidate_risks))
                        events.append({"stage": "sql_candidate_validated", "attempt": attempt + 1,
                                       "candidate": candidate_index + 1, "risks": candidate_risks})
                    except (sqlite3.Error, ValueError) as exc:
                        candidate_errors.append(str(exc)[:500])
                        events.append({"stage": "sql_candidate_rejected", "attempt": attempt + 1,
                                       "candidate": candidate_index + 1, "error": str(exc)[:500]})
                if executable:
                    _, selected_index, sql, rows, _ = min(executable, key=lambda item: (item[0], item[1]))
                    events.append({"stage": "sql_candidate_selected", "attempt": attempt + 1,
                                   "candidate": selected_index + 1, "candidate_count": len(candidates),
                                   "selection": "fewest_semantic_risks_then_model_rank"})
                    events.append({"stage": "sql_validated", "attempt": attempt + 1})
                    break
                error = " | ".join(dict.fromkeys(candidate_errors))[:500]
                events.append({"stage": "sql_repair", "attempt": attempt + 1, "error": error})
            else:
                raise ValueError(f"repair limit exceeded: {error}")
            risks = plan_sql_risks(case.question, plan, sql)
            events.append({"stage": "semantic_validation", "risks": risks})
            for semantic_attempt in range(2):
                if not risks:
                    break
                repaired = extract_sql(chat(base_url, api_key, model,
                    "You are SQLPilot's SQL semantic safety reviewer. Repair the SQL only when the listed semantic risks apply. Return one read-only SQLite SQL query only. "
                    "Preserve the user's entity grain; for different named business concepts prefer the descriptive field over a surrogate ID unless the user requested IDs.",
                    f"QUESTION:\n{case.question}\nPLAN:\n{json.dumps(plan, ensure_ascii=False)}\nSCHEMA:\n{prompt_schema}\n"
                    f"ACTUAL DIMENSION VALUES:\n{json.dumps(values, ensure_ascii=False)}\nCURRENT SQL:\n{sql}\n"
                    f"SEMANTIC RISKS:\n" + "\n".join(f"- {risk}" for risk in risks)))
                rows = validate_and_execute(benchmark.database_path(case.db_id), repaired)
                sql = repaired
                events.append({"stage": "semantic_repair", "attempt": semantic_attempt + 1, "risks": risks})
                risks = plan_sql_risks(case.question, plan, sql)
                events.append({"stage": "semantic_revalidation", "attempt": semantic_attempt + 1, "risks": risks})
            gold_rows = SpiderBenchmark._execute(benchmark.database_path(case.db_id), case.gold_sql)
            matched = SpiderBenchmark._equivalent(gold_rows, rows)
            events.append({"stage": "result_verified", "matched": matched})
            status = "matched" if matched else "result_mismatch"
            results.append({"case_id": case.case_id, "db_id": case.db_id, "hardness": case.hardness,
                            "status": status, "matched": matched, "sql": sql, "events": events,
                            "elapsed_ms": int((time.perf_counter() - started) * 1000)})
        except Exception as exc:
            results.append({"case_id": case.case_id, "db_id": case.db_id, "hardness": case.hardness,
                            "status": "pipeline_error", "matched": False, "error": str(exc)[:500],
                            "events": events, "elapsed_ms": int((time.perf_counter() - started) * 1000)})
        print(f"[{position}/{len(cases)}] {case.case_id} {results[-1]['status']}", flush=True)
    matched = sum(bool(item["matched"]) for item in results)
    status_counts = Counter(item["status"] for item in results)
    by_hardness = {level: {"total": sum(item["hardness"] == level for item in results),
                           "matched": sum(item["hardness"] == level and item["matched"] for item in results)}
                   for level in ("easy", "medium", "hard", "extra")}
    report = {"benchmark": "spider-1.0", "mode": "sqlpilot_full_logical_pipeline", "model": model,
              "total": len(results), "matched": matched, "execution_accuracy": matched / len(results) if results else 0,
              "status_counts": dict(status_counts), "by_hardness": by_hardness, "cases": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FULL_PIPELINE_EX={report['execution_accuracy']:.2%} ({matched}/{len(results)})")
    print(f"report={args.output}")


if __name__ == "__main__":
    main()
