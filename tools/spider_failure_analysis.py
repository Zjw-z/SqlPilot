from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import expressions as exp

from app.benchmarks.spider import SpiderBenchmark


def parse(sql: str) -> exp.Expression | None:
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return None


def features(sql: str) -> dict[str, Any]:
    tree = parse(sql)
    if tree is None:
        return {"parse_error": True, "tables": [], "columns": []}
    return {
        "parse_error": False,
        "tables": sorted({node.name.lower() for node in tree.find_all(exp.Table)}),
        "columns": sorted({node.name.lower() for node in tree.find_all(exp.Column)}),
        "joins": sum(1 for _ in tree.find_all(exp.Join)),
        "aggregates": sorted(type(node).__name__.lower() for node in tree.walk() if isinstance(node, exp.AggFunc)),
        "has_where": tree.find(exp.Where) is not None,
        "has_group": tree.find(exp.Group) is not None,
        "has_having": tree.find(exp.Having) is not None,
        "has_order": tree.find(exp.Order) is not None,
        "has_limit": tree.find(exp.Limit) is not None,
        "has_distinct": tree.find(exp.Distinct) is not None,
        "has_subquery": tree.find(exp.Subquery) is not None,
        "set_operations": sorted(type(node).__name__.lower() for node in tree.walk()
                                 if isinstance(node, (exp.Union, exp.Intersect, exp.Except))),
        "projection_count": len(tree.expressions) if isinstance(tree, exp.Select) else None,
    }


def event(case: dict[str, Any], stage: str) -> dict[str, Any]:
    return next((item for item in case.get("events", []) if item.get("stage") == stage), {})


def classify(case: dict[str, Any], gold_sql: str) -> tuple[str, list[str]]:
    gold, predicted = features(gold_sql), features(case.get("sql", ""))
    if predicted.get("parse_error"):
        return "sql_parse", ["生成SQL无法解析"]
    gold_tables, predicted_tables = set(gold["tables"]), set(predicted["tables"])
    retrieved = {str(v).lower() for v in event(case, "schema_rag").get("tables", [])}
    selected = {str(v).lower() for v in event(case, "plan_created").get("plan", {}).get("selected_tables", [])}
    missing_retrieval = sorted(gold_tables - retrieved - predicted_tables)
    if missing_retrieval:
        return "schema_retrieval", [f"RAG未召回：{', '.join(missing_retrieval)}"]
    missing_plan = sorted(gold_tables - selected - predicted_tables)
    if missing_plan:
        return "query_plan_tables", [f"计划未选择：{', '.join(missing_plan)}"]
    if gold_tables != predicted_tables:
        return "sql_table_selection", [f"标准表={sorted(gold_tables)}", f"生成表={sorted(predicted_tables)}"]
    comparisons = [
        ("set_operation", "set_operations", "集合运算不一致"),
        ("aggregation", "aggregates", "聚合函数不一致"),
        ("join", "joins", "连接数量不一致"),
        ("filter", "has_where", "过滤条件结构不一致"),
        ("grouping", "has_group", "分组结构不一致"),
        ("having", "has_having", "HAVING结构不一致"),
        ("ordering_limit", "has_order", "排序结构不一致"),
        ("ordering_limit", "has_limit", "结果范围不一致"),
        ("distinct", "has_distinct", "去重结构不一致"),
        ("subquery", "has_subquery", "子查询结构不一致"),
        ("projection", "projection_count", "输出列数量不一致"),
    ]
    for category, key, message in comparisons:
        if gold.get(key) != predicted.get(key):
            return category, [message, f"标准={gold.get(key)}", f"生成={predicted.get(key)}"]
    if set(gold["columns"]) != set(predicted["columns"]):
        return "column_semantics", ["使用字段不一致"]
    return "expression_semantics", ["SQL结构相近，但表达式、常量或逻辑组合不一致"]


