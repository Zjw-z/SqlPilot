from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from app.benchmarks.spider import SpiderBenchmark


class ErrorCircuitBreaker:
    def __init__(self, threshold: int = 5) -> None:
        self.threshold = threshold
        self.consecutive_errors = 0

    def observe(self, status: str) -> bool:
        self.consecutive_errors = self.consecutive_errors + 1 if status == "pipeline_error" else 0
        return self.consecutive_errors >= self.threshold


def load_case_report(path: Path) -> dict[str, Any] | None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        case = report["cases"][0] if report.get("cases") else None
        if case and report.get("model"):
            case.setdefault("model", report["model"])
        return case
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def aggregate(case_dir: Path, expected_ids: set[str]) -> dict[str, Any]:
    cases = []
    for path in case_dir.glob("*.json"):
        case = load_case_report(path)
        if case and case.get("case_id") in expected_ids:
            cases.append(case)
    cases.sort(key=lambda item: item["case_id"])
    matched = sum(bool(item.get("matched")) for item in cases)
    status = Counter(item.get("status", "unknown") for item in cases)
    by_hardness = {
        level: {"total": sum(item.get("hardness") == level for item in cases),
                "matched": sum(item.get("hardness") == level and item.get("matched") for item in cases)}
        for level in ("easy", "medium", "hard", "extra")
    }
    return {
        "benchmark": "spider-1.0", "mode": "sqlpilot_full_logical_pipeline",
        "expected_total": len(expected_ids), "completed": len(cases), "matched": matched,
        "execution_accuracy": matched / len(cases) if cases else 0,
        "status_counts": dict(status), "by_hardness": by_hardness, "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumable concurrent Spider full-suite runner")
    parser.add_argument("--dataset", type=Path, default=Path("data/benchmarks/spider-data/spider_data"))
    parser.add_argument("--case-dir", type=Path, default=Path("data/benchmarks/reports/spider-full-cases"))
    parser.add_argument("--report", type=Path, default=Path("data/benchmarks/reports/spider-full-suite.json"))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--case-id-file", type=Path, help="optional newline-delimited case IDs to evaluate")
    parser.add_argument("--error-circuit-threshold", type=int, default=5)
    args = parser.parse_args()
    cases = SpiderBenchmark(args.dataset).load_cases()[args.offset:]
    if args.case_id_file:
        requested = {line.strip() for line in args.case_id_file.read_text(encoding="utf-8").splitlines() if line.strip()}
        cases = [case for case in cases if case.case_id in requested]
    if args.limit is not None:
        cases = cases[:args.limit]
    expected_ids = {case.case_id for case in cases}
    args.case_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    pending = []
    for case in cases:
        path = args.case_dir / f"{case.case_id}.json"
        existing = load_case_report(path)
        if existing and (not args.retry_failures or existing.get("status") != "pipeline_error"):
            continue
        pending.append(case)
    lock = threading.Lock()
    started = time.time()

    def write_report(report: dict[str, Any]) -> None:
        temporary = args.report.with_suffix(args.report.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # On Windows the dashboard may briefly hold the current report open.
        # Keep atomic replacement, but tolerate that short-lived reader lock.
        last_error: PermissionError | None = None
        for attempt in range(30):
            try:
                temporary.replace(args.report)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(min(0.05 * (attempt + 1), 0.5))
        raise last_error or PermissionError(f"cannot replace report: {args.report}")

    def run(case_id: str) -> tuple[str, int, str]:
        output = args.case_dir / f"{case_id}.json"
        command = [sys.executable, "-m", "tools.spider_full_pipeline", "--dataset", str(args.dataset),
                   "--all-cases", "--case-id", case_id, "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        case = load_case_report(output)
        return case_id, result.returncode, case.get("status", "missing_report") if case else "missing_report"

    print(f"suite total={len(cases)} cached={len(cases)-len(pending)} pending={len(pending)} concurrency={args.concurrency}", flush=True)
    breaker = ErrorCircuitBreaker(max(1, args.error_circuit_threshold))
    pending_iterator = iter(pending)
    completed_now = 0
    circuit_open = False
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = {}
        for _ in range(min(args.concurrency, len(pending))):
            case = next(pending_iterator, None)
            if case:
                futures[executor.submit(run, case.case_id)] = case.case_id
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future, None)
                case_id, returncode, status = future.result()
                completed_now += 1
                if breaker.observe(status):
                    circuit_open = True
            index = completed_now
            with lock:
                report = aggregate(args.case_dir, expected_ids)
                write_report(report)
                elapsed = max(time.time() - started, 1)
                rate = index / elapsed * 60
                remaining = (len(pending) - index) / rate if rate else 0
                print(f"[{index}/{len(pending)}] {case_id} {status} rc={returncode} "
                      f"EX={report['execution_accuracy']:.2%} rate={rate:.1f}/min eta={remaining:.1f}min", flush=True)
            if circuit_open:
                print(f"CIRCUIT_OPEN after {breaker.consecutive_errors} consecutive pipeline errors; "
                      "remaining cases were not submitted. Check model quota/configuration and resume with --retry-failures.", flush=True)
                break
            for _ in range(len(done)):
                case = next(pending_iterator, None)
                if case:
                    futures[executor.submit(run, case.case_id)] = case.case_id
        if circuit_open:
            for future in futures:
                future.cancel()
    report = aggregate(args.case_dir, expected_ids)
    write_report(report)
    print(f"FULL_SUITE_EX={report['execution_accuracy']:.2%} ({report['matched']}/{report['completed']}) circuit_open={circuit_open}", flush=True)


if __name__ == "__main__":
    main()
