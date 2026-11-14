"""Bounded projections of one selected version, never a sum of alternatives."""
from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from pydantic import Field
from app.schemas.draft_plans import Model,DraftRecord,PlanIssue

class PlanLoadDay(Model):
    date: date
    planned_person_hours: Decimal
    reserved_person_hours: Decimal
    unplaced_due_person_hours: Decimal
    required_people_peak: int
    selected_people_peak: int
    available_people_peak: int|None
    available_person_hours: Decimal|None
    deficit_person_hours: Decimal|None

class PlanLoadMonth(Model):
    month: str
    due_person_hours: Decimal
    planned_person_hours: Decimal
    reserved_person_hours: Decimal
    unplaced_due_person_hours: Decimal
    available_person_hours: Decimal|None
    deficit_person_hours: Decimal|None
    required_people_peak: int
    selected_people_peak: int

class PlanLoadTotals(Model):
    total_person_hours: Decimal
    placed_person_hours: Decimal
    unplaced_person_hours: Decimal
    available_person_hours: Decimal|None
    deficit_person_hours: Decimal|None
    due_outside_view_person_hours: Decimal
    unplaced_outside_view_person_hours: Decimal

class PlanLoadPreview(Model):
    record: DraftRecord
    timezone: str
    checked_at: datetime
    resource_sha256: str
    source_state: Literal['current','stale','published_snapshot']
    validation_status: Literal['valid','incomplete','invalid']
    total_issues: int
    issues: list[PlanIssue] = Field(max_length=25)
    unknown_workers: int
    published_tasks: int
    totals: PlanLoadTotals
    months: list[PlanLoadMonth] = Field(max_length=14)
    days: list[PlanLoadDay] = Field(max_length=367)

PLAN_LOAD_CONTRACTS=(PlanLoadPreview,)
