from typing import Any, Literal
from pydantic import BaseModel, Field

class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "analyst"] = "analyst"
class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    role: Literal["admin", "analyst"] | None = None
    status: Literal["active", "disabled"] | None = None
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)
class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    base_plan_version: int | None = Field(default=None, ge=1)
    data_source_id: str | None = Field(default=None, max_length=36)
class ConfirmRequest(BaseModel):
    plan_version: int = Field(ge=1)
    plan_hash: str = Field(min_length=64, max_length=64)
class ExecuteRequest(BaseModel):
    plan_version: int = Field(ge=1)
class SchemaCatalogUpdateRequest(BaseModel):
    schema_name: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=128)
    column_name: str = Field(default="", max_length=128)
    display_name: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    enabled: bool = True
class CreateDataSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    database_type: str = "postgresql"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1000)
    schemas: list[str] = Field(default_factory=lambda: ["public"], min_length=1, max_length=30)
class UpdateDataSourceRulesRequest(BaseModel):
    business_rules: list[Literal["valid_settlement_only", "exclude_cancelled"]] = Field(
        default_factory=list, max_length=10
    )
class SemanticDefinitionRequest(BaseModel):
    kind: Literal["metric", "dimension", "value_set", "join", "business_rule", "golden_query"]
    semantic_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    label: str = Field(min_length=1, max_length=255)
    definition: dict[str, Any]
    status: Literal["draft", "certified", "disabled"] = "draft"
class UserPreferenceRequest(BaseModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
    value: Any
    enabled: bool = True
class BusinessMemoryRequest(BaseModel):
    source_id: str | None = Field(default=None, max_length=36)
    category: Literal["metric_definition", "dimension_definition", "business_rule", "field_mapping", "query_example"] = "business_rule"
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    evidence: str = Field(default="", max_length=2000)
    status: Literal["draft", "certified", "disabled"] = "draft"
    schema_fingerprint: str = Field(default="", max_length=64)
    expires_at: str | None = None


class QueryFeedbackRequest(BaseModel):
    verdict: Literal["correct", "incorrect"]
    issue_type: Literal["", "business_definition", "field_binding", "filter", "join", "sql_logic", "result", "other"] = ""
    comment: str = Field(default="", max_length=2000)


class FeedbackReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)
def envelope(data: Any, request_id: str) -> dict[str, Any]:
    return {"request_id": request_id, "data": data, "error": None, "meta": {}}
