import json
import sqlite3

from app.benchmarks.spider_knowledge import SpiderKnowledgeAdapter


def schema():
    return {
        "table_names_original": ["singer", "concert"],
        "table_names": ["singer", "concert"],
        "column_names_original": [[-1, "*"], [0, "Singer_ID"], [0, "Name"], [1, "concert_ID"], [1, "Singer_ID"]],
        "column_names": [[-1, "*"], [0, "singer id"], [0, "singer name"], [1, "concert id"], [1, "singer id"]],
        "primary_keys": [1, 3],
        "foreign_keys": [[4, 1]],
    }


def test_spider_knowledge_is_persistent_isolated_and_contains_no_gold_sql(tmp_path):
    database = tmp_path / "music.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE singer(Singer_ID INTEGER PRIMARY KEY, Name TEXT);"
            "CREATE TABLE concert(concert_ID INTEGER PRIMARY KEY, Singer_ID INTEGER);"
            "INSERT INTO singer VALUES(1, 'Alice');"
        )
    adapter = SpiderKnowledgeAdapter(tmp_path, tmp_path / "knowledge")
    result = adapter.build("music", database, schema())
    payload = json.loads(adapter.index_path("music").read_text(encoding="utf-8"))
    assert result["document_count"] == 7
    assert payload["namespace"] == "spider:music"
    assert "SELECT" not in json.dumps(payload)
    hits = adapter.search("music", "singer name Alice", database, schema())
    assert hits[0].table_name == "singer"
    assert hits[0].metadata["db_id"] == "music"
    column_hit = next(item for item in hits if item.object_type == "column")
    assert column_hit.as_dict()["column_name"]
    coverage_hits = adapter.search("music", "singer name and singer id", database, schema())
    assert coverage_hits[0].table_name == "singer"
