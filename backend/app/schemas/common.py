"""Common API schemas for error responses."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Single field-level error detail."""

    field: str | None = None
    issue: str


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str


# Standard error codes
class ErrorCode:
    """Enumeration of standard API error codes."""

    # Authentication & authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    CSRF_INVALID = "CSRF_INVALID"

    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_UUID = "INVALID_UUID"

    # Business logic errors
    STALE_REVISION = "STALE_REVISION"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    QUALIFICATION_MISMATCH = "QUALIFICATION_MISMATCH"
    ASSIGNMENT_CONFLICT = "ASSIGNMENT_CONFLICT"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    RULE_UNCONFIRMED = "RULE_UNCONFIRMED"
    DURATION_UNCONFIRMED = "DURATION_UNCONFIRMED"

    # Infrastructure errors
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
