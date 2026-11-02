from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.benchmarks.spider import SpiderBenchmark


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def schema_prompt(schema: dict[str, Any]) -> str:
    table_names = schema.get("table_names_original") or schema.get("table_names", [])
    columns = schema.get("column_names_original") or schema.get("column_names", [])
    types = schema.get("column_types", [])
    by_table: dict[int, list[str]] = {index: [] for index in range(len(table_names))}
    for index, (table_index, column_name) in enumerate(columns):
        if table_index < 0:
            continue
        column_type = types[index] if index < len(types) else "text"
        by_table[table_index].append(f"{column_name} {column_type}")
    foreign_keys = []
    for left, right in schema.get("foreign_keys", []):
        lt, lc = columns[left]
        rt, rc = columns[right]
        foreign_keys.append(f"{table_names[lt]}.{lc} = {table_names[rt]}.{rc}")
    tables = "\n".join(f"TABLE {name} ({', '.join(by_table[index])})" for index, name in enumerate(table_names))
    joins = "\n".join(foreign_keys) or "none"
    return f"{tables}\nFOREIGN KEYS:\n{joins}"


def extract_sql(content: str) -> str:
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", content, re.I | re.S)
    sql = fenced.group(1) if fenced else content
    match = re.search(r"\b(SELECT|WITH)\b.*", sql.strip(), re.I | re.S)
    if not match:
        raise ValueError("model did not return read-only SQL")
    return match.group(0).strip().rstrip(";")


def call_model(base_url: str, api_key: str, model: str, question: str, schema: str, timeout: int) -> str:
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You are a Text-to-SQL compiler. Generate exactly one read-only SQLite query. Use only the supplied schema. Return SQL only, without explanation."},
            {"role": "user", "content": f"DATABASE SCHEMA:\n{schema}\n\nQUESTION:\n{question}\n\nSQL:"},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return extract_sql(payload["choices"][0]["message"]["content"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Spider predictions with SQLPilot's configured Bailian model")
    parser.add_argument("--dataset", type=Path, default=Path("data/benchmarks/spider-data/spider_data"))
    parser.add_argument("--output", type=Path, default=Path("data/benchmarks/work/predictions.jsonl"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--stratified", action="store_true", help="sample evenly across inferred hardness levels")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    load_env(Path(".env"))
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    base_url = os.getenv("SQLPILOT_BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("SQLPILOT_BAILIAN_MODEL", "")
    if not api_key or not model:
        raise SystemExit("DASHSCOPE_API_KEY or SQLPILOT_BAILIAN_MODEL is not configured")
    benchmark = SpiderBenchmark(args.dataset)
    schemas = benchmark.load_schema()
    all_cases = benchmark.load_cases()
    if args.stratified:
        rng = random.Random(20260828)
        groups = {level: [] for level in ("easy", "medium", "hard", "extra")}
        for case in all_cases:
            groups[case.hardness].append(case)
        per_level = max(1, args.limit // len(groups))
        cases = []
        for level in groups:
            rng.shuffle(groups[level])
            cases.extend(groups[level][:per_level])
        cases = cases[:args.limit]
    else:
        cases = all_cases[args.offset:args.offset + args.limit]
    existing: dict[str, str] = {}
    if args.output.exists():
        existing = benchmark.load_predictions(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as output:
        for index, case in enumerate(cases, 1):
            if case.case_id in existing:
                print(f"[{index}/{len(cases)}] {case.case_id} cached", flush=True)
                continue
            started = time.perf_counter()
            try:
                sql = call_model(base_url, api_key, model, case.question, schema_prompt(schemas[case.db_id]), args.timeout)
                row = {"case_id": case.case_id, "db_id": case.db_id, "sql": sql, "model": model}
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                print(f"[{index}/{len(cases)}] {case.case_id} {int((time.perf_counter()-started)*1000)}ms", flush=True)
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
                row = {"case_id": case.case_id, "db_id": case.db_id, "sql": "", "model": model, "error": str(exc)[:500]}
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                print(f"[{index}/{len(cases)}] {case.case_id} ERROR {exc}", flush=True)


if __name__ == "__main__":
    main()
