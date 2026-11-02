from tools.spider_generate import extract_sql, schema_prompt


def test_extract_sql_and_schema_prompt():
    schema = {
        "table_names_original": ["singer"],
        "column_names_original": [[-1, "*"], [0, "Singer_ID"], [0, "Name"]],
        "column_types": ["text", "number", "text"],
        "foreign_keys": [],
    }
    prompt = schema_prompt(schema)
    assert "TABLE singer (Singer_ID number, Name text)" in prompt
    assert extract_sql("```sql\nSELECT Name FROM singer;\n```") == "SELECT Name FROM singer"
