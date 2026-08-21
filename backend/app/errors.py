"""Structured error handling for the Mehman.io backend.

Every expected failure mode has a code, HTTP status, human-readable message,
and retryable flag. Errors are designed to be safely surfaced to the frontend UI
without leaking stack traces, database internals, or API keys.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Exhaustive set of structured error codes."""

    INVALID_REQUEST = "INVALID_REQUEST"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_TEMPORARY_ERROR = "DATABASE_TEMPORARY_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UNAVAILABLE_ROOM = "UNAVAILABLE_ROOM"
    CAPACITY_ERROR = "CAPACITY_ERROR"
    INVALID_DATES = "INVALID_DATES"
    UNKNOWN_INFORMATION = "UNKNOWN_INFORMATION"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    CONVERSATION_CLOSED = "CONVERSATION_CLOSED"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Retryable error classification mapping
RETRYABLE_ERROR_CODES: set[ErrorCode] = {
    ErrorCode.DATABASE_TEMPORARY_ERROR,
    ErrorCode.LLM_TIMEOUT,
    ErrorCode.LLM_ERROR,
}


class AppError(Exception):
    """Base application error with structured metadata and retryability."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        retryable: Optional[bool] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable if retryable is not None else (code in RETRYABLE_ERROR_CODES)
        super().__init__(message)


class ErrorDetail(BaseModel):
    """Standardized error object."""

    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Structured error response returned to API clients."""

    error: ErrorDetail
