from tools.spider_failure_analysis import classify, features


def test_features_extract_tables_and_query_shape():
    value = features("SELECT a.name, COUNT(*) FROM a JOIN b ON a.id=b.id GROUP BY a.name")
    assert value["tables"] == ["a", "b"]
    assert value["joins"] == 1
    assert value["has_group"] is True
    assert value["aggregates"] == ["count"]


def test_classify_schema_retrieval_before_sql_shape():
    case = {"sql": "SELECT name FROM a", "events": [
        {"stage": "schema_rag", "tables": ["a"]},
        {"stage": "plan_created", "plan": {"selected_tables": ["a"]}},
    ]}
    category, reasons = classify(case, "SELECT b.name FROM b")
    assert category == "schema_retrieval"
    assert "b" in reasons[0]


def test_does_not_blame_retrieval_when_sql_used_the_table():
    case = {"sql": "SELECT name FROM b", "events": [
        {"stage": "schema_rag", "tables": ["a"]},
        {"stage": "plan_created", "plan": {"selected_tables": ["a"]}},
    ]}
    category, _ = classify(case, "SELECT DISTINCT name FROM b")
    assert category == "distinct"
