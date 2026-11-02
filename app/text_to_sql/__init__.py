__all__ = ["PostgresTextToSqlEngine"]


def __getattr__(name: str):
    if name == "PostgresTextToSqlEngine":
        from app.text_to_sql.engine import PostgresTextToSqlEngine
        return PostgresTextToSqlEngine
    raise AttributeError(name)
