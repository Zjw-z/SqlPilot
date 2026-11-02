from app.data_sources import TOOLS, _cosine, _dictionary_candidate, _embedding, _tokens
from app.infrastructure.secrets import protect_secret, unprotect_secret


def test_database_password_is_encrypted_with_windows_dpapi():
    encrypted = protect_secret("test-database-password", "test-encryption-key")

    assert encrypted != "test-database-password"
    assert unprotect_secret(encrypted, "test-encryption-key") == "test-database-password"


def test_schema_documents_have_searchable_vector_representation():
    query = _embedding("医保基金支付")
    relevant = _embedding("基金支付总额 fund_pay_sumamt")
    unrelated = _embedding("医院地址和联系电话")

    assert _cosine(query, relevant) > _cosine(query, unrelated)
    assert "医保" in _tokens("统计医保基金支付")


def test_ready_source_registers_readonly_query_tools():
    assert TOOLS == [
        "search_schema", "get_table_detail", "lookup_dimension_values", "explain_sql", "execute_readonly_sql"
    ]


def test_dictionary_sampling_selects_business_codes_but_excludes_pii():
    assert _dictionary_candidate({"column_name": "medical_type_code", "column_comment": "医疗类别代码", "data_type": "varchar"})
    assert not _dictionary_candidate({"column_name": "patient_name", "column_comment": "患者姓名", "data_type": "varchar"})
    assert not _dictionary_candidate({"column_name": "total_fee", "column_comment": "医疗总费用", "data_type": "numeric"})
