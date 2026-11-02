from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.database.local", ROOT / ".env.knowledge.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SQLPilot"
    environment: str = "development"
    system_database_url: str = f"sqlite+aiosqlite:///{(ROOT / 'data' / 'sqlpilot_system.db').as_posix()}"
    dashscope_api_key: str = ""
    sqlpilot_secret_key: str = ""
    sqlpilot_bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    sqlpilot_bailian_model: str = "qwen3.6-plus-2026-04-02"
    sqlpilot_embedding_model: str = "text-embedding-v4"
    sqlpilot_embedding_dimensions: int = Field(default=1024, ge=64, le=2048)
    sqlpilot_embedding_batch_size: int = Field(default=10, ge=1, le=10)
    planner_timeout_seconds: float = Field(default=120, gt=0)
    planner_max_retries: int = Field(default=2, ge=0, le=5)
    sql_candidate_count: int = Field(default=3, ge=1, le=5)
    prompt_version: str = "query-planner-v1"
    auto_create_schema: bool = True
    auth_required: bool = True
    auth_token_ttl_seconds: int = Field(default=28_800, ge=300, le=604_800)
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "Sqlpilot@123"
    sqlpilot_db_host: str = ""
    sqlpilot_db_port: int = 5432
    sqlpilot_db_name: str = ""
    sqlpilot_db_user: str = ""
    sqlpilot_db_password: str = ""
    sqlpilot_kb_host: str = ""
    sqlpilot_kb_port: int = 5432
    sqlpilot_kb_name: str = ""
    sqlpilot_kb_user: str = ""
    sqlpilot_kb_password: str = ""
    business_schema: str = "nhsa"
    query_timeout_seconds: int = Field(default=15, ge=1, le=120)
    query_max_rows: int = Field(default=500, ge=1, le=5000)
    query_max_estimated_rows: int = Field(default=1_000_000, ge=1)
    query_max_total_cost: float = Field(default=1_000_000.0, gt=0)

    @property
    def business_database_configured(self) -> bool:
        return all((self.sqlpilot_db_host, self.sqlpilot_db_name, self.sqlpilot_db_user, self.sqlpilot_db_password))

    @property
    def secret_encryption_key(self) -> str:
        return self.sqlpilot_secret_key or self.dashscope_api_key

    @property
    def knowledge_database_configured(self) -> bool:
        return all((self.sqlpilot_kb_host, self.sqlpilot_kb_name, self.sqlpilot_kb_user, self.sqlpilot_kb_password))


@lru_cache
def get_settings() -> Settings:
    return Settings()
