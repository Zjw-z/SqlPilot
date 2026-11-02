from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.benchmarks.spider import SpiderBenchmark
from app.benchmarks.spider_knowledge import SpiderKnowledgeAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Build isolated Schema knowledge indexes for Spider databases")
    parser.add_argument("--dataset", type=Path, default=Path("data/benchmarks/spider-data/spider_data"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/benchmarks/knowledge/spider"))
    parser.add_argument("--db-id", action="append", help="build selected database; may be repeated")
    args = parser.parse_args()
    benchmark = SpiderBenchmark(args.dataset)
    schemas = benchmark.load_schema()
    selected = args.db_id or sorted(schemas)
    adapter = SpiderKnowledgeAdapter(args.dataset, args.index_dir)
    summaries = []
    for position, db_id in enumerate(selected, 1):
        if db_id not in schemas:
            raise SystemExit(f"unknown Spider db_id: {db_id}")
        summary = adapter.build(db_id, benchmark.database_path(db_id), schemas[db_id])
        summaries.append(summary)
        print(f'[{position}/{len(selected)}] {db_id} {summary["document_count"]} documents', flush=True)
    print(json.dumps({"database_count": len(summaries),
                      "document_count": sum(item["document_count"] for item in summaries),
                      "index_dir": str(args.index_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
