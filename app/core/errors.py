from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    retryable: bool = False
    details: dict[str, Any] | None = None


class ConfigurationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("CONFIGURATION_ERROR", message, 503, False)


class PlannerError(AppError):
    def __init__(self, code: str, message: str, retryable: bool = False, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, 502, retryable, details)


class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__("NOT_FOUND", f"{resource}不存在", 404, False)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("VERSION_CONFLICT", message, 409, False)
