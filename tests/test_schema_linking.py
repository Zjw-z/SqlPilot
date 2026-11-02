from app.planning.models import DateRange, PlanProvenance, QueryPlanV1, SemanticBinding
from app.schema_linking import link_fields


def test_field_linker_prioritizes_exact_value_and_confirmed_binding():
    context = [
        {"object_type": "column", "object_key": "main.airlines.name", "schema_name": "main",
         "table_name": "airlines", "column_name": "name", "business_name": "airline name",
         "content": "airline name", "score": .5, "metadata": {"sample_values": ["JetBlue Airways"]}},
        {"object_type": "column", "object_key": "main.flights.airline_id", "schema_name": "main",
         "table_name": "flights", "column_name": "airline_id", "business_name": "airline id",
         "content": "airline identifier", "score": .7, "metadata": {}},
    ]
    plan = QueryPlanV1(
        intent="aggregate_analysis", metrics=["flight_count"], dimensions=[],
        date_range=DateRange(type="all"), provenance=PlanProvenance(model="test", prompt_version="test"),
        semantic_bindings=[SemanticBinding(role="filter", key="airline", label="航空公司",
            object_key="main.airlines.name", schema_name="main", table_name="airlines", column_name="name")],
    )
    candidates = link_fields("number of JetBlue Airways flights", context, plan)
    assert candidates[0].object_key == "main.airlines.name"
    assert candidates[0].value_match is True
    assert candidates[0].selected is True
