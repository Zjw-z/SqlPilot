import json

from tools.spider_regression_sets import build_sets


def test_build_sets_separates_stable_fixed_regressed_and_persistent(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(json.dumps({"cases": [
        {"case_id": "a", "matched": True}, {"case_id": "b", "matched": False},
        {"case_id": "c", "matched": True}, {"case_id": "d", "matched": False},
    ]}), encoding="utf-8")
    candidate.write_text(json.dumps({"cases": [
        {"case_id": "a", "matched": True}, {"case_id": "b", "matched": True},
        {"case_id": "c", "matched": False}, {"case_id": "d", "matched": False},
    ]}), encoding="utf-8")
    assert build_sets(baseline, candidate) == {
        "stable_correct": ["a"], "fixed": ["b"], "regressed": ["c"],
        "persistent_failure": ["d"],
    }
