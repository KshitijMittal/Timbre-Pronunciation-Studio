from __future__ import annotations

from typing import Any, Iterable


class AppError(Exception):
    error_type = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, details: Iterable[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = list(details or [])

    def to_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"type": self.error_type, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"success": False, "error": error}


class ValidationError(AppError):
    error_type = "VALIDATION_ERROR"
    status_code = 400


class LimitExceeded(AppError):
    error_type = "LIMIT_EXCEEDED"
    status_code = 400


class NotFound(AppError):
    error_type = "NOT_FOUND"
    status_code = 404


class Conflict(AppError):
    error_type = "CONFLICT"
    status_code = 409


class ConfigurationError(AppError):
    error_type = "CONFIGURATION_ERROR"
    status_code = 500


class InternalError(AppError):
    error_type = "INTERNAL_ERROR"
    status_code = 500


class UpstreamError(AppError):
    error_type = "UPSTREAM_ERROR"
    status_code = 502


class UpstreamAuthError(AppError):
    error_type = "UPSTREAM_AUTH"
    status_code = 401


class UpstreamForbiddenError(AppError):
    error_type = "UPSTREAM_FORBIDDEN"
    status_code = 403


class UpstreamRateLimitError(AppError):
    error_type = "UPSTREAM_RATE_LIMIT"
    status_code = 429


class UpstreamBadRequestError(AppError):
    error_type = "UPSTREAM_BAD_REQUEST"
    status_code = 400


class UpstreamTimeoutError(AppError):
    error_type = "UPSTREAM_TIMEOUT"
    status_code = 504


class UpstreamUnreachableError(AppError):
    error_type = "UPSTREAM_UNREACHABLE"
    status_code = 503
