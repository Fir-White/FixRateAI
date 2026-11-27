"""Typed boundary for approved knowledge retrieval and prepared workbook edits."""
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from app.schemas.assistant import Input


class SourceAccess(Input):
    user_id: UUID
    site_id: UUID
    role: str


class DocumentQuery(Input):
    query: str = Field(min_length=1, max_length=1000)
    effective_on: date
    equipment_id: UUID | None = None
    source_type: Literal['approved_regulation', 'manufacturer_document', 'operator_instruction'] | None = None
    limit: int = Field(default=10, ge=1, le=25)


class DocumentExcerpt(Input):
    source_id: UUID
    site_id: UUID
    source_type: Literal['approved_regulation', 'manufacturer_document', 'operator_instruction']
    revision: int = Field(ge=1)
    status: Literal['approved', 'draft', 'retired']
    title: str = Field(min_length=1, max_length=300)
    content_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    locator: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=6000)
    valid_from: date
    valid_until: date | None = None


class DocumentRetriever(Protocol):
    async def search(self, access: SourceAccess, query: DocumentQuery) -> list[DocumentExcerpt]:
        """Enforce access in the backend before returning document text."""
        ...


class WorkbookCellChange(Input):
    sheet: str = Field(min_length=1, max_length=31)
    row: int = Field(ge=1, le=1048576)
    column: int = Field(ge=1, le=16384)
    value: str | int | float | bool | None


class WorkbookEditRequest(Input):
    conversation_id: UUID
    attachment_id: UUID
    expected_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    cells: list[WorkbookCellChange] = Field(min_length=1, max_length=100)


class WorkbookEditPreview(Input):
    attachment_id: UUID
    before_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    cells: list[WorkbookCellChange] = Field(min_length=1, max_length=100)


class WorkbookEditor(Protocol):
    async def preview(self, access: SourceAccess, request: WorkbookEditRequest) -> WorkbookEditPreview:
        """Prepare a data-only preview. The action flow owns confirmation and dispatch."""
        ...
