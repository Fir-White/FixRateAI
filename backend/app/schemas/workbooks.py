from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkbookVersion(BaseModel):
    book_id: UUID
    filename: str
    version: int
    sha256: str
    size_bytes: int
    created_by: UUID
    created_at: datetime


class WorkbookPage(BaseModel):
    items: list[WorkbookVersion]
    total: int


class EditorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2_147_483_647)


class EditorCommit(EditorInput):
    session_id: UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: UUID


class EditorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class EditorStatus(BaseModel):
    session_id: UUID
    base_version: int
    state: Literal["editing", "pending", "ready", "unchanged", "failed", "saved"]
    snapshot_request_id: UUID | None
    snapshot_sha256: str | None
    expires_at: datetime


class EditorSession(EditorStatus):
    api_url: str
    document_config: dict
    detached_connections: bool
