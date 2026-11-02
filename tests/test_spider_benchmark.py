import json
import sqlite3

from app.benchmarks.spider import SpiderBenchmark


def test_spider_execution_accuracy_and_readiness(tmp_path):
    dataset = tmp_path / "spider"
    database_dir = dataset / "database" / "demo"
    database_dir.mkdir(parents=True)
    (dataset / "dev.json").write_text(json.dumps([{
        "db_id": "demo", "question": "有多少名用户？", "query": "SELECT count(*) FROM users"
    }], ensure_ascii=False), encoding="utf-8")
    (dataset / "tables.json").write_text(json.dumps([{"db_id": "demo"}]), encoding="utf-8")
    with sqlite3.connect(database_dir / "demo.sqlite") as connection:
        connection.execute("CREATE TABLE users(id INTEGER)")
        connection.executemany("INSERT INTO users VALUES (?)", [(1,), (2,)])
    benchmark = SpiderBenchmark(dataset)
    report = benchmark.evaluate({"dev-0000": "SELECT count(id) FROM users"})
    assert benchmark.readiness()["ready"] is True
    assert report.execution_accuracy == 1.0
    assert report.cases[0].status == "matched"
    assert report.cases[0].hardness == "easy"


def test_spider_reports_missing_database(tmp_path):
    (tmp_path / "dev.json").write_text(json.dumps([{
        "db_id": "missing", "question": "test", "query": "SELECT 1"
    }]), encoding="utf-8")
    (tmp_path / "tables.json").write_text("[]", encoding="utf-8")
    benchmark = SpiderBenchmark(tmp_path)
    assert benchmark.readiness()["missing_databases"] == ["missing"]
    report = benchmark.evaluate({"dev-0000": "SELECT 1"})
    assert report.missing_databases == 1


def test_spider_can_evaluate_only_predicted_cases(tmp_path):
    (tmp_path / "dev.json").write_text(json.dumps([
        {"db_id": "missing", "question": "one", "query": "SELECT 1"},
        {"db_id": "missing", "question": "two", "query": "SELECT 2"},
    ]), encoding="utf-8")
    (tmp_path / "tables.json").write_text("[]", encoding="utf-8")
    report = SpiderBenchmark(tmp_path).evaluate({"dev-0001": "SELECT 2"}, only_predicted=True)
    assert report.total == 1


def test_spider_result_equivalence_allows_column_reordering():
    assert SpiderBenchmark._equivalent([(1, "a"), (2, "b")], [("a", 1), ("b", 2)])
