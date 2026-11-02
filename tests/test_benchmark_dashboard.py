import json

from app.benchmark_dashboard import (
    available_benchmark_runs,
    benchmark_dashboard_payload,
    benchmark_report_path,
    read_benchmark_report,
)


def test_dashboard_payload_uses_completed_as_accuracy_denominator(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "benchmark": "spider-1.0", "mode": "full", "expected_total": 10,
        "completed": 2, "matched": 1, "status_counts": {"matched": 1, "result_mismatch": 1},
        "by_hardness": {"easy": {"total": 2, "matched": 1}},
        "cases": [{"case_id": "a", "model": "qwen", "elapsed_ms": 100}, {"case_id": "b", "model": "qwen", "elapsed_ms": 300}],
    }), encoding="utf-8")
    result = benchmark_dashboard_payload(path)
    assert result["progress"] == .2
    assert result["execution_accuracy"] == .5
    assert result["remaining"] == 8
    assert result["average_elapsed_ms"] == 200


def test_report_reader_rejects_incomplete_json(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"cases":', encoding="utf-8")
    try:
        read_benchmark_report(path, retries=1)
    except RuntimeError as exc:
        assert "暂时不可读取" in str(exc)
    else:
        raise AssertionError("incomplete JSON must not be accepted")


def test_dashboard_exposes_baseline_and_root_fix_runs():
    runs = {item["id"]: item for item in available_benchmark_runs()}
    assert "baseline" in runs
    assert "root-fix" in runs
    assert "schema-knowledge" in runs
    assert benchmark_report_path("root-fix").name == "spider-root-fix-failure-suite.json"
