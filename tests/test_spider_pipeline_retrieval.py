from tools.spider_full_pipeline import retrieve_tables, schema_neighbors, semantic_risks, tokens


SCHEMA = {
    "table_names_original": ["orders", "customers", "countries"],
    "table_names": ["orders", "customers", "countries"],
    "column_names_original": [[-1, "*"], [0, "customer_id"], [1, "id"], [1, "country_id"], [2, "id"]],
    "foreign_keys": [[1, 2], [3, 4]],
}


def test_schema_neighbors_are_bidirectional():
    graph = schema_neighbors(SCHEMA)
    assert graph["orders"] == {"customers"}
    assert graph["customers"] == {"orders", "countries"}


def test_retrieval_expands_fk_graph_to_bridge_and_dimension_tables():
    assert retrieve_tables("count orders", SCHEMA) == ["orders", "customers", "countries"]


def test_tokens_include_simple_singular_variants():
    assert "country" in tokens("countries")
    assert "maker" in tokens("makers")


def test_semantic_risk_detects_any_quantifier_direction():
    assert semantic_risks(
        "Which countries have greater area than any country in Europe?",
        "SELECT name FROM country WHERE area > (SELECT MAX(area) FROM country WHERE continent='Europe')",
    ) == []
    risks = semantic_risks(
        "Which countries have greater area than any country in Europe?",
        "SELECT name FROM country WHERE area > (SELECT MIN(area) FROM country WHERE continent='Europe')",
    )
    assert any("MAX而非MIN" in risk for risk in risks)


def test_semantic_risk_detects_missing_distinct_count():
    risks = semantic_risks(
        "How many different degrees are offered?",
        "SELECT COUNT(degree_id) FROM degree_programs",
    )
    assert any("COUNT必须使用DISTINCT" in risk for risk in risks)


def test_semantic_risk_accepts_distinct_inside_count_parentheses():
    assert semantic_risks(
        "How many different degrees are offered?",
        "SELECT COUNT(DISTINCT degree_summary_name) FROM degree_programs",
    ) == []
