from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.benchmarks.spider import SpiderBenchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLPilot Spider 1.0 benchmark harness")
    parser.add_argument("--dataset", type=Path, default=Path("data/benchmarks/spider-official"))
    parser.add_argument("--split", default="dev")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--oracle-smoke", action="store_true", help="use gold SQL to verify the evaluator")
    parser.add_argument("--export-cases", type=Path)
    parser.add_argument("--report", type=Path, default=Path("data/benchmarks/reports/spider-dev.json"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only-predicted", action="store_true")
    args = parser.parse_args()
    benchmark = SpiderBenchmark(args.dataset)
    readiness = benchmark.readiness(args.split)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    if args.export_cases:
        args.export_cases.parent.mkdir(parents=True, exist_ok=True)
        benchmark.write_cases(args.export_cases, benchmark.load_cases(args.split)[:args.limit])
    if not args.predictions and not args.oracle_smoke:
        return
    predictions = ({case.case_id: case.gold_sql for case in benchmark.load_cases(args.split)}
                   if args.oracle_smoke else benchmark.load_predictions(args.predictions))
    report = benchmark.evaluate(predictions, args.split, args.limit, args.only_predicted)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EX={report.execution_accuracy:.2%} ({report.execution_matches}/{report.evaluated})")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
