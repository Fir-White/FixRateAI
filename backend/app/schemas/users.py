"""API request/response schemas for users and authentication."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Role names as used in the database (site_memberships.role)
UserRole = Literal["executive", "chief_engineer", "engineer", "technician"]

# Simplified role names for the API layer
ApiRole = Literal["admin", "dispatcher", "engineer", "executor"]

# Mapping from DB roles to API roles
DB_TO_API_ROLE: dict[str, ApiRole] = {
    "executive": "admin",
    "chief_engineer": "engineer",
    "engineer": "engineer",
    "technician": "executor",
}

# Mapping from API roles to DB roles
API_TO_DB_ROLE: dict[ApiRole, str] = {
    "admin": "executive",
    "dispatcher": "executive",  # Dispatcher is an executive sub-role
    "engineer": "engineer",
    "executor": "technician",
}


class LoginRequest(BaseModel):
    """Login request with email and password."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserProfile(BaseModel):
    """Authenticated user profile."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    full_name: str
    email: str
    roles: list[dict[str, str]]  # [{site_id, role}, ...]


class SessionResponse(BaseModel):
    """Successful authentication response."""

    user: UserProfile
    csrf_token: str
    expires_at: datetime


class UserResponse(BaseModel):
    """User information returned by admin endpoints."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    full_name: str
    email: str
    is_active: bool
    created_at: datetime


class UserSiteRole(BaseModel):
    """User role on a specific site."""

    site_id: UUID
    user_id: UUID
    role: UserRole
    is_active: bool
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SiteResponse(BaseModel):
    """Site information."""

    model_config = ConfigDict(from_attributes=True)

    site_id: UUID
    name: str
    address: str | None
    timezone: str
    is_active: bool


class RolePermissions(BaseModel):
    """API role and its permissions."""

    role: ApiRole
    permissions: list[str]


# Permission matrix: API role → set of allowed permissions
ROLE_PERMISSIONS: dict[ApiRole, frozenset[str]] = {
    "admin": frozenset({
        "reference:read",
        "reference:write",
        "users:read",
        "users:write",
        "equipment:read",
        "equipment:write",
        "schedule:read",
        "schedule:write",
    }),
    "dispatcher": frozenset({
        "equipment:read",
        "equipment:write",
        "operation:read",
        "operation:write",
        "schedule:read",
        "schedule:write",
        "task:assign",
    }),
    "engineer": frozenset({
        "equipment:read",
        "operation:read",
        "schedule:read",
        "execution:read",
        "execution:accept",
        "forecast:read",
    }),
    "executor": frozenset({
        "task:read_assigned",
        "execution:write",
        "photo:write",
    }),
}
