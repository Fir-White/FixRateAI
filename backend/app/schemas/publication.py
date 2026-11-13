"""Immutable, explicitly approved publication of a finite catalog scenario."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from app.schemas.draft_plans import Model,PlanValidation,PlanIssue,DraftPolicy
from app.schemas.management import ChecklistSetting


class ExecutionProfile(Model):
    row_number:int=Field(ge=1,le=1048576)
    instructions:str=Field(min_length=1,max_length=10000)
    safety_notes:str=Field(min_length=1,max_length=5000)
    methodology_ref:str=Field(min_length=1,max_length=2000)
    engineer_note:str=Field(default='',max_length=2000)
    checklist:list[ChecklistSetting]=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def units(self):
        if any(c.answer_kind=='number' and not c.unit for c in self.checklist):
            raise ValueError('Числовой пункт требует подтверждённой единицы')
        return self


class PreparePublication(Model):
    expected_revision:int=Field(ge=1)
    idempotency_key:UUID
    reason:str=Field(min_length=1,max_length=2000)
    scope_note:str=Field(min_length=1,max_length=2000)
    profiles:list[ExecutionProfile]=Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def distinct(self):
        if len({p.row_number for p in self.profiles})!=len(self.profiles):raise ValueError('Профили строк повторяются')
        return self


class PublicationDecision(Model):
    expected_digest:str=Field(pattern='^[a-f0-9]{64}$')
    reason:str=Field(min_length=1,max_length=2000)


class PublishApproved(Model):
    expected_digest:str=Field(pattern='^[a-f0-9]{64}$')
    approval_token:UUID
    idempotency_key:UUID


class PublicationSummary(Model):
    added_tasks:int
    changed_tasks:Literal[0]=0
    cancelled_tasks:Literal[0]=0
    occurrences:int
    segments:int
    total_person_hours:Decimal
    selected_rows:int
    unselected_rows:int
    months:list[str]


class PublicationProposal(Model):
    proposal_id:UUID
    draft_id:UUID
    base_revision:int
    state:Literal['prepared','approved','rejected','published']
    created_by:UUID
    created_at:datetime
    expires_at:datetime
    reason:str
    scope_note:str
    proposal_digest:str
    summary:PublicationSummary
    validation:PlanValidation
    blockers:list[PlanIssue]
    blocker_count:int
    can_approve:bool
    decided_by:UUID|None=None
    decided_at:datetime|None=None
    decision_reason:str|None=None
    approval_token:UUID|None=None
    published_at:datetime|None=None
    publication_id:UUID|None=None
    planning_policy:DraftPolicy|None=None


class PublicationHistoryItem(Model):
    proposal_id:UUID
    draft_id:UUID
    base_revision:int
    state:Literal['prepared','approved','rejected','published']
    created_at:datetime
    expires_at:datetime
    summary:PublicationSummary
    blocker_count:int


class PublicationProposalList(Model):
    items:list[PublicationHistoryItem]
    total:int


class PublicationChange(Model):
    item_id:UUID
    occurrence_id:UUID
    segment_ids:list[UUID]
    depends_on_item_ids:list[UUID]
    row_number:int
    operation_code:str
    title:str
    equipment_ids:list[UUID]
    worker_ids:list[UUID]
    start_at:datetime|None
    end_at:datetime|None
    person_hours:Decimal
    kind:Literal['create']='create'
    previous:None=None
    execution:ExecutionProfile


class PublicationChangePage(Model):
    items:list[PublicationChange]
    total:int
    worker_labels:dict[str,str]
    equipment_labels:dict[str,str]


class PublicationProfileChoices(Model):
    items:list[dict]
    total:int


PUBLICATION_CONTRACTS=(PreparePublication,PublicationDecision,PublishApproved,PublicationProposal,
    PublicationProposalList,PublicationChangePage,PublicationProfileChoices)
