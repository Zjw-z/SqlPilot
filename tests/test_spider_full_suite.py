import json

from tools.spider_full_suite import ErrorCircuitBreaker, aggregate, load_case_report


def test_full_suite_aggregation_is_resumable(tmp_path):
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    payload = {"cases": [{"case_id": "dev-0000", "hardness": "easy", "status": "matched", "matched": True}]}
    path = case_dir / "dev-0000.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_case_report(path)["matched"] is True
    report = aggregate(case_dir, {"dev-0000", "dev-0001"})
    assert report["expected_total"] == 2
    assert report["completed"] == 1
    assert report["execution_accuracy"] == 1.0


def test_error_circuit_breaker_stops_consecutive_pipeline_failures():
    breaker = ErrorCircuitBreaker(threshold=3)
    assert breaker.observe("pipeline_error") is False
    assert breaker.observe("matched") is False
    assert breaker.observe("pipeline_error") is False
    assert breaker.observe("pipeline_error") is False
    assert breaker.observe("pipeline_error") is True
