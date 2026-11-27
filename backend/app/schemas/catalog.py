"""Public read contracts for source drafts; no publication or normalization commands."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class SourceCell(BaseModel):
    address:str
    present:bool
    text:str|None
    raw_value:str|None
    cell_type:str|None
    style:str|None
    formula:str|None
    sheet:str|None=None

class CatalogMark(SourceCell):
    day:int=Field(ge=1,le=31)

class CatalogSummary(BaseModel):
    operation_count:int
    group_count:int
    top_level_group_count:int
    maintenance_types:dict[str,int]
    frequency_counts:dict[str,int]
    empty_duration_count:int
    mark_count:int
    readiness_counts:dict[str,int]
    ready_count:Literal[0]
    issue_count:int
    ready_for_real_plan:Literal[False]

class CatalogGroup(BaseModel):
    id:str
    code:str
    title:str
    row:int
    parent_id:str|None
    source_cells:list[str]

class CatalogIssue(BaseModel):
    code:str
    sheet:str
    cell:str
    message:str

class FrequencyHint(BaseModel):
    kind:Literal['quarter','yearly_count','year','month','day','week','daily_events','event','included_in','unknown']
    interval:int|None
    confirmed:Literal[False]

class CatalogOperation(BaseModel):
    row:int
    code:str
    title:str
    maintenance_type:str
    frequency_raw:str
    frequency_hint:FrequencyHint
    group_id:str|None
    quality_flags:list[str]
    interpretation:Literal['UNKNOWN']
    ready_for_real_plan:Literal[False]
    norm_value:None=None
    norm_unit:None=None
    quantity:None=None
    equipment_ids:list[UUID]
    calendar_month:Literal[1]
    calendar_year:None=None
    mark_count:int
    source_cells:dict[str,str]

class CatalogOperationSource(CatalogOperation):
    raw_cells:dict[str,SourceCell]
    calendar_marks:list[CatalogMark]

class CatalogRecord(BaseModel):
    import_id:UUID
    filename:str
    source_sha256:str
    parser_version:str
    status:Literal['draft']
    created_at:datetime
    summary:CatalogSummary

class CatalogDetail(CatalogRecord):
    source_kind:Literal['hvac_january_catalog']
    groups:list[CatalogGroup]
    issues:list[CatalogIssue]
    sheet2_diagnostic:list[SourceCell]
    header_context:list[SourceCell]

class CatalogList(BaseModel):
    items:list[CatalogRecord]
    total:int

class CatalogOperations(BaseModel):
    items:list[CatalogOperation]
    total:int

class CatalogPreview(BaseModel):
    format:Literal['hvac_catalog']
    preview_token:str
    can_save_draft:Literal[True]
    parser_version:str
    source_sha256:str
    summary:CatalogSummary
    groups:list[CatalogGroup]
    issues:list[CatalogIssue]
    header_context:list[SourceCell]
    sheet2_diagnostic:list[SourceCell]
    operations:list[CatalogOperation]
    total:int
    ready_for_real_plan:Literal[False]

class CatalogSaved(BaseModel):
    import_id:UUID
    status:Literal['draft']
    already_saved:bool
    summary:CatalogSummary
    ready_for_real_plan:Literal[False]

from .catalog_decisions import DECISION_CONTRACTS
CATALOG_CONTRACTS=(CatalogPreview,CatalogSaved,CatalogList,CatalogDetail,CatalogOperations,CatalogOperationSource,*DECISION_CONTRACTS)