def pipeline_metrics(results: list[dict[str, Any]], sources: dict[str, Any]) -> dict[str, Any]:
    """分层评估召回、计划、校验、执行和结果，避免用单一EX掩盖根因。"""
    counters = Counter(total=len(results))
    for result in results:
        source = sources.get(result.get("case_id"))
        if source is None:
            continue
        gold_tables = set(features(source.gold_sql).get("tables", []))
        retrieved = {str(value).lower() for value in event(result, "schema_rag").get("tables", [])}
        selected = {str(value).lower() for value in event(result, "plan_created").get("plan", {}).get("selected_tables", [])}
        if gold_tables.issubset(retrieved):
            counters["schema_recall"] += 1
        if gold_tables.issubset(selected):
            counters["plan_table_recall"] += 1
        validated = event(result, "sql_validated")
        if validated or result.get("status") in {"matched", "result_mismatch"}:
            counters["sql_validated"] += 1
        semantic = event(result, "semantic_validation")
        if semantic and not semantic.get("risks"):
            counters["semantic_validation"] += 1
        if result.get("status") in {"matched", "result_mismatch"}:
            counters["executed"] += 1
        if result.get("matched"):
            counters["result_matched"] += 1
    total = max(1, counters["total"])
    return {
        key: {"passed": counters[key], "total": counters["total"],
              "rate": round(counters[key] * 100 / total, 2)}
        for key in ("schema_recall", "plan_table_recall", "sql_validated",
                    "semantic_validation", "executed", "result_matched")
    }


def analyze(report_path: Path, dataset: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    benchmark = SpiderBenchmark(dataset)
    cases = {case.case_id: case for case in benchmark.load_cases()}
    failures, categories, databases = [], Counter(), defaultdict(Counter)
    for result in report.get("cases", []):
        if result.get("status") != "result_mismatch":
            continue
        source = cases[result["case_id"]]
        category, reasons = classify(result, source.gold_sql)
        categories[category] += 1
        databases[source.db_id][category] += 1
        failures.append({
            "case_id": source.case_id, "db_id": source.db_id, "hardness": source.hardness,
            "category": category, "reasons": reasons, "question": source.question,
            "gold_sql": source.gold_sql, "predicted_sql": result.get("sql", ""),
        })
    return {
        "source_report": str(report_path), "failure_total": len(failures),
        "pipeline_metrics": pipeline_metrics(report.get("cases", []), cases),
        "categories": dict(categories.most_common()),
        "databases": {name: dict(counts.most_common()) for name, counts in
                      sorted(databases.items(), key=lambda item: -sum(item[1].values()))},
        "failures": failures,
    }


def markdown(analysis: dict[str, Any]) -> str:
    lines = ["# Spider 失败根因分析", "", f"失败总数：{analysis['failure_total']}", "", "## 根因分布", ""]
    lines += [f"- {name}: {count}" for name, count in analysis["categories"].items()]
    lines += ["", "## 失败最多的数据库", ""]
    for db_id, counts in list(analysis["databases"].items())[:15]:
        lines.append(f"- {db_id}: {sum(counts.values())}（" + "、".join(f"{k} {v}" for k, v in counts.items()) + "）")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("data/benchmarks/reports/spider-qwen37plus-full-suite.json"))
    parser.add_argument("--dataset", type=Path, default=Path("data/benchmarks/spider-data/spider_data"))
    parser.add_argument("--output", type=Path, default=Path("data/benchmarks/reports/spider-qwen37plus-failure-analysis.json"))
    parser.add_argument("--case-id-output", type=Path, help="optional newline-delimited mismatch case IDs")
    args = parser.parse_args()
    result = analyze(args.report, args.dataset)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(result), encoding="utf-8")
    if args.case_id_output:
        args.case_id_output.write_text("\n".join(item["case_id"] for item in result["failures"]) + "\n", encoding="utf-8")
    print(json.dumps({"failure_total": result["failure_total"], "categories": result["categories"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
