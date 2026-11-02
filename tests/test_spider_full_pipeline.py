import sqlite3

from tools.spider_full_pipeline import dimension_evidence, parse_json, parse_sql_candidates, plan_sql_risks, rerank_retrieved_tables, retrieve_tables, selected_schema_prompt, semantic_risks


SCHEMA = {
    "table_names_original": ["singer", "stadium"],
    "table_names": ["singer", "stadium"],
    "column_names_original": [[-1, "*"], [0, "name"], [0, "age"], [1, "capacity"]],
    "column_types": ["text", "text", "number", "number"],
    "foreign_keys": [],
}


def test_spider_rag_and_plan_parsing():
    assert retrieve_tables("How many singers are there?", SCHEMA)[0] == "singer"
    assert "TABLE singer" in selected_schema_prompt(SCHEMA, ["singer"])
    assert "TABLE stadium" not in selected_schema_prompt(SCHEMA, ["singer"])
    assert parse_json('```json\n{"intent":"aggregate"}\n```')["intent"] == "aggregate"
    assert parse_sql_candidates('{"sql_candidates":[" SELECT 1; ","SELECT  1","SELECT 2"]}') == ["SELECT 1", "SELECT 2"]


def test_dimension_values_and_negative_semantic_risk(tmp_path):
    database = tmp_path / "pets.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE Pets(PetType TEXT)")
        connection.executemany("INSERT INTO Pets VALUES (?)", [("cat",), ("dog",)])
    evidence = dimension_evidence(database, ["Pets"], "students who do not own cats")
    assert evidence[0]["values"] == ["cat", "dog"]
    risks = semantic_risks("students who do not own cats", "SELECT id FROM pets WHERE PetType != 'cat'")
    assert risks and "NOT EXISTS" in risks[0]
    universe_risks = semantic_risks(
        "students who do not own cats",
        "SELECT s.id FROM student s JOIN has_pet h ON s.id=h.id EXCEPT SELECT id FROM has_pet",
    )
    assert any("左侧全集" in risk for risk in universe_risks)
    any_risks = semantic_risks(
        "countries with population smaller than any country in Asia",
        "SELECT name FROM country WHERE population < (SELECT MAX(population) FROM country)",
    )
    assert any("MIN" in risk for risk in any_risks)


def test_plan_sql_risks_validate_projection_and_distinct_contract():
    plan = {"output_fields": ["name"], "distinct_keys": ["singer_id"], "logical_operator": "and"}
    risks = plan_sql_risks("List distinct singer names", plan, "SELECT name, age FROM singer")
    assert any("输出列数量" in risk for risk in risks)
    assert any("缺少DISTINCT" in risk for risk in risks)


def test_table_rerank_combines_hits_with_fk_neighbors():
    class Hit:
        def __init__(self, table_name, score):
            self.table_name, self.score = table_name, score
    linked = dict(SCHEMA)
    linked["foreign_keys"] = [[1, 3]]
    tables = rerank_retrieved_tables("singer name", linked, [Hit("singer", .9)], limit=3)
    assert tables[0] == "singer"
    assert "stadium" in tables
