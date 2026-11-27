"""Bounded asynchronous scenario calculation, comparison and explicit adoption."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field
from app.schemas.draft_plans import Model,PlanValidation,WorkSegment,DraftRecord,PlanIssue

class OptimizationWeights(Model):
    daily_peak: int = Field(default=10,ge=0,le=100)
    worker_spread: int = Field(default=3,ge=0,le=100)
    changes: int = Field(default=10,ge=0,le=100)
    earliness: int = Field(default=0,ge=0,le=100)

class OptimizationOptions(Model):
    grid_minutes: Literal[15,30,60] = 60
    time_limit_seconds: int = Field(default=10,ge=1,le=30)
    replan_existing: bool = False
    start_buffer_minutes: int = Field(default=5,ge=1,le=60)
    random_seed: int = Field(default=1,ge=0,le=2147483647)
    weights: OptimizationWeights = Field(default_factory=OptimizationWeights)

class StartOptimization(Model):
    expected_revision: int = Field(ge=1)
    idempotency_key: UUID
    options: OptimizationOptions = Field(default_factory=OptimizationOptions)

class OptimizationMetrics(Model):
    total_occurrences: int
    covered_occurrences: int
    mandatory_work_coverage: Decimal
    total_person_hours: Decimal
    placed_person_hours: Decimal
    unplaced_segments: int
    peak_daily_person_hours: Decimal
    peak_daily_utilization: Decimal | None
    daily_load_balance: Decimal | None
    staff_utilization: Decimal | None
    fairness_spread: Decimal | None
    changed_assignments: int
    unfilled_slots: int

class OptimizationVariant(Model):
    kind: Literal['baseline','optimized']
    method_version: str
    solver_status: Literal['HEURISTIC','OPTIMAL','FEASIBLE','INFEASIBLE','UNKNOWN','MODEL_INVALID','UNAVAILABLE']
    coverage_status: Literal['FEASIBLE','INFEASIBLE','UNKNOWN']
    optimality_proven: bool
    optimality_scope: Literal['discrete_candidate_model'] = 'discrete_candidate_model'
    model_complete: bool
    duration_seconds: float
    objective_value: int | None = None
    objective_bound: float | None = None
    metrics: OptimizationMetrics
    validation: PlanValidation
    applicable: bool

class OptimizationResult(Model):
    model_version: str
    objective_version: str
    candidate_count: int
    variable_count: int
    model_complete: bool
    completion_reason: Literal['finished','time_limit','model_limit','needs_input','solver_unavailable']
    diagnostics: list[PlanIssue]
    diagnostic_counts: dict[str,int]
    baseline: OptimizationVariant | None
    optimized: OptimizationVariant | None
    ready_for_real_plan: Literal[False] = False

class OptimizationRun(Model):
    run_id: UUID
    draft_id: UUID
    base_revision: int
    created_by: UUID
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    state: Literal['queued','running','cancel_requested','cancelled','succeeded','failed']
    options: OptimizationOptions
    input_sha256: str
    error_code: str | None
    result: OptimizationResult | None = None
    applied_revision: int | None = None
    applied_kind: Literal['baseline','optimized'] | None = None

class OptimizationRunList(Model):
    items: list[OptimizationRun]
    total: int

class OptimizationPlacements(Model):
    items: list[WorkSegment]
    worker_labels: dict[str,str]
    occurrence_labels: dict[str,str]
    total: int

class ApplyOptimization(Model):
    expected_revision: int = Field(ge=1)
    kind: Literal['baseline','optimized']
    reason: str = Field(min_length=1,max_length=2000)

OPTIMIZATION_CONTRACTS=(StartOptimization,OptimizationRun,OptimizationRunList,OptimizationPlacements,ApplyOptimization)
