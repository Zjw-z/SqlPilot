from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_REPORT = Path("data/benchmarks/reports/spider-multicandidate-20260829-full-suite.json")
REPORTS = {
    "multicandidate-20260829": {"label": "确定性多候选版 · 全量评测（1034条）", "path": DEFAULT_REPORT},
    "optimized-20260829": {"label": "字段级混合RAG优化版 · 全量评测（1034条）", "path": Path("data/benchmarks/reports/spider-optimized-20260829-full-suite.json")},
    "nightly-20260828": {"label": "夜间全量评测 · 当前版本（1034条）", "path": Path("data/benchmarks/reports/spider-nightly-20260828-full.json")},
    "baseline": {"label": "Qwen3.7 Plus · 完整基线（1034条）", "path": Path("data/benchmarks/reports/spider-qwen37plus-full-suite.json")},
    "root-fix": {"label": "根因修复 · 原失败集回归（165条）", "path": Path("data/benchmarks/reports/spider-root-fix-failure-suite.json")},
    "schema-knowledge": {"label": "持久化Schema RAG · 剩余失败集（103条）", "path": Path("data/benchmarks/reports/spider-knowledge-rag-remaining-suite.json")},
}


def available_benchmark_runs() -> list[dict[str, Any]]:
    return [{"id": key, "label": value["label"], "available": value["path"].exists()}
            for key, value in REPORTS.items()]


def benchmark_report_path(run_id: str) -> Path:
    if run_id not in REPORTS:
        raise KeyError(run_id)
    return REPORTS[run_id]["path"]


def read_benchmark_report(path: Path = DEFAULT_REPORT, retries: int = 5) -> dict[str, Any]:
    """Read a report that may be replaced or rewritten by the benchmark runner."""
    error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload.get("cases"), list):
                raise ValueError("benchmark report has no cases list")
            return payload
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(0.05)
    raise RuntimeError(f"评测报告暂时不可读取：{error}") from error


def benchmark_dashboard_payload(path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    report = read_benchmark_report(path)
    analysis_path = path.with_name(path.stem.replace("-suite", "-analysis") + ".json")
    pipeline_metrics: dict[str, Any] = {}
    if analysis_path.exists():
        try:
            pipeline_metrics = json.loads(analysis_path.read_text(encoding="utf-8")).get("pipeline_metrics", {})
        except (OSError, json.JSONDecodeError):
            pipeline_metrics = {}
    completed = int(report.get("completed", 0))
    total = int(report.get("expected_total", 0))
    matched = int(report.get("matched", 0))
    cases = report.get("cases", [])
    elapsed_values = [int(case.get("elapsed_ms", 0)) for case in cases if case.get("elapsed_ms")]
    models = sorted({case.get("model") for case in cases if case.get("model")})
    if not models:
        case_dir = path.with_name(path.stem.replace("-suite", "-cases"))
        first_case = next(case_dir.glob("*.json"), None) if case_dir.is_dir() else None
        if first_case:
            try:
                model = json.loads(first_case.read_text(encoding="utf-8")).get("model")
                models = [model] if model else []
            except (OSError, json.JSONDecodeError):
                pass
    return {
        "benchmark": report.get("benchmark"),
        "mode": report.get("mode"),
        "model": models[0] if len(models) == 1 else ("、".join(models) if models else "未知"),
        "expected_total": total,
        "completed": completed,
        "remaining": max(total - completed, 0),
        "progress": completed / total if total else 0,
        "matched": matched,
        "execution_accuracy": matched / completed if completed else 0,
        "status_counts": report.get("status_counts", {}),
        "by_hardness": report.get("by_hardness", {}),
        "pipeline_metrics": pipeline_metrics,
        "average_elapsed_ms": round(sum(elapsed_values) / len(elapsed_values)) if elapsed_values else 0,
        "updated_at": path.stat().st_mtime,
        "cases": cases,
    }
